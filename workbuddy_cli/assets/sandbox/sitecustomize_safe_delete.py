"""
genie-safe-delete — Python 运行时安全删除 shim

通过 PYTHONPATH 中的 sitecustomize.py 自动加载，
拦截 os.remove / os.rmdir / shutil.rmtree / pathlib 的删除 API，
把文件移入操作系统的回收站而不是真删。

实现：优先调用 genie-trash native binary；不可用时回退到平台内联实现
（macOS: ctypes FSMoveObjectToTrashSync，Windows: ctypes SHFileOperationW，
 Linux: freedesktop Trash spec 纯 Python 实现）。

设计要点见 apps/workbuddy-desktop/docs/safe-delete-runtime-trash.md
"""

import errno
import builtins
import io
import json
import os
import socket
import stat
import sys
import tempfile
import time

# ---------------------------------------------------------------------------
# 触发条件
# ---------------------------------------------------------------------------

_SESSION_ID = (
    os.environ.get("CODEBUDDY_SESSION_ID")
    or os.environ.get("CLAUDE_SESSION_ID")
)
_IN_SANDBOX = os.environ.get("CODEBUDDY_SAFE_DELETE_SANDBOX") == "1"
_SAFE_DELETE_ENABLED = os.environ.get("CODEBUDDY_SAFE_DELETE_ENABLED") != "0"
_BROKERED_FS_HOOK_ENABLED = (
    os.environ.get("CODEBUDDY_BROKERED_FS_HOOK_ENABLED") == "1"
    or _IN_SANDBOX
)

