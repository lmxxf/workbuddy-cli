#!/usr/bin/env python3
"""
Example 02: "齐活林" Expert Team — Spawn Hub-and-Spoke Relay vs. Single-Context Role-Switch
============================================================================================
Demonstrates the hilarious architectural contradiction inside Tencent WorkBuddyAI:
1. `spawn` mode ("给客户汇报撑场面的包工头星型传话模式"):
   - Enforces the official 3-character homophonic pun names (`谐音梗花名规范` from `expert-team-spec.md`):
     交付总监 **齐活林** (Qi) -> 产品经理 **许清楚** (Xu) -> 架构师 **高见远** (Gao) ->
     程序员 **寇豆码** (Kou) -> 测试工程师 **严过关** (Yan).
   - Hard red line: Members CANNOT talk directly! Team Lead `齐活林` must copy-paste every prior stage's
     output into the next sub-agent's prompt and wrap replies in `<teammate-message teammate_id="...">`,
     causing severe **Double Context Explosion (二传手双倍 Token 爆炸)**!
2. `role-switch` mode ("腾讯核心开发者自己在 `tdoc-orchestrator.md` 第 150 行偷偷用的独角戏模式"):
   - Directly quotes Tencent's internal warning: `⚠️ 注意：subagent 模式上下文隔离，效果不稳定，非必要不使用`.
   - Uses `[角色切换] 现在以 <role> 身份执行 Stage N` inside a single shared context with ZERO relay tax!
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workbuddy_cli.tools.expert_team import ExpertTeamEngine


def main() -> None:
    print("=" * 88)
    print("🎭 [02] WorkBuddy-CLI: 『齐活林』专家团 — 包工头星型传话 (Spawn) vs 原地换帽子 (Role-Switch)")
    print("=" * 88)

    engine = ExpertTeamEngine()
    teams = engine.list_expert_teams()
    print(f"\n📋 [1] 已加载 `curated-experts.json` 中的 {len(teams)} 个官方内置专家团（含三字谐音梗花名）：")
    for t in teams[:5]:
        print(f"  - [{t['id']:<20}] 主理人: {t['lead_name']:<18} | 团员: {t['members_summary']}")

    task = "设计并实现一个支持 GB 45438-2025 隐式水印与零 LLM AST 门禁的智能文档流水线"

    # 1. Run `spawn` mode (Hub-and-Spoke via 齐活林)
    spawn_res = engine.run_team_workflow(
        team_id="SoftwareCompany",
        task_prompt=task,
        mode="spawn",
        fast_mode=True,
    )

    # 2. Run `role-switch` mode (Single-Context Hat Swap)
    switch_res = engine.run_team_workflow(
        team_id="SoftwareCompany",
        task_prompt=task,
        mode="role-switch",
        fast_mode=True,
    )

    print("\n" + "-" * 88)
    print("🔥 [2] 模式一：`spawn` 包工头星型二传手模式（外行汇报演戏版）调度轨迹：")
    print("-" * 88)
    for st in spawn_res["stages"]:
        print(
            f"  Phase {st['phase']}: {st['name_zh']}（{st['profession_zh']} | 谐音：{st['pun_meaning']}）"
            f" -> 产出 {st['output_tokens']} tokens | 齐活林二传手粘贴税: +{st['relay_tax_tokens']} tokens"
        )
    print("\n  📦 `<teammate-message>` XML 传话信封示例 (Phase 1 许清楚):")
    for line in spawn_res["stages"][0]["xml_envelope"].splitlines():
        print(f"    {line}")

    print("\n" + "-" * 88)
    print("⚡ [3] 模式二：`role-switch` 单上下文原地换帽子模式（腾讯 `tdoc-orchestrator.md` 自用版）：")
    print("-" * 88)
    for line in switch_res["final_summary"].splitlines()[:9]:
        print(f"  {line}")

    print("\n" + "=" * 88)
    print("📊 [4] 两种多智能体编排模式的工程 Token 账单终极对比：")
    print("=" * 88)
    spawn_useful = spawn_res["useful_output_tokens"]
    spawn_tax = spawn_res["lead_copy_paste_tax_tokens"]
    switch_useful = switch_res["useful_output_tokens"]
    switch_tax = switch_res["lead_copy_paste_tax_tokens"]

    print(f"  - `spawn` 星型传话模式      : 有效产出 {spawn_useful:>4} tokens | 包工头二传手复读税 +{spawn_tax:>4} tokens (额外膨胀 {spawn_tax / max(1, spawn_useful) * 100:.1f}%)")
    print(f"  - `role-switch` 原地换帽模式: 有效产出 {switch_useful:>4} tokens | 包工头二传手复读税 +{switch_tax:>4} tokens (0 传话损耗，上下文 100% 共享)")

    assert spawn_tax > 0, "Spawn mode must demonstrate non-zero relay copy-paste token tax!"
    assert switch_tax == 0, "Role-switch mode must have zero relay token tax!"
    print("\n🎉 Example 02 全部断言通过！")


if __name__ == "__main__":
    main()
