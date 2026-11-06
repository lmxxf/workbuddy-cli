#!/usr/bin/env python3
"""
Example 01: Sarcastic Soul, Native AGENTS.md Injection & 33K-to-2.2K Token Footprint Showdown
=============================================================================================
Demonstrates:
1. Tencent WorkBuddyAI Desktop's 32,739-token "Hello" startup bloat (`full` profile + 100+ schemas)
   vs. `workbuddy-cli` Lean Profile (~2.2K tokens on-demand + dynamic `0.8*Cosine + 0.2*BM25` skill routing).
2. Automatic discovery & injection of `AGENTS.md` / `CLAUDE.md` in the workspace.
3. All 7 reversed speaking styles (`sarcastic` 毒舌朋友, `efficient`, `professional`, `socratic`,
   `friendly`, `creative`, `straightforward`), plus OpenClaw-derived `SOUL.md` & 48-bit Zero-Width Watermark.
"""

import sys
import tempfile
from pathlib import Path

# Ensure workbuddy_cli is importable when running directly from examples/
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workbuddy_cli.config import WorkBuddyConfig
from workbuddy_cli.memory import (
    SoulMemoryManager,
    append_invisible_run_marker,
    decode_invisible_run_marker,
)
from workbuddy_cli.prompt_engine import PromptEngine
from workbuddy_cli.skill_router import SkillRouter


def main() -> None:
    print("=" * 88)
    print("🔥 [01] WorkBuddy-CLI: 33K 僵尸底仓瘦身对比 + AGENTS.md 挂载 + 7 种说话风格 & 毒舌灵魂实测")
    print("=" * 88)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        cfg_dir = tmp_root / "config"
        ws_dir = tmp_root / "workspace"
        ws_dir.mkdir(parents=True, exist_ok=True)

        # 1. Create a mock project AGENTS.md in workspace to demonstrate automatic discovery
        agents_md_file = ws_dir / "AGENTS.md"
        agents_md_file.write_text(
            "# Project Engineering Rules (AGENTS.md)\n"
            "- Always prioritize DeepSeek MLA/HCA memory efficiency.\n"
            "- Never use bloated multi-agent relay when single-context role-switch suffices.\n",
            encoding="utf-8",
        )

        cfg = WorkBuddyConfig(
            model="deepseek-flash",
            mode="craft",
            style="sarcastic",
            prompt_profile="lean",
            load_agents_md=True,
            workspace_dir=str(ws_dir),
            config_dir=str(cfg_dir),
        )

        mem = SoulMemoryManager(cfg_dir, ws_dir, ".workbuddy")
        engine = PromptEngine(cfg, memory_manager=mem)

        # 2. Compare Startup Token Footprint (Lean vs Full .tpl vs Desktop 32,739 baseline)
        footprint = engine.compare_token_footprint()
        print("\n📊 [1] 开局第一句“你好”的系统提示词 Token 账单对比：")
        print(f"  - 原版 WorkBuddy 桌面端实测 (`rawUsage` 含百余工具 Schema): {footprint['workbuddy_desktop_hello_tokens']:,} tokens")
        print(f"  - 原版 `.tpl` 全量静态拼接 (`--profile full`):             {footprint['full_tpl_tokens']:,} tokens ({footprint['full_tpl_chars']:,} chars)")
        print(f"  - workbuddy-cli 精简按需加载 (`--profile lean`, 默认):     {footprint['lean_tokens']:,} tokens ({footprint['lean_chars']:,} chars)")
        print(f"  ⚡ 开局底仓直降比例: 节省 {footprint['token_savings_vs_desktop_pct']}% 僵尸 Token！(把宝贵的算力留给真实代码与推理)")

        # 3. Show all 7 reversed speaking styles & highlight `sarcastic` (毒舌朋友)
        print("\n🎭 [2] 逆向提取的 7 种内置说话风格 (`assets/templates/style/style-*.md`)：")
        styles = engine.list_styles()
        for s_name, s_desc in styles.items():
            marker = "👉 [当前激活]" if s_name == "sarcastic" else "   "
            print(f"  {marker} {s_name:<16} : {s_desc}")

        sarcastic_body = engine.load_style_content("sarcastic")
        print("\n🌶️  [`sarcastic` 毒舌朋友风格核心指令预览]：")
        for line in sarcastic_body.splitlines()[:8]:
            print(f"    {line}")

        # 4. Verify AGENTS.md & Model-aware Complexity Gating inside rendered prompt
        lean_prompt = engine.render_system_prompt(mode="craft", style="sarcastic", profile="lean")
        assert "<agents_md" in lean_prompt, "AGENTS.md must be injected into system prompt!"
        assert "Stock price increase (涨) → Red (红色)" in lean_prompt, "A-share convention must be present!"
        print("\n✅ [3] 原生 `AGENTS.md` 自动挂载与本土化护栏验证通过：")
        print(f"  - 已自动向上探测并注入: {agents_md_file}")
        print(f"  - A 股红涨绿跌铁律: 已内嵌 (`Stock price increase (涨) → Red`)")
        print(f"  - 模型智商画图分级 (`Model-aware complexity gating`): {cfg.model} -> Tier `{cfg.get_model_complexity_tier()}` (无上限)")

        # 5. Dynamic RecallIndex (0.8 * Cosine + 0.2 * BM25) on-demand skill injection
        router = SkillRouter()
        query = "帮我起草一份符合国家标准的红头通知公文，并检查封面居中排版"
        hits = router.match(query, top_k=3)
        print(f"\n🧭 [4] `0.8 * Cosine + 0.2 * BM25` 动态技能路由实测 (Query: 「{query}」)：")
        for idx, h in enumerate(hits, start=1):
            print(f"  Top-{idx}: {h['id']:<28} | score={h['score']:.4f} (bm25={h['bm25']:.4f}) | {h['description'][:48]}...")

        # 6. Demonstrate 48-bit Zero-Width Invisible Watermark from claw-content-utils.js
        sample_reply = "行了别磨叽了，你那个 OOM 就是因为把整个数据集塞进列表了，改成生成器 3 行代码搞定。"
        watermarked = append_invisible_run_marker(sample_reply, "run-suzaku-2026")
        decoded_hex = decode_invisible_run_marker(watermarked)
        print("\n🕵️ [5] OpenClaw 48-bit 零宽字符隐式水印 (`\\u200b` / `\\u200c` 二进制编码) 往返验证：")
        print(f"  - 表面可见文本: {watermarked}")
        print(f"  - 零宽字符解码 (SHA-256 前 6 字节 Hex): {decoded_hex}")
        assert decoded_hex is not None and len(decoded_hex) == 12

    print("\n🎉 Example 01 全部断言通过！")


if __name__ == "__main__":
    main()
