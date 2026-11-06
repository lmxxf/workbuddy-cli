"""
Safe Shell, Trash-Intercepted File Deletion (`sitecustomize_safe_delete.py`),
8 Personal Files Safety Rules, and 3-Phase Document Backup Transaction (`DocumentBackup`).
"""

import datetime
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..config import ASSETS_DIR


HIGH_RISK_WARNING_BANNER = "⚠️ 此操作非常危险，可能导致不可逆的数据丢失！"

NO_GO_ZONES = (
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path("/"),
    Path("/System"),
    Path("/etc"),
    Path.home() / ".config",
    Path.home() / ".ssh",
)


class SafeTrashInterceptor:
    """
    Provides deterministic Trash redirection for file deletions (`safe-delete`)
    and injects WorkBuddy's `sitecustomize_safe_delete.py` shim into subprocess `PYTHONPATH`.
    """

    def __init__(self, trash_dir: Optional[Path] = None):
        default_trash = Path.home() / ".local" / "share" / "Trash"
        self.trash_dir = Path(trash_dir) if trash_dir else default_trash
        self.files_dir = self.trash_dir / "files"
        self.info_dir = self.trash_dir / "info"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.info_dir.mkdir(parents=True, exist_ok=True)

    def is_no_go_zone(self, target: Path) -> bool:
        resolved = target.resolve()
        if resolved == Path.home().resolve():
            return True
        for zone in NO_GO_ZONES:
            try:
                z_res = zone.resolve()
                if resolved == z_res or z_res in resolved.parents:
                    return True
            except Exception:
                continue
        return False

    def safe_delete(self, target_path: str | Path, allow_personal_dir: bool = False) -> Dict[str, Any]:
        """
        Intercepts deletion and moves the file/directory into the freedesktop Trash specification
        (`files/` + `.trashinfo`) instead of unlinking permanently.
        """
        target = Path(target_path).resolve()
        if not allow_personal_dir and self.is_no_go_zone(target):
            return {
                "status": "blocked",
                "warning": HIGH_RISK_WARNING_BANNER,
                "reason": f"[SAFE_DELETE_NO_GO_ZONE] Refusing destructive operation on protected path: {target}",
                "path": str(target),
            }

        if not target.exists():
            return {"status": "skipped", "reason": "not_found", "path": str(target)}

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        trash_name = f"{target.name}.{stamp}"
        dest_path = self.files_dir / trash_name
        info_path = self.info_dir / f"{trash_name}.trashinfo"

        deletion_date = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        trashinfo_content = (
            "[Trash Info]\n"
            f"Path={target}\n"
            f"DeletionDate={deletion_date}\n"
        )

        try:
            shutil.move(str(target), str(dest_path))
            info_path.write_text(trashinfo_content, encoding="utf-8")
            return {
                "status": "trashed",
                "original_path": str(target),
                "trash_path": str(dest_path),
                "trashinfo_path": str(info_path),
                "warning": HIGH_RISK_WARNING_BANNER,
            }
        except Exception as exc:
            raise RuntimeError(f"[SAFE_DELETE_FAIL_CLOSED] Failed to move {target} to Trash: {exc}") from exc

    def create_python_shim_dir(self, base_dir: Optional[Path] = None) -> Path:
        """
        Creates a directory containing `sitecustomize.py` that monkey-patches
        `os.remove`, `os.unlink`, `os.rmdir`, `shutil.rmtree`, `Path.unlink`, and `Path.rmdir`
        to redirect deletions into `self.trash_dir` (Fail-Closed).
        """
        shim_dir = Path(base_dir) if base_dir else (self.trash_dir / "_python_shim")
        shim_dir.mkdir(parents=True, exist_ok=True)
        sitecustomize_file = shim_dir / "sitecustomize.py"

        shim_code = f'''# Auto-generated WorkBuddy Safe-Delete Monkey-Patch Shim
import datetime
import os
import pathlib
import shutil

_TRASH_FILES = pathlib.Path({repr(str(self.files_dir))})
_TRASH_INFO = pathlib.Path({repr(str(self.info_dir))})
_TRASH_FILES.mkdir(parents=True, exist_ok=True)
_TRASH_INFO.mkdir(parents=True, exist_ok=True)

_ORIG_REMOVE = os.remove
_ORIG_UNLINK = os.unlink
_ORIG_RMDIR = os.rmdir
_ORIG_RMTREE = shutil.rmtree
_ORIG_MOVE = shutil.move


def _move_to_trash(path_obj):
    p = pathlib.Path(path_obj).resolve()
    if not p.exists():
        return
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name = f"{{p.name}}.{{stamp}}"
    dest = _TRASH_FILES / name
    info = _TRASH_INFO / f"{{name}}.trashinfo"
    _ORIG_MOVE(str(p), str(dest))
    info.write_text(
        f"[Trash Info]\\nPath={{p}}\\nDeletionDate={{datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}}\\n",
        encoding="utf-8",
    )


def _safe_remove(path, *args, **kwargs):
    _move_to_trash(path)


def _safe_rmtree(path, *args, **kwargs):
    _move_to_trash(path)


os.remove = _safe_remove
os.unlink = _safe_remove
os.rmdir = _safe_remove
shutil.rmtree = _safe_rmtree
pathlib.Path.unlink = lambda self, missing_ok=False: _move_to_trash(self)
pathlib.Path.rmdir = lambda self: _move_to_trash(self)
'''
        sitecustomize_file.write_text(shim_code, encoding="utf-8")
        return shim_dir

    def run_sandboxed_python(self, code: str, cwd: Optional[Path] = None, timeout: int = 30) -> Dict[str, Any]:
        """Runs a Python snippet with `sitecustomize.py` prepended to `PYTHONPATH`."""
        shim_dir = self.create_python_shim_dir()
        env = dict(os.environ)
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{shim_dir}{os.pathsep}{existing_pp}" if existing_pp else str(shim_dir)

        proc = subprocess.run(
            ["python3", "-c", code],
            cwd=str(cwd or Path.cwd()),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "shim_dir": str(shim_dir),
            "trash_files": [str(p) for p in sorted(self.files_dir.iterdir())],
        }


class DocumentBackupTransaction:
    """
    Replicates WorkBuddy's 3-phase Office file edit transaction (`edsdk.py`):
    `("ipc", "edit") -> ("ipc", "prepare", save-ticket snapshot) -> ("sdk", "save_file") -> ("ipc", "complete" / "cancel")`
    """

    def __init__(self, backup_root: Optional[Path] = None):
        self.backup_root = Path(backup_root) if backup_root else (Path(tempfile.gettempdir()) / "workbuddy_doc_backups")
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.tickets: Dict[str, Path] = {}

    def prepare(self, file_path: str | Path) -> str:
        target = Path(file_path).resolve()
        ticket = f"ticket_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        if target.exists():
            snap = self.backup_root / f"{ticket}_{target.name}"
            shutil.copy2(str(target), str(snap))
            self.tickets[ticket] = snap
        return ticket

    def rollback(self, ticket: str, file_path: str | Path) -> bool:
        snap = self.tickets.get(ticket)
        target = Path(file_path).resolve()
        if snap and snap.exists():
            shutil.copy2(str(snap), str(target))
            return True
        return False
