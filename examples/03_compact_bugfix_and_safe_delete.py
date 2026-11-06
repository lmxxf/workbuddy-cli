#!/usr/bin/env python3
"""
Example 03: 3-Stage Context Compactor Bugfix (`already completed` Hypnosis) & `sitecustomize.py` Safe-Delete
============================================================================================================
Demonstrates:
1. `HistoryEngineeringCompactor`: Deterministic 0-LLM history pruning (strips `function_call_result`,
   replaces `content`/`widget_code`/`new_string` with `<omitted>`, checks 15% sufficiency threshold).
2. Bugfix for Tencent WorkBuddyAI 5.9.4's `/compact` Hypnosis Bug:
   - Original `context-summary-prompt.txt` hardcoded:
     `All tasks described below are already completed. **DO NOT re-run, re-do or re-execute any of the tasks mentioned!**`
   - When triggered mid-task, the successor agent gets hypnotized into refusing unfinished work!
   - `workbuddy-cli`'s `FIXED_CONTEXT_SUMMARY_PROMPT` cleanly separates `Completed Tasks` from
     `Pending Tasks & Current Work`.
3. Process-level Safe-Delete (`SafeTrashInterceptor` & `sitecustomize.py` monkey-patch):
   - Intercepts `os.remove`, `shutil.rmtree`, `Path.unlink` in child Python processes and redirects
     deleted files into the system Trash (`files/` + `.trashinfo`) with Fail-Closed protection.
"""

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workbuddy_cli.compactor import (
    BUGGY_TENCENT_HEADER,
    FIXED_CONTEXT_SUMMARY_PROMPT,
    HistoryEngineeringCompactor,
    ThreeStageCompactor,
)
from workbuddy_cli.tools.safe_shell import SafeTrashInterceptor


def main() -> None:
    print("=" * 88)
    print("🛡️  [03] WorkBuddy-CLI: 15% 零 LLM 工程压缩 + 修复 `/compact` 假完工催眠乌龙 + 进程级防删库")
    print("=" * 88)

    # 1. Build a multi-turn agent conversation with heavy tool call payloads and unfinished work
    messages = [
        {
            "role": "user",
            "content": "<user_query>\n重构整个项目的数据库层（共 3 个模块：连接池、ORM 映射、迁移脚本），目前先写第 1 个模块。\n</user_query>",
        },
        {
            "role": "assistant",
            "content": "好的，我现在开始编写模块 1（连接池 `db_pool.py`），模块 2 和模块 3 处于待执行状态。",
            "tool_calls": [
                {
                    "function": {
                        "name": "write_file",
                        "arguments": {
                            "path": "src/db_pool.py",
                            "content": "class ConnectionPool:\n" + ("    # heavy implementation line\n" * 120),
                        },
                    }
                }
            ],
        },
        {
            "role": "tool",
            "content": "Successfully wrote 121 lines to src/db_pool.py\n" + ("Verbose tool log...\n" * 80),
        },
    ]

    # 2. Run Stage-1 HistoryEngineeringCompactor (0 LLM cost)
    compactor = ThreeStageCompactor(max_context_tokens=300000, sufficiency_pct=0.15)
    res_eng = compactor.run_compact(messages, engineering_only=True)
    print("\n✂️  [1] 第一阶段 `HistoryEngineeringCompactor`（零 LLM 规则剪刀）实测：")
    print(f"  - 原始对话估算 Token: {res_eng['original_tokens']} tokens")
    print(f"  - 规则剥离 `tool` 结果与大参数 `<omitted>` 后: {res_eng['compacted_tokens']} tokens")
    print(f"  - 15% 免 LLM 阈值线 (`budget * 0.15`): {res_eng['sufficiency_budget']:,} tokens -> 触发策略: `{res_eng['strategy']}`")
    assert "<omitted>" in res_eng["summary_text"]

    # 3. Contrast Tencent's Buggy Header vs Our Fixed Prompt
    print("\n🐛 [2] 腾讯原版 `context-summary-prompt.txt` 假完工催眠乌龙 vs `workbuddy-cli` 修复版对比：")
    print("  ❌ [原版 WorkBuddy 5.9.4 第 8-9 行硬编码死令]：")
    for line in BUGGY_TENCENT_HEADER.splitlines():
        print(f"     {line}")
    print("     -> 后果：任务才干了 1/3 触发 `/compact`，继任 Agent 读到这句直接摆烂宣称『全部已完成，严禁重跑』！")

    print("\n  ✅ [`workbuddy-cli` 修复版 `FIXED_CONTEXT_SUMMARY_PROMPT` 核心指令]：")
    for line in FIXED_CONTEXT_SUMMARY_PROMPT.splitlines():
        if "DO continue" in line or "5. Completed" in line or "6. Pending" in line:
            print(f"     {line}")
    assert "already completed" not in FIXED_CONTEXT_SUMMARY_PROMPT
    assert "Pending Tasks & Current Work" in FIXED_CONTEXT_SUMMARY_PROMPT

    # 4. Test SafeTrashInterceptor & sitecustomize.py subprocess monkey-patch
    print("\n🗑️  [3] `sitecustomize.py` 进程级防删库猴子补丁实测（劫持 `os.remove` / `shutil.rmtree` / `Path.unlink`）：")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        trash_root = tmp_path / "Trash"
        workspace = tmp_path / "work"
        workspace.mkdir(parents=True, exist_ok=True)

        victim_file = workspace / "critical_customer_database.sqlite"
        victim_dir = workspace / "important_configs"
        victim_dir.mkdir()
        victim_file.write_text("SELECT * FROM millionaire_accounts;", encoding="utf-8")
        (victim_dir / "secret.yaml").write_text("api_key: sk-live-99999", encoding="utf-8")

        interceptor = SafeTrashInterceptor(trash_dir=trash_root)

        # Spawn a real child python3 process that tries to permanently delete both via os.remove & shutil.rmtree
        rogue_script = (
            "import os, shutil\n"
            f"os.remove({repr(str(victim_file))})\n"
            f"shutil.rmtree({repr(str(victim_dir))})\n"
            "print('Child process executed os.remove() and shutil.rmtree()!')\n"
        )
        run_res = interceptor.run_sandboxed_python(rogue_script, cwd=workspace)
        print(f"  - 子进程输出: {run_res['stdout'].strip()}")
        print(f"  - 原路径文件是否已移除: victim_file.exists()={victim_file.exists()}, victim_dir.exists()={victim_dir.exists()}")
        print(f"  - 回收站 `Trash/files/` 成功截获保命文件 ({len(run_res['trash_files'])} 项):")
        for tf in run_res["trash_files"]:
            print(f"    🔒 {Path(tf).name}")

        # Also verify No-Go Zone blocking on ~/Desktop
        desktop_block = interceptor.safe_delete(Path.home() / "Desktop", allow_personal_dir=False)
        print(f"  - 禁区拦截测试 (`~/Desktop`): status=`{desktop_block['status']}` | {desktop_block['warning']}")

        assert not victim_file.exists()
        assert len(run_res["trash_files"]) == 2
        assert desktop_block["status"] == "blocked"

    print("\n🎉 Example 03 全部断言通过！")


if __name__ == "__main__":
    main()