if _SESSION_ID:
    # __file__ 在 sitecustomize 加载时指向本文件路径，dirname 即 vendor/shim/
    _SHIM_DIR = os.path.dirname(os.path.abspath(__file__))

    # sitecustomize 是 Python 保留文件名，Python 启动时会自动 import
    # sys.path 上第一个匹配的模块。把 shim 目录前置到 PYTHONPATH 后，
    # 用户环境原有的 sitecustomize（conda / virtualenv / 企业配置等）会被覆盖。
    # 因此在注入 shim 前，先临时从 sys.modules 和 sys.path 中移除自身，
    # 尝试加载原始的 sitecustomize，再恢复自身。
    _self = sys.modules.pop("sitecustomize", None)
    if _SHIM_DIR in sys.path:
        sys.path.remove(_SHIM_DIR)
    try:
        __import__("sitecustomize")
    except ImportError as e:
        # 只有模块本身不存在时才静默（e.name == "sitecustomize"）；
        # 若模块存在但内部导入失败（e.name 为其他名），输出 traceback 到 stderr
        if e.name is not None and e.name != "sitecustomize":
            import traceback
            traceback.print_exc(file=sys.stderr)
    if _SHIM_DIR not in sys.path:
        sys.path.insert(0, _SHIM_DIR)
    if _self is not None:
        sys.modules["sitecustomize"] = _self

    # -----------------------------------------------------------------------
    # 平台内联 trash 实现（genie-trash binary 不可用时的降级路径）
    # 仅使用标准库，无第三方依赖。
    # -----------------------------------------------------------------------

    if sys.platform == "darwin":
        # macOS: ctypes → CoreServices.FSMoveObjectToTrashSync
        # API 在 macOS 10.8 标记 deprecated，但至今仍可用；不依赖 Finder，headless 安全。
        from ctypes import cdll, byref, Structure, c_char, c_char_p
        from ctypes.util import find_library as _find_library

        _Foundation = cdll.LoadLibrary(_find_library("Foundation"))
        _CoreServices = cdll.LoadLibrary(_find_library("CoreServices"))
        _GetOSStatusComment = _Foundation.GetMacOSStatusCommentString
        _GetOSStatusComment.restype = c_char_p
        _FSPathMakeRefWithOptions = _CoreServices.FSPathMakeRefWithOptions
        _FSMoveObjectToTrashSync = _CoreServices.FSMoveObjectToTrashSync

        class _FSRef(Structure):
            _fields_ = [("hidden", c_char * 80)]

        def _platform_trash(abs_path):
            path_b = abs_path.encode("utf-8") if isinstance(abs_path, str) else abs_path
            fp = _FSRef()
            rc = _FSPathMakeRefWithOptions(path_b, 0x01, byref(fp), None)
            if rc:
                raise OSError(_GetOSStatusComment(rc).decode("utf-8", errors="replace"))
            rc = _FSMoveObjectToTrashSync(byref(fp), None, 0)
            if rc:
                raise OSError(_GetOSStatusComment(rc).decode("utf-8", errors="replace"))

    elif sys.platform == "win32":
        # Windows: ctypes → shell32.SHFileOperationW
        # API 在 Vista 后标记 deprecated（推荐 IFileOperation），但仍广泛可用。
        from ctypes import (
            windll, Structure, byref, c_uint,
            create_unicode_buffer, addressof,
            GetLastError, FormatError,
        )
        from ctypes.wintypes import HWND, UINT, BOOL, LPCWSTR

        _kernel32 = windll.kernel32
        _shell32 = windll.shell32
        _FO_DELETE = 3
        _FOF_FLAGS = 64 | 16 | 1024 | 4  # ALLOWUNDO | NOCONFIRMATION | NOERRORUI | SILENT

        class _SHFILEOPSTRUCTW(Structure):
            _fields_ = [
                ("hwnd", HWND), ("wFunc", UINT), ("pFrom", LPCWSTR),
                ("pTo", LPCWSTR), ("fFlags", c_uint), ("fAnyOperationsAborted", BOOL),
                ("hNameMappings", c_uint), ("lpszProgressTitle", LPCWSTR),
            ]

        def _get_short_path(path):
            """调用 GetShortPathNameW 处理超长路径和特殊字符。"""
            prefix = "\\\\?\\"
            long_path = (prefix + "UNC" + path[1:]) if path.startswith("\\\\") else (prefix + path)
            n = _kernel32.GetShortPathNameW(long_path, None, 0)
            if not n:
                err = GetLastError()
                raise OSError(err, FormatError(err), path)
            buf = create_unicode_buffer(n)
            _kernel32.GetShortPathNameW(long_path, buf, n)
            s = buf.value
            # 还原 UNC 前缀：\\?\UNC\server → \\server
            if s.startswith("\\\\?\\UNC"):
                return "\\" + s[7:]
            # 普通路径：去掉 \\?\
            return s[4:] if s.startswith(prefix) else s

        def _platform_trash(abs_path):
            path = _get_short_path(os.path.abspath(abs_path))
            # pFrom 需要双 null 终止的字符串（SHFileOperationW 规范）
            buf = create_unicode_buffer(path, len(path) + 2)
            fileop = _SHFILEOPSTRUCTW()
            fileop.wFunc = _FO_DELETE
            fileop.pFrom = LPCWSTR(addressof(buf))
            fileop.fFlags = _FOF_FLAGS
            result = _shell32.SHFileOperationW(byref(fileop))
            if result:
                raise OSError("SHFileOperationW 失败: 0x%x" % result)

    else:
        # Linux / 其他 POSIX: freedesktop Trash spec（XDG Base Directory）
        from datetime import datetime as _datetime
        import shutil as _shutil

        def _trashinfo_encode(s):
            """仅编码非 ASCII 和控制字符，与 Node.js/Bash 版本保持一致。"""
            parts = []
            for ch in s:
                if '\x20' <= ch <= '\x7e':
                    parts.append(ch)
                else:
                    parts.append(''.join('%{:02X}'.format(b) for b in ch.encode('utf-8')))
            return ''.join(parts)

        _uid = os.getuid()
        _xdg_data = os.fsencode(
            os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        )
        _home_trash = os.path.join(_xdg_data, b"Trash")

        def _find_ext_volume_trash(volume_root):
            """freedesktop spec §1: 优先 .Trash/$uid（需 sticky bit），否则 .Trash-$uid。"""
            uid_b = str(_uid).encode()
            trash_base = os.path.join(volume_root, b".Trash")
            if (
                os.path.isdir(trash_base)
                and not os.path.islink(trash_base)
                and bool(os.lstat(trash_base).st_mode & 0o1000)  # sticky bit
            ):
                trash_dir = os.path.join(trash_base, uid_b)
                os.makedirs(trash_dir, 0o700, exist_ok=True)
                return trash_dir
            trash_dir = os.path.join(volume_root, b".Trash-" + uid_b)
            os.makedirs(trash_dir, 0o700, exist_ok=True)
            return trash_dir

        def _trash_move(path_b, dest_trash, topdir):
            """将文件移动到 dest_trash，并写入对应的 .trashinfo。"""
            files_dir = os.path.join(dest_trash, b"files")
            info_dir = os.path.join(dest_trash, b"info")
            os.makedirs(files_dir, 0o700, exist_ok=True)
            os.makedirs(info_dir, 0o700, exist_ok=True)

            filename = os.path.basename(path_b)
            base, ext = os.path.splitext(filename)
            dest_name = filename
            counter = 0
            while os.path.exists(os.path.join(files_dir, dest_name)) or \
                    os.path.exists(os.path.join(info_dir, dest_name + b".trashinfo")):
                counter += 1
                dest_name = base + b"." + str(counter).encode() + ext

            real_path = os.path.realpath(path_b)
            real_top = os.path.realpath(topdir)
            if real_path.startswith(real_top):
                info_path = _trashinfo_encode(os.fsdecode(os.path.relpath(path_b, topdir)))
            else:
                info_path = _trashinfo_encode(os.fsdecode(os.path.abspath(path_b)))

            info_content = "[Trash Info]\nPath=%s\nDeletionDate=%s\n" % (
                info_path, _datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            )
            info_file = os.path.join(info_dir, dest_name + b".trashinfo")
            fd = os.open(info_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(info_content)
            except Exception:
                try:
                    _orig_unlink(info_file)
                except OSError:
                    pass
                raise

            dest_file = os.path.join(files_dir, dest_name)
            try:
                os.rename(path_b, dest_file)
            except OSError as e:
                if e.errno == errno.EXDEV:
                    # _shutil.move 内部调用 shutil.rmtree，后者已被补丁为
                    # _safe_shutil_rmtree —— 这会重入 _try_trash 形成循环。
                    # 临时将 shutil.rmtree 恢复为原始版本后再调用。
                    _saved_rmtree = shutil.rmtree
                    shutil.rmtree = _orig_shutil_rmtree
                    try:
                        _shutil.move(os.fsdecode(path_b), os.fsdecode(dest_file))
                    except Exception:
                        try:
                            _orig_unlink(info_file)
                        except OSError:
                            pass
                        raise
                    finally:
                        shutil.rmtree = _saved_rmtree
                else:
                    try:
                        _orig_unlink(info_file)
                    except OSError:
                        pass
                    raise

        def _platform_trash(abs_path):
            path_b = os.fsencode(abs_path)
            path_dev = os.lstat(path_b).st_dev
            home_dev = os.lstat(os.path.expanduser(b"~")).st_dev
            if path_dev == home_dev:
                _trash_move(path_b, _home_trash, _xdg_data)
            else:
                mount = os.path.realpath(path_b)
                while not os.path.ismount(mount):
                    mount = os.path.split(mount)[0]
                dest_trash = _find_ext_volume_trash(mount)
                try:
                    _trash_move(path_b, dest_trash, mount)
                except OSError as e:
                    if e.errno == errno.EXDEV:
                        _trash_move(path_b, _home_trash, _xdg_data)
                    else:
                        raise

    # -----------------------------------------------------------------------
    # 全局状态
    # -----------------------------------------------------------------------

    # 保存原始引用（patch 前）
    import shutil
    import subprocess
    import pathlib
    import platform

    _orig_builtin_open = builtins.open
    _orig_io_open = io.open
    _orig_os_open = os.open
    _orig_remove = os.remove
    _orig_unlink = os.unlink
    _orig_rmdir = os.rmdir
    _orig_mkdir = os.mkdir
    _orig_makedirs = os.makedirs
    _orig_rename = os.rename
    _orig_replace = os.replace
    _orig_chmod = os.chmod
    _orig_link = os.link
    _orig_symlink = os.symlink
    _orig_shutil_rmtree = shutil.rmtree
    _orig_shutil_copyfile = shutil.copyfile
    _orig_shutil_copy2 = shutil.copy2
    _orig_shutil_copytree = shutil.copytree
    _orig_path_unlink = pathlib.Path.unlink
    _orig_path_rmdir = pathlib.Path.rmdir
    _orig_path_mkdir = pathlib.Path.mkdir
    _orig_path_touch = pathlib.Path.touch
    _report_path = os.environ.get("CODEBUDDY_SAFE_DELETE_REPORT_PATH")

    # -----------------------------------------------------------------------
    # Brokered sandbox file-token support.
    #
    # Mirrors the shell/toybox broker model, but the interception point is
    # Python's runtime file APIs. The host still owns policy and token issuing.
    # -----------------------------------------------------------------------

    _broker_socket_path = os.environ.get("CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS")
    _broker_session_id = os.environ.get("CODEBUDDY_SANDBOX_BROKER_SESSION_ID") or _SESSION_ID
    _broker_tool_call_id = (
        os.environ.get("CODEBUDDY_SANDBOX_BROKER_TOOL_CALL_ID")
        or os.environ.get("CODEBUDDY_TOOL_CALL_ID")
    )
    _broker_trace_id = os.environ.get("CODEBUDDY_SANDBOX_BROKER_TRACE_ID")
    _broker_file_token_command = (
        os.environ.get("CODEBUDDY_SANDBOX_FILE_TOKEN_OPERATION_COMMAND")
        or "FileTokenRequest"
    )
    _broker_host_operation_command = os.environ.get(
        "CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND"
    )
    _broker_request_seq = 0
    _broker_host_operation_depth = 0
    _COPYTREE_DEFAULT = object()

    def _broker_enabled():
        return bool(sys.platform == "darwin" and _BROKERED_FS_HOOK_ENABLED and _broker_socket_path and _broker_session_id and _broker_file_token_command)

    def _broker_write_completed_enabled():
        return bool(sys.platform == "darwin" and _BROKERED_FS_HOOK_ENABLED and _broker_socket_path and _broker_session_id)

    def _broker_host_ops_enabled():
        return bool(
            sys.platform == "darwin"
            and _BROKERED_FS_HOOK_ENABLED
            and _broker_socket_path
            and _broker_session_id
            and _broker_host_operation_command
            and _broker_host_operation_depth == 0
        )

    def _broker_abs_path(file_path, dir_fd=None):
        if isinstance(file_path, int):
            return None
        try:
            raw_path = os.fspath(file_path)
        except TypeError:
            return None
        if isinstance(raw_path, bytes):
            try:
                raw_path = os.fsdecode(raw_path)
            except UnicodeError:
                return None
        if not raw_path:
            return None
        if dir_fd is not None and not os.path.isabs(raw_path):
            return None
        return os.path.abspath(raw_path)

    def _broker_readline(sock):
        chunks = []
        while True:
            chunk = sock.recv(1)
            if not chunk:
                break
            if chunk == b"\n":
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")

    def _broker_consume_token(token):
        if sys.platform != "darwin":
            return
        import ctypes

        lib = ctypes.CDLL(None, use_errno=True)
        fn = lib.sandbox_extension_consume
        fn.argtypes = [ctypes.c_char_p]
        fn.restype = ctypes.c_int64
        handle = fn(token.encode("utf-8"))
        if handle <= 0:
            err = ctypes.get_errno() or errno.EINVAL
            raise OSError(err, os.strerror(err))

    def _broker_response_timeout_seconds(request):
        if (
            request.get("command") == _broker_file_token_command
            and request.get("operation") == "read"
        ):
            try:
                timeout_ms = int(os.environ.get("CODEBUDDY_SANDBOX_BROKER_READ_TIMEOUT_MS", ""))
            except (TypeError, ValueError):
                timeout_ms = 0
            if timeout_ms > 0:
                return timeout_ms / 1000.0
        return 5

    def _broker_send_request(request):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect(_broker_socket_path)
                sock.sendall((json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8"))
                sock.settimeout(_broker_response_timeout_seconds(request))
                line = _broker_readline(sock)
        except Exception:
            return None

        try:
            response = json.loads(line)
        except Exception:
            return None
        return response if isinstance(response, dict) else None

    def _broker_request_file_token(abs_path, operation):
        global _broker_request_seq
        if not _broker_enabled():
            return

        _broker_request_seq += 1
        request = {
            "id": "python-%d" % _broker_request_seq,
            "command": _broker_file_token_command,
            "runtime": "python",
            "operation": operation,
            "path": abs_path,
            "sessionId": _broker_session_id,
        }
        if _broker_tool_call_id:
            request["toolCallId"] = _broker_tool_call_id
        if _broker_trace_id:
            request["brokerTraceId"] = _broker_trace_id

        response = _broker_send_request(request)
        if response is None:
            # Match toybox's fail-to-sandbox behavior: if IPC is unavailable,
            # do not grant anything here; let the native sandbox decide.
            return

        token = response.get("token") if response.get("ok") is True else None
        if isinstance(token, str) and token:
            _broker_consume_token(token)
            return
        if response.get("decision") == "sandbox":
            return

        raise PermissionError(
            response.get("error")
            or "Brokered sandbox denied %s access to %s" % (operation, abs_path)
        )

    def _broker_notify_file_write_completed(abs_path, existed_before):
        global _broker_request_seq
        if existed_before:
            return
        if not _broker_write_completed_enabled():
            return

        _broker_request_seq += 1
        request = {
            "id": "python-%d" % _broker_request_seq,
            "command": "FileWriteCompleted",
            "runtime": "python",
            "operation": "write",
            "path": abs_path,
            "sessionId": _broker_session_id,
        }
        if _broker_tool_call_id:
            request["toolCallId"] = _broker_tool_call_id
        if _broker_trace_id:
            request["brokerTraceId"] = _broker_trace_id
        _broker_send_request(request)

    def _broker_request_host_operation(operation, primary_path, **fields):
        global _broker_request_seq
        if not _broker_host_ops_enabled():
            return False

        _broker_request_seq += 1
        request = {
            "id": "python-%d" % _broker_request_seq,
            "command": _broker_host_operation_command,
            "runtime": "python",
            "operation": operation,
            "sessionId": _broker_session_id,
        }
        request.update(fields)
        if _broker_tool_call_id:
            request["toolCallId"] = _broker_tool_call_id
        if _broker_trace_id:
            request["brokerTraceId"] = _broker_trace_id

        response = _broker_send_request(request)
        if response is None:
            return False
        if response.get("ok") is True:
            return True
        if response.get("decision") == "sandbox":
            return False
        if response.get("ok") is False and response.get("decision") == "host-op":
            # 策略已放行但宿主代执行失败：还原为对应 errno 的标准异常，
            # 让调用方按普通文件系统错误处理（例如 EEXIST）。
            # 打上标记，供安全删除链路识别「真实失败」而非「策略拒绝」。
            error = _broker_host_operation_error(response, operation, primary_path)
            error._codebuddy_broker_host_op_error = True
            raise error
        raise PermissionError(
            response.get("error")
            or "Brokered sandbox denied host %s for %s" % (operation, primary_path)
        )

    def _broker_host_operation_error(response, operation, primary_path):
        error_code = response.get("errorCode")
        message = (
            response.get("error")
            or "Brokered host %s failed for %s" % (operation, primary_path)
        )
        errno_value = errno.EIO
        if isinstance(error_code, str) and error_code:
            errno_value = getattr(errno, error_code, errno.EIO)
        # 三参形式让 OSError 派生出正确的子类（FileExistsError 等）并带上 filename，
        # 与原生 os.mkdir/os.unlink 抛出的异常形状一致。
        return OSError(errno_value, message, primary_path)

    def _broker_call_native_host_operation(fn, *args, **kwargs):
        global _broker_host_operation_depth
        _broker_host_operation_depth += 1
        try:
            return fn(*args, **kwargs)
        finally:
            _broker_host_operation_depth -= 1

    def _broker_operation_for_mode(mode):
        mode = mode or "r"
        return "write" if any(ch in mode for ch in "wax+") else "read"

    def _broker_operation_for_flags(flags):
        write_flags = (
            os.O_WRONLY
            | os.O_RDWR
            | os.O_CREAT
            | os.O_TRUNC
            | os.O_APPEND
            | getattr(os, "O_TMPFILE", 0)
        )
        return "write" if flags & write_flags else "read"

    def _broker_gate(file_path, operation, dir_fd=None):
        abs_path = _broker_abs_path(file_path, dir_fd=dir_fd)
        if abs_path:
            _broker_request_file_token(abs_path, operation)

    def _brokered_open(
        open_fn,
        file,
        mode="r",
        buffering=-1,
        encoding=None,
        errors=None,
        newline=None,
        closefd=True,
        opener=None,
    ):
        operation = _broker_operation_for_mode(mode)
        abs_path = _broker_abs_path(file)
        existed_before = bool(abs_path and os.path.exists(abs_path))
        if abs_path:
            _broker_request_file_token(abs_path, operation)
        file_obj = open_fn(file, mode, buffering, encoding, errors, newline, closefd, opener)
        if operation == "write" and abs_path and os.path.exists(abs_path):
            _broker_notify_file_write_completed(abs_path, existed_before)
        return file_obj

    def _brokered_builtin_open(
        file,
        mode="r",
        buffering=-1,
        encoding=None,
        errors=None,
        newline=None,
        closefd=True,
        opener=None,
    ):
        return _brokered_open(
            _orig_builtin_open,
            file, mode, buffering, encoding, errors, newline, closefd, opener,
        )

    def _brokered_io_open(
        file,
        mode="r",
        buffering=-1,
        encoding=None,
        errors=None,
        newline=None,
        closefd=True,
        opener=None,
    ):
        return _brokered_open(
            _orig_io_open,
            file, mode, buffering, encoding, errors, newline, closefd, opener,
        )

    def _brokered_os_open(path, flags, mode=0o777, *, dir_fd=None):
        _broker_gate(path, _broker_operation_for_flags(flags), dir_fd=dir_fd)
        if dir_fd is not None:
            return _orig_os_open(path, flags, mode, dir_fd=dir_fd)
        return _orig_os_open(path, flags, mode)

    def _brokered_os_mkdir(path, mode=0o777, *, dir_fd=None):
        abs_path = _broker_abs_path(path, dir_fd=dir_fd)
        if abs_path and isinstance(mode, int) and _broker_request_host_operation(
            "mkdir", abs_path, path=abs_path, mode=mode
        ):
            return None
        if dir_fd is not None:
            return _broker_call_native_host_operation(_orig_mkdir, path, mode, dir_fd=dir_fd)
        return _broker_call_native_host_operation(_orig_mkdir, path, mode)

    def _brokered_os_makedirs(name, mode=0o777, exist_ok=False):
        abs_path = _broker_abs_path(name)
        if abs_path and isinstance(mode, int):
            if not exist_ok and os.path.exists(abs_path):
                return _broker_call_native_host_operation(
                    _orig_makedirs, name, mode=mode, exist_ok=exist_ok
                )
            if _broker_request_host_operation(
                "mkdir", abs_path, path=abs_path, recursive=True, mode=mode
            ):
                return None
        return _broker_call_native_host_operation(
            _orig_makedirs, name, mode=mode, exist_ok=exist_ok
        )

    def _brokered_os_rename(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
        from_path = _broker_abs_path(src, dir_fd=src_dir_fd)
        to_path = _broker_abs_path(dst, dir_fd=dst_dir_fd)
        if from_path and to_path and _broker_request_host_operation(
            "rename", from_path, **{"from": from_path, "to": to_path}
        ):
            return None
        if src_dir_fd is not None or dst_dir_fd is not None:
            return _broker_call_native_host_operation(
                _orig_rename, src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd
            )
        return _broker_call_native_host_operation(_orig_rename, src, dst)

    def _brokered_os_replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
        from_path = _broker_abs_path(src, dir_fd=src_dir_fd)
        to_path = _broker_abs_path(dst, dir_fd=dst_dir_fd)
        if from_path and to_path and _broker_request_host_operation(
            "rename", from_path, **{"from": from_path, "to": to_path}
        ):
            return None
        if src_dir_fd is not None or dst_dir_fd is not None:
            return _broker_call_native_host_operation(
                _orig_replace, src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd
            )
        return _broker_call_native_host_operation(_orig_replace, src, dst)

    def _brokered_os_chmod(path, mode, *, dir_fd=None, follow_symlinks=True):
        abs_path = _broker_abs_path(path, dir_fd=dir_fd)
        if abs_path and isinstance(mode, int) and follow_symlinks and _broker_request_host_operation(
            "chmod", abs_path, path=abs_path, mode=mode
        ):
            return None
        if dir_fd is not None:
            return _broker_call_native_host_operation(
                _orig_chmod, path, mode, dir_fd=dir_fd, follow_symlinks=follow_symlinks
            )
        return _broker_call_native_host_operation(
            _orig_chmod, path, mode, follow_symlinks=follow_symlinks
        )

    def _brokered_os_link(src, dst, *, src_dir_fd=None, dst_dir_fd=None, follow_symlinks=True):
        from_path = _broker_abs_path(src, dir_fd=src_dir_fd)
        to_path = _broker_abs_path(dst, dir_fd=dst_dir_fd)
        should_broker = follow_symlinks and from_path and to_path
        try:
            should_broker = should_broker and not os.path.islink(from_path)
        except Exception:
            should_broker = False
        if should_broker and _broker_request_host_operation(
            "link", from_path, **{"from": from_path, "to": to_path, "symbolic": False}
        ):
            return None
        if src_dir_fd is not None or dst_dir_fd is not None:
            return _broker_call_native_host_operation(
                _orig_link, src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks
            )
        return _broker_call_native_host_operation(
            _orig_link, src, dst, follow_symlinks=follow_symlinks
        )

    def _brokered_os_symlink(src, dst, target_is_directory=False, *, dir_fd=None):
        source = None
        try:
            source = os.fspath(src)
            if isinstance(source, bytes):
                source = os.fsdecode(source)
        except (TypeError, UnicodeError):
            source = None
        to_path = _broker_abs_path(dst, dir_fd=dir_fd)
        if source and to_path and _broker_request_host_operation(
            "link", to_path, **{"from": source, "to": to_path, "symbolic": True}
        ):
            return None
        if dir_fd is not None:
            return _broker_call_native_host_operation(
                _orig_symlink, src, dst, target_is_directory, dir_fd=dir_fd
            )
        return _broker_call_native_host_operation(
            _orig_symlink, src, dst, target_is_directory
        )

    def _brokered_shutil_copyfile(src, dst, *, follow_symlinks=True):
        from_path = _broker_abs_path(src)
        to_path = _broker_abs_path(dst)
        if follow_symlinks and from_path and to_path and _broker_request_host_operation(
            "copy", from_path, **{"from": from_path, "to": to_path, "recursive": False}
        ):
            return dst
        return _broker_call_native_host_operation(
            _orig_shutil_copyfile, src, dst, follow_symlinks=follow_symlinks
        )

    def _brokered_shutil_copytree(
        src,
        dst,
        symlinks=False,
        ignore=None,
        copy_function=_COPYTREE_DEFAULT,
        ignore_dangling_symlinks=False,
        dirs_exist_ok=False,
    ):
        native_copy_function = (
            _orig_shutil_copy2
            if copy_function is _COPYTREE_DEFAULT
            else copy_function
        )
        can_broker = (
            symlinks is False
            and ignore is None
            and native_copy_function is _orig_shutil_copy2
            and ignore_dangling_symlinks is False
            and dirs_exist_ok is False
        )
        from_path = _broker_abs_path(src) if can_broker else None
        to_path = _broker_abs_path(dst) if can_broker else None
        if from_path and to_path and _broker_request_host_operation(
            "copy", from_path, **{"from": from_path, "to": to_path, "recursive": True}
        ):
            return dst
        return _broker_call_native_host_operation(
            _orig_shutil_copytree,
            src,
            dst,
            symlinks=symlinks,
            ignore=ignore,
            copy_function=native_copy_function,
            ignore_dangling_symlinks=ignore_dangling_symlinks,
            dirs_exist_ok=dirs_exist_ok,
        )

    def _brokered_path_mkdir(self, mode=0o777, parents=False, exist_ok=False):
        abs_path = _broker_abs_path(self)
        if abs_path and isinstance(mode, int):
            if not exist_ok and os.path.exists(abs_path):
                return _broker_call_native_host_operation(
                    _orig_path_mkdir, self, mode=mode, parents=parents, exist_ok=exist_ok
                )
            if _broker_request_host_operation(
                "mkdir", abs_path, path=abs_path, recursive=parents, mode=mode
            ):
                return None
        return _broker_call_native_host_operation(
            _orig_path_mkdir, self, mode=mode, parents=parents, exist_ok=exist_ok
        )

    def _brokered_path_touch(self, mode=0o666, exist_ok=True):
        abs_path = _broker_abs_path(self)
        can_broker = abs_path and mode == 0o666 and (exist_ok or not os.path.exists(abs_path))
        if can_broker and _broker_request_host_operation("touch", abs_path, path=abs_path):
            return None
        return _broker_call_native_host_operation(
            _orig_path_touch, self, mode=mode, exist_ok=exist_ok
        )

    def _path_for_compare(path):
        return os.path.normcase(os.path.realpath(os.path.abspath(path)))

    def _load_bulk_replay_paths():
        replay_file = os.environ.get("CODEBUDDY_SAFE_DELETE_BULK_REPLAY_FILE")
        if not replay_file:
            return set()
        try:
            with _orig_builtin_open(replay_file, "r", encoding="utf-8") as f:
                paths = json.load(f)
            if not isinstance(paths, list):
                return set()
            return {
                _path_for_compare(path)
                for path in paths
                if isinstance(path, str)
            }
        except Exception:
            return set()

    _bulk_replay_paths = _load_bulk_replay_paths()

    def _was_deleted_before_bulk_replay(abs_path):
        return _path_for_compare(abs_path) in _bulk_replay_paths

    def _is_usable_temp_root(path):
        try:
            root = _path_for_compare(path)
            if os.path.dirname(root) == root:
                return False
            return os.path.isdir(root)
        except Exception:
            return False

    def _build_os_tmp_dirs():
        candidates = [
            tempfile.gettempdir(),
        ]
        if sys.platform != "win32":
            candidates.append("/tmp")
            candidates.append("/private/tmp")

        roots = []
        seen = set()
        for candidate in candidates:
            if not candidate or not _is_usable_temp_root(candidate):
                continue
            root = _path_for_compare(candidate)
            if root in seen:
                continue
            seen.add(root)
            roots.append(root)
        return roots

    _os_tmp_dirs = _build_os_tmp_dirs()

    def _record_report(operation, abs_path):
        if not _report_path:
            return
        try:
            with _orig_builtin_open(_report_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "operation": operation,
                    "runtime": "python",
                    "path": abs_path,
                    "timestamp": int(time.time() * 1000),
                }, ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception:
            pass

    def _exit_bulk_guard_control(message):
        try:
            sys.stderr.write(message)
            if not message.endswith("\n"):
                sys.stderr.write("\n")
            sys.stderr.flush()
        finally:
            raise SystemExit(1)

    def _check_bulk_delete_guard(abs_path):
        guard_path = os.environ.get("CODEBUDDY_SAFE_DELETE_BULK_GUARD")
        node_bin = os.environ.get("CODEBUDDY_NODE_BIN")
        if not os.environ.get("CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR") \
                or not os.environ.get("CODEBUDDY_TOOL_CALL_ID"):
            return
        if not guard_path or not node_bin or not os.path.isfile(guard_path):
            _exit_bulk_guard_control(
                "[safe-delete][SAFE_DELETE_BULK_GUARD_ERROR] msg=helper-unavailable guard=%s"
                % (guard_path or "unset")
            )
        env = dict(os.environ)
        env["NODE_OPTIONS"] = ""
        if env.get("CODEBUDDY_NODE_RUN_AS_NODE") == "1":
            env["ELECTRON_RUN_AS_NODE"] = "1"
        try:
            result = subprocess.run(
                [node_bin, guard_path, "check", "--target", abs_path],
                capture_output=True, text=True, timeout=10, env=env
            )
        except Exception as e:
            _exit_bulk_guard_control(
                "[safe-delete][SAFE_DELETE_BULK_GUARD_ERROR] %s" % e
            )
        if result.returncode != 0:
            _exit_bulk_guard_control(
                result.stderr.strip()
                or "[safe-delete][SAFE_DELETE_BULK_GUARD_ERROR] exit %d" % result.returncode
            )

    # -----------------------------------------------------------------------
    # genie-trash native binary 支持（优先路径，不可用自动降级）
    # 优先使用 GENIE_TRASH_DIR 环境变量（由 buildSafeDeleteEnv() 注入），
    # 解决打包后 extraResources 与 shim 不共父目录的路径错位问题。
    # -----------------------------------------------------------------------

    def _get_trash_bin():
        system = "win32" if sys.platform == "win32" else platform.system().lower()
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            arch = "arm64"
        elif machine in ("x86_64", "amd64"):
            arch = "x64"
        else:
            arch = machine
        ext = ".exe" if sys.platform == "win32" else ""
        file_name = "%s-%s%s" % (system, arch, ext)
        trash_dir = os.environ.get("GENIE_TRASH_DIR")
        if trash_dir:
            return os.path.join(trash_dir, file_name)
        shim_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(shim_dir, "..", "genie-trash", file_name)

    _trash_bin_available = None  # None=未探测, True=可用, False=不可用

    def _try_trash_via_binary(abs_path):
        global _trash_bin_available
        if _trash_bin_available is False:
            return False
        existed = os.path.lexists(abs_path)
        try:
            result = subprocess.run(
                [_get_trash_bin(), abs_path],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                _trash_bin_available = True
                return True
            # Windows 上 trash crate 的 IFileOperation::GetAnyOperationsAborted 会误报 true，
            # 但 PerformOperations 实际已删除文件。以文件系统事实为准：调用前在、调用后没了 = 删除成功。
            # 仅 Windows 启用：根因是 Win32 独有 API，非 Windows 上失败原因未知，不应静默吞掉。
            # 参考 https://github.com/maxkagamine/wsl-tools 的 recycle_bin.rs
            if sys.platform == "win32" and existed and not os.path.lexists(abs_path):
                _trash_bin_available = True
                return True
            # binary 已启动但对该路径失败：抛错，不降级真删
            raise OSError(
                "[safe-delete] 操作失败: %s"
                % (result.stderr.strip() or "exit %d" % result.returncode)
            )
        except FileNotFoundError:
            _trash_bin_available = False  # binary 不存在，进程生命周期内不会凭空出现
            return False
        except PermissionError:
            # 不缓存：权限问题可能是临时状态（如 chmod +x 后恢复）
            return False
        except subprocess.TimeoutExpired:
            # 与 exit 1 同样检查：超时也可能文件已被删除
            if sys.platform == "win32" and existed and not os.path.lexists(abs_path):
                _trash_bin_available = True
                return True
            return False  # 超时是临时问题，不永久禁用 native binary
        except OSError:
            raise
        except Exception:
            pass
        _trash_bin_available = False
        return False

    # -----------------------------------------------------------------------
    # 核心：移入回收站。
    # 返回 True=已移入回收站；抛错=fail-closed，调用方不得真删。
    # -----------------------------------------------------------------------

    def _try_broker_delete(abs_path, recursive=False, force=False):
        if not _broker_host_ops_enabled():
            return "unavailable"
        try:
            if _broker_request_host_operation(
                "delete",
                abs_path,
                path=abs_path,
                deleteMode="trash",
                recursive=bool(recursive),
                force=bool(force),
            ):
                return "ok"
            return "unavailable"
        except Exception as error:
            # 宿主已接单但执行失败（备份失败、ENOTEMPTY、EBUSY 等）：这不是「broker
            # 不可用」，不能回落沙箱再删一次——那会绕开备份并可能重复删除。
            # PermissionError 是 OSError 的子类，必须先按标记判定，避免 errno 被吞掉。
            if getattr(error, "_codebuddy_broker_host_op_error", False):
                raise
            if isinstance(error, PermissionError):
                return "denied"
            return "unavailable"

    def _emit_safe_delete_fail_closed(abs_path, reason, detail=None):
        payload = {
            "target": abs_path,
            "reason": reason,
        }
        if detail:
            payload["detail"] = detail
        message = (
            "[safe-delete][SAFE_DELETE_FAIL_CLOSED] "
            + json.dumps(payload, ensure_ascii=False)
        )
        try:
            sys.stderr.write(message + "\n")
            sys.stderr.flush()
        except Exception:
            pass

    def _try_trash(abs_path, recursive=False, force=False):
        _check_bulk_delete_guard(abs_path)

        broker_result = _try_broker_delete(abs_path, recursive=recursive, force=force)
        if broker_result == "ok":
            return True
        if broker_result == "denied":
            raise PermissionError(
                "[safe-delete] broker denied delete: path=%s" % abs_path
            )

        # Windows 沙箱且开启文件备份：普通文件交给 tsbx+Center 决定是否进回收站（本轮新建的
        # 直接删）。原生删除失败（如 Center 拒绝）时继续走 genie-trash，保留审批与 fail-closed。
        if sys.platform == "win32" and _IN_SANDBOX \
                and os.environ.get("CODEBUDDY_FILE_BACKUP_ENABLED") == "1":
            st = _safe_lstat(abs_path)
            if st and stat.S_ISREG(st.st_mode):
                try:
                    _orig_unlink(abs_path)
                    _record_report("native-delete", abs_path)
                    return True
                except OSError:
                    pass

        try:
            if _try_trash_via_binary(abs_path):
                _record_report("trash", abs_path)
                return True
            _platform_trash(abs_path)
        except Exception as e:
            _emit_safe_delete_fail_closed(abs_path, "trash-failed", str(e))
            raise
        _record_report("trash", abs_path)
        return True

    def _safe_lstat(abs_path):
        try:
            return os.lstat(abs_path)
        except OSError as e:
            if e.errno == errno.ENOENT:
                return None
            # EACCES / ELOOP 等错误：让调用方回退原生
            return False  # 与 None 区分开

    def _is_dir_empty(abs_path):
        try:
            return len(os.listdir(abs_path)) == 0
        except OSError:
            return False

    def _is_under_root(root, abs_path):
        try:
            target = _path_for_compare(os.fsdecode(abs_path))
            root_path = _path_for_compare(root)
            rel = os.path.relpath(target, root_path)
        except (TypeError, UnicodeError, ValueError):
            return False
        return rel not in ("", ".") and rel != ".." and not rel.startswith(".." + os.sep) and not os.path.isabs(rel)

    def _is_under_os_tmp_dir(abs_path):
        for tmp_dir in _os_tmp_dirs:
            if _is_under_root(tmp_dir, abs_path):
                return True
        return False

    def _is_pip_site_packages_temp_dir(abs_path):
        try:
            target = _path_for_compare(os.fsdecode(abs_path))
        except (TypeError, UnicodeError):
            return False
        parts = target.split(os.sep)
        for index, part in enumerate(parts[:-1]):
            if part not in ("site-packages", "dist-packages"):
                continue
            backup_root = parts[index + 1]
            if backup_root.startswith("~") or backup_root.startswith("accesstest_deleteme"):
                return True
        return False

    def _is_workbuddy_managed_pip_site_packages_path(abs_path):
        config_dir = os.environ.get("WORKBUDDY_CONFIG_DIR")
        if not config_dir:
            return False
        managed_env = _path_for_compare(os.path.join(
            config_dir, "binaries", "python", "envs", "default"
        ))
        try:
            if _path_for_compare(sys.prefix) != managed_env:
                return False
            pip_entrypoint = _path_for_compare(os.fsdecode(sys.argv[0]))
            expected_pip = os.path.join(
                managed_env,
                "Scripts" if sys.platform == "win32" else "bin",
                "pip.exe" if sys.platform == "win32" else "pip",
            )
            expected_pip = _path_for_compare(expected_pip)
            if sys.platform == "win32":
                if pip_entrypoint.endswith(".exe"):
                    pip_entrypoint = pip_entrypoint[:-4]
                expected_pip = expected_pip[:-4]
            if pip_entrypoint != expected_pip:
                return False
            target = _path_for_compare(os.fsdecode(abs_path))
            rel = os.path.relpath(target, managed_env)
        except (IndexError, TypeError, UnicodeError, ValueError):
            return False
        if rel in ("", ".") or rel == ".." or rel.startswith(".." + os.sep) \
                or os.path.isabs(rel):
            return False
        parts = rel.split(os.sep)
        if sys.platform == "win32":
            return len(parts) >= 3 \
                and parts[0] == "lib" \
                and parts[1] == "site-packages"
        return len(parts) >= 4 \
            and parts[0] == "lib" \
            and parts[1].startswith("python") \
            and parts[2] in ("site-packages", "dist-packages")

    def _should_bypass_safe_delete(abs_path):
        return _is_under_os_tmp_dir(abs_path) \
            or _is_pip_site_packages_temp_dir(abs_path) \
            or _is_workbuddy_managed_pip_site_packages_path(abs_path)

    # -----------------------------------------------------------------------
    # 包装：os.remove / os.unlink （文件，不能是目录）
    # -----------------------------------------------------------------------

    def _safe_remove(path, *, dir_fd=None):
        # dir_fd 不为 None → 走原生（无法解析到 abs_path）
        if dir_fd is not None:
            return _orig_remove(path, dir_fd=dir_fd)
        abs_path = os.path.abspath(os.fspath(path))
        if _should_bypass_safe_delete(abs_path):
            return _orig_remove(path)
        st = _safe_lstat(abs_path)
        if not st:
            if st is None and _was_deleted_before_bulk_replay(abs_path):
                return None
            return _orig_remove(path)  # ENOENT / stat 错误 → 让原生抛
        if stat.S_ISDIR(st.st_mode):
            return _orig_remove(path)  # 让原生抛 EISDIR / EPERM
        _try_trash(abs_path)

    def _emit_sandbox_delete_denial(path, dir_fd=None):
        try:
            raw_path = os.fsdecode(os.fspath(path))
            if dir_fd is not None and not os.path.isabs(raw_path):
                import fcntl
                dir_path = fcntl.fcntl(dir_fd, 50, b"\0" * 1024).split(b"\0", 1)[0]
                raw_path = os.path.join(os.fsdecode(dir_path), raw_path)
            abs_path = os.path.abspath(raw_path)
            sys.stderr.write("python: %s: Operation not permitted\n" % abs_path)
            sys.stderr.flush()
        except Exception:
            pass

    def _native_delete_with_sandbox_diagnostic(delete_fn, path, dir_fd=None):
        try:
            if dir_fd is not None:
                return delete_fn(path, dir_fd=dir_fd)
            return delete_fn(path)
        except PermissionError as e:
            if e.errno == errno.EPERM and not getattr(
                    e, "_codebuddy_delete_diagnostic_emitted", False):
                _emit_sandbox_delete_denial(path, dir_fd)
                e._codebuddy_delete_diagnostic_emitted = True
            raise

    def _native_remove_with_sandbox_diagnostic(path, *, dir_fd=None):
        return _native_delete_with_sandbox_diagnostic(_orig_remove, path, dir_fd)

    def _native_unlink_with_sandbox_diagnostic(path, *, dir_fd=None):
        return _native_delete_with_sandbox_diagnostic(_orig_unlink, path, dir_fd)

    def _native_rmdir_with_sandbox_diagnostic(path, *, dir_fd=None):
        return _native_delete_with_sandbox_diagnostic(_orig_rmdir, path, dir_fd)

    def _native_path_rmdir_with_sandbox_diagnostic(self):
        return _native_delete_with_sandbox_diagnostic(_orig_path_rmdir, self)

    # -----------------------------------------------------------------------
    # 包装：os.rmdir（必须是空目录）
    # -----------------------------------------------------------------------

    def _safe_rmdir(path, *, dir_fd=None):
        if dir_fd is not None:
            return _orig_rmdir(path, dir_fd=dir_fd)
        abs_path = os.path.abspath(os.fspath(path))
        if _should_bypass_safe_delete(abs_path):
            return _orig_rmdir(path)
        st = _safe_lstat(abs_path)
        if not st:
            if st is None and _was_deleted_before_bulk_replay(abs_path):
                return None
            return _orig_rmdir(path)  # ENOENT / stat 错误
        if not stat.S_ISDIR(st.st_mode):
            return _orig_rmdir(path)  # ENOTDIR
        if not _is_dir_empty(abs_path):
            return _orig_rmdir(path)  # ENOTEMPTY
        _try_trash(abs_path)

    # -----------------------------------------------------------------------
    # 包装：shutil.rmtree（递归删目录）
    # -----------------------------------------------------------------------

    def _safe_shutil_rmtree(path, ignore_errors=False, onerror=None, **kwargs):
        # Python 3.12+ 引入 onexc，3.14+ 还有 dir_fd——一并 forward 给原生
        try:
            abs_path = os.path.abspath(os.fspath(path))
        except TypeError:
            return _orig_shutil_rmtree(
                path, ignore_errors=ignore_errors, onerror=onerror, **kwargs
            )

        if _should_bypass_safe_delete(abs_path):
            return _orig_shutil_rmtree(
                path, ignore_errors=ignore_errors, onerror=onerror, **kwargs
            )

        st = _safe_lstat(abs_path)
        if not st:
            if st is None and _was_deleted_before_bulk_replay(abs_path):
                return None
            return _orig_shutil_rmtree(
                path, ignore_errors=ignore_errors, onerror=onerror, **kwargs
            )
        if not stat.S_ISDIR(st.st_mode):
            # 不是目录 → 让原生处理（rmtree 会抛 NotADirectoryError）
            return _orig_shutil_rmtree(
                path, ignore_errors=ignore_errors, onerror=onerror, **kwargs
            )

        try:
            _try_trash(abs_path, recursive=True)
        except Exception as e:
            if ignore_errors:
                return
            if onerror is not None:
                onerror(_safe_shutil_rmtree, path, sys.exc_info())
                return
            raise

    # -----------------------------------------------------------------------
    # 包装：pathlib.Path.unlink / rmdir
    # -----------------------------------------------------------------------

    def _safe_path_unlink(self, missing_ok=False):
        abs_path = os.path.abspath(str(self))
        if _should_bypass_safe_delete(abs_path):
            return _orig_path_unlink(self, missing_ok=missing_ok)
        st = _safe_lstat(abs_path)
        if not st:
            if st is None and _was_deleted_before_bulk_replay(abs_path):
                return None
            if st is None and missing_ok:
                return None
            return _orig_path_unlink(self, missing_ok=missing_ok)  # 让原生抛
        if stat.S_ISDIR(st.st_mode):
            return _orig_path_unlink(self, missing_ok=missing_ok)  # 抛 IsADirectoryError
        _try_trash(abs_path)

    def _safe_path_rmdir(self):
        abs_path = os.path.abspath(str(self))
        if _should_bypass_safe_delete(abs_path):
            return _orig_path_rmdir(self)
        st = _safe_lstat(abs_path)
        if not st:
            if st is None and _was_deleted_before_bulk_replay(abs_path):
                return None
            return _orig_path_rmdir(self)  # ENOENT / stat 错误 → 让原生抛
        if not stat.S_ISDIR(st.st_mode):
            return _orig_path_rmdir(self)  # 抛 NotADirectoryError
        if not _is_dir_empty(abs_path):
            return _orig_path_rmdir(self)  # 抛 OSError(ENOTEMPTY)
        _try_trash(abs_path)

    # -----------------------------------------------------------------------
    # 安装 patch
    # -----------------------------------------------------------------------

    if _broker_enabled():
        builtins.open = _brokered_builtin_open
        io.open = _brokered_io_open
        os.open = _brokered_os_open

    if _broker_host_ops_enabled():
        os.mkdir = _brokered_os_mkdir
        os.makedirs = _brokered_os_makedirs
        os.rename = _brokered_os_rename
        os.replace = _brokered_os_replace
        os.chmod = _brokered_os_chmod
        os.link = _brokered_os_link
        os.symlink = _brokered_os_symlink
        shutil.copyfile = _brokered_shutil_copyfile
        shutil.copytree = _brokered_shutil_copytree
        pathlib.Path.mkdir = _brokered_path_mkdir
        pathlib.Path.touch = _brokered_path_touch

    if _SAFE_DELETE_ENABLED:
        os.remove = _safe_remove
        os.unlink = _safe_remove  # CPython 里 os.unlink is os.remove，显式 patch 兼容其它实现
        os.rmdir = _safe_rmdir
        shutil.rmtree = _safe_shutil_rmtree
        pathlib.Path.unlink = _safe_path_unlink
        pathlib.Path.rmdir = _safe_path_rmdir
    elif _broker_enabled():
        os.remove = _native_remove_with_sandbox_diagnostic
        os.unlink = _native_unlink_with_sandbox_diagnostic
        os.rmdir = _native_rmdir_with_sandbox_diagnostic
        pathlib.Path.rmdir = _native_path_rmdir_with_sandbox_diagnostic
