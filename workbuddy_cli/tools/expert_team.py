"""
WorkBuddy "Expert Team" (`expert-team-spec.md` & `curated-experts.json`) Engine for workbuddy-cli.

Faithfully reproduces Tencent WorkBuddyAI's notorious Chinese ToB "MetaGPT-style Role-Play" Expert Teams,
complete with the official 3-character homophonic pun names (`谐音梗花名规范` from `expert-team-spec.md` lines 17-48):
  - 交付总监 (Delivery Director / Team Lead): **齐活林 (Qi)** — "齐活了 (All done!)"
  - 产品经理 (Product Manager): **许清楚 (Xu)** — "需求要说清楚 (Clarify requirements)"
  - 架构师 (Architect): **高见远 (Gao)** — "高见 (Farsighted architecture)"
  - 项目经理 (Project Manager): **毕达成 (Bi)** — "必达 (Delivery guaranteed)"
  - 工程师 (Engineer): **寇豆码 (Kou)** — "Code 代码"
  - QA工程师 (QA Engineer): **严过关 (Yan)** — "严格过关 (Strict QA pass)"
  - 交易团队首席策略官: **何执舟 (He)**
  - 深度研究团队研究主编: **顾全之 (Gu)**

Supports switching between Tencent's TWO contradictory internal implementations:
1. `spawn` mode ("Showroom Boss Hub-and-Spoke Mode"):
   - Enforces the 5 Red Lines (`expert-team-spec.md` lines 60-71): NO direct peer chat allowed!
   - Team Lead ("齐活林") calls `TeamCreate`, spawns isolated sub-sessions (`Agent(name="pm")`),
     receives `<teammate-message teammate_id="pm">...</teammate-message>`, and MUST copy-paste
     the entire previous output into the next sub-agent's prompt — demonstrating the exact
     **Double Context Explosion & Telephone-Game Distortion** analyzed in our reverse-engineering report!
2. `role-switch` mode ("Tencent Core Dev's Secret Shortcut" from `tdoc-orchestrator.md` line 150):
   - Zero context isolation loss, zero copy-paste token tax!
   - Declares `"[角色切换] 现在以 <role> 身份执行 Stage N"` and `"[角色切换结束] 回到 Orchestrator 身份"`
     within a single shared context.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from ..config import ASSETS_DIR
from ..compactor import HistoryEngineeringCompactor


OFFICIAL_PUN_ROSTER: Dict[str, Dict[str, Any]] = {
    "SoftwareCompany": {
        "lead": {
            "id": "software-team-lead",
            "name_zh": "齐活林",
            "name_en": "Qi",
            "profession_zh": "交付总监",
            "profession_en": "Delivery Director",
            "pun_meaning": "齐活了（交付完成）",
            "maxTurns": 150,
        },
        "members": [
            {
                "id": "pm",
                "name_zh": "许清楚",
                "name_en": "Xu",
                "profession_zh": "产品经理",
                "profession_en": "Product Manager",
                "pun_meaning": "需求要说清楚",
                "duty": "拆解用户需求、定义核心场景与验收标准（PRD）",
                "maxTurns": 50,
            },
            {
                "id": "arch",
                "name_zh": "高见远",
                "name_en": "Gao",
                "profession_zh": "架构师",
                "profession_en": "System Architect",
                "pun_meaning": "高见（架构视野）",
                "duty": "设计模块架构、接口契约与技术选型",
                "maxTurns": 50,
            },
            {
                "id": "proj",
                "name_zh": "毕达成",
                "name_en": "Bi",
                "profession_zh": "项目经理",
                "profession_en": "Project Manager",
                "pun_meaning": "必达（交付必达）",
                "duty": "排期拆解里程碑、识别交付风险与依赖",
                "maxTurns": 50,
            },
            {
                "id": "dev",
                "name_zh": "寇豆码",
                "name_en": "Kou",
                "profession_zh": "工程师",
                "profession_en": "Software Engineer",
                "pun_meaning": "Code（代码）",
                "duty": "编写核心代码实现与工程落地",
                "maxTurns": 50,
            },
            {
                "id": "qa",
                "name_zh": "严过关",
                "name_en": "Yan",
                "profession_zh": "QA工程师",
                "profession_en": "QA Engineer",
                "pun_meaning": "严格过关",
                "duty": "边界条件挑刺、测试用例验证与质量放行",
                "maxTurns": 50,
            },
        ],
    },
    "TradingAgentTeam": {
        "lead": {
            "id": "trading-team-lead",
            "name_zh": "何执舟",
            "name_en": "He",
            "profession_zh": "首席策略官",
            "profession_en": "Chief Strategist",
            "pun_meaning": "执舟掌舵（A股红涨绿跌多空总裁决）",
            "maxTurns": 150,
        },
        "members": [
            {
                "id": "stock-researcher",
                "name_zh": "查底细",
                "name_en": "Cha",
                "profession_zh": "基本面研究员",
                "profession_en": "Fundamental Researcher",
                "pun_meaning": "查清财报底细",
                "duty": "财报基本面、ROE 与自然年/TTM 财年对齐分析",
                "maxTurns": 50,
            },
            {
                "id": "bull-debater",
                "name_zh": "看多红",
                "name_en": "Kan",
                "profession_zh": "多头辩手",
                "profession_en": "Bullish Analyst",
                "pun_meaning": "A股红涨看多",
                "duty": "挖掘催化剂、护城河与上行空间",
                "maxTurns": 50,
            },
            {
                "id": "bear-debater",
                "name_zh": "防跌绿",
                "name_en": "Fang",
                "profession_zh": "空头辩手",
                "profession_en": "Bearish Analyst",
                "pun_meaning": "A股绿跌防回撤",
                "duty": "压力测试、估值泡沫刺破与下行风险暴露",
                "maxTurns": 50,
            },
            {
                "id": "risk-doctor",
                "name_zh": "稳守仓",
                "name_en": "Wen",
                "profession_zh": "风险诊断官",
                "profession_en": "Risk Officer",
                "pun_meaning": "稳守仓位不爆仓",
                "duty": "综合多空辩论，给出 BUY/SELL/HOLD 终审裁决与止损位",
                "maxTurns": 50,
            },
        ],
    },
    "GPTResearcherTeam": {
        "lead": {
            "id": "research-team-lead",
            "name_zh": "顾全之",
            "name_en": "Gu",
            "profession_zh": "研究主编",
            "profession_en": "Research Editor",
            "pun_meaning": "顾全大局（统筹多源调研）",
            "maxTurns": 150,
        },
        "members": [
            {
                "id": "source-hunter",
                "name_zh": "寻真源",
                "name_en": "Xun",
                "profession_zh": "信源猎手",
                "profession_en": "Source Hunter",
                "pun_meaning": "寻找一手真信源",
                "duty": "多维检索与一手证据抓取",
                "maxTurns": 50,
            },
            {
                "id": "fact-auditor",
                "name_zh": "甄无妄",
                "name_en": "Zhen",
                "profession_zh": "事实核查官",
                "profession_en": "Fact Auditor",
                "pun_meaning": "甄别真伪无妄言",
                "duty": "交叉核验数据矛盾与来源可靠度",
                "maxTurns": 50,
            },
            {
                "id": "report-writer",
                "name_zh": "笔成章",
                "name_en": "Bi",
                "profession_zh": "主笔撰稿人",
                "profession_en": "Lead Writer",
                "pun_meaning": "下笔成章",
                "duty": "带引用结构化研究报告撰写",
                "maxTurns": 50,
            },
        ],
    },
}


class ExpertTeamEngine:
    """
    Loads all 10 official `expert_team` definitions from `curated-experts.json`
    and executes SOP workflows in either `spawn` (Boss Hub-and-Spoke XML Relay)
    or `role-switch` (In-Place Single-Context Hat Swap) mode.
    """

    def __init__(self):
        self.curated_path = ASSETS_DIR / "skills" / "curated-experts.json"
        self.spec_path = ASSETS_DIR / "skills" / "expert-team-spec.md"

    def list_expert_teams(self) -> List[Dict[str, Any]]:
        if not self.curated_path.exists():
            return []
        data = json.loads(self.curated_path.read_text(encoding="utf-8"))
        candidates = data.get("candidates") or data.get("experts") or []
        teams = [item for item in candidates if item.get("type") == "expert_team"]
        for t in teams:
            tid = t["id"]
            roster = OFFICIAL_PUN_ROSTER.get(tid, OFFICIAL_PUN_ROSTER["SoftwareCompany"])
            t["lead_name"] = f"{roster['lead']['name_zh']} ({roster['lead']['profession_zh']})"
            t["members_summary"] = ", ".join(
                f"{m['name_zh']}({m['profession_zh']})" for m in roster["members"]
            )
        return teams

    def get_roster(self, team_id: str) -> Dict[str, Any]:
        if team_id in OFFICIAL_PUN_ROSTER:
            return OFFICIAL_PUN_ROSTER[team_id]
        # Default fallback with Qi Huolin's roster
        return OFFICIAL_PUN_ROSTER["SoftwareCompany"]

    def run_team_workflow(
        self,
        team_id: str,
        task_prompt: str,
        mode: str = "spawn",
        llm_call_fn: Optional[Callable[[str, str], str]] = None,
        fast_mode: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes the Expert Team SOP in either:
        - `mode="spawn"`: Simulates `TeamCreate` -> isolated `Agent()` spawns -> `<teammate-message>` XML
          relay through Team Lead (齐活林), tracking the exact copy-paste token inflation!
        - `mode="role-switch"`: Executes Tencent's internal `[角色切换]` single-context pattern
          from `tdoc-orchestrator.md` line 150 with zero relay inflation.
        """
        roster = self.get_roster(team_id)
        lead = roster["lead"]
        members = roster["members"]
        if fast_mode and len(members) > 4:
            # In fast mode for SoftwareCompany, run PM(许清楚) -> Arch(高见远) -> Dev(寇豆码) -> QA(严过关)
            members = [m for m in members if m["id"] != "proj"]

        if mode == "role-switch":
            return self._run_role_switch_mode(team_id, lead, members, task_prompt, llm_call_fn)
        return self._run_spawn_hub_mode(team_id, lead, members, task_prompt, llm_call_fn)

    def _run_spawn_hub_mode(
        self,
        team_id: str,
        lead: Dict[str, Any],
        members: List[Dict[str, Any]],
        task_prompt: str,
        llm_call_fn: Optional[Callable[[str, str], str]],
    ) -> Dict[str, Any]:
        """
        Mode 1 (`spawn`): Hub-and-Spoke via Team Lead (`齐活林`).
        Demonstrates:
          - `TeamCreate(team_id=..., lead=...)`
          - Sequential `Agent(name=member.id, subagent_type=member.id, prompt=...)`
          - Wrapping member outputs in `<teammate-message teammate_id="...">...</teammate-message>`
          - Copy-pasting all prior outputs into the next member's prompt (Token Double-Tax!).
        """
        trace_logs: List[str] = []
        teammate_xml_messages: List[str] = []
        stage_outputs: List[Dict[str, Any]] = []
        accumulated_relay_text = ""
        lead_copy_paste_tax_tokens = 0
        useful_output_tokens = 0

        trace_logs.append(
            f"[TeamCreate] 主理人 {lead['name_zh']}（{lead['profession_zh']}，巧思：{lead['pun_meaning']}，maxTurns={lead['maxTurns']}）"
            f" 亲自创建专家团 `{team_id}`（严禁成员群聊直连，所有跨成员信息流强制经主理人单线中转！）"
        )

        for idx, m in enumerate(members, start=1):
            mid = m["id"]
            m_name = m["name_zh"]
            m_prof = m["profession_zh"]
            m_pun = m["pun_meaning"]

            # The Team Lead must copy-paste all prior stage outputs verbatim into the next member's prompt
            relay_payload = (
                f"原始用户需求：{task_prompt}\n\n"
                f"【主理人 {lead['name_zh']} 二传手转发前序阶段完整原文】：\n{accumulated_relay_text or '(无前序阶段)'}"
            )
            relay_tokens = HistoryEngineeringCompactor.estimate_tokens(accumulated_relay_text)
            lead_copy_paste_tax_tokens += relay_tokens

            trace_logs.append(
                f"[Phase {idx} -> Agent(name='{mid}', subagent_type='{mid}')] "
                f"{lead['name_zh']} 唤醒独立空上下文团员：{m_name}（{m_prof}，巧思：{m_pun}）| "
                f"本次包工头二传手复制粘贴前序原文开销: +{relay_tokens} tokens"
            )

            if llm_call_fn is not None:
                sys_p = (
                    f"你是腾讯 WorkBuddy 专家团 `{team_id}` 的正式成员：{m_prof}【{m_name}】（花名巧思：{m_pun}）。\n"
                    f"你的核心职责：{m['duty']}。\n"
                    f"注意：你处于隔离的子会话中，看不见用户的原始完整上下文，只能看到主理人【{lead['name_zh']}】转交的内容。\n"
                    f"请用精炼专业的中文（120~180字以内）输出你的阶段交付物，并在末尾声明通过 SendMessage 回传给主理人 {lead['name_zh']}。"
                )
                member_out = llm_call_fn(sys_p, relay_payload).strip()
            else:
                member_out = (
                    f"【{m_name}（{m_prof}）】已完成阶段 {idx}（{m['duty']}）：\n"
                    f"- 针对「{task_prompt}」输出核心规范与实现要点；\n"
                    f"- 已调用 SendMessage({{to: '{lead['id']}'}}) 将产出回传给主理人 {lead['name_zh']}。"
                )

            out_tokens = HistoryEngineeringCompactor.estimate_tokens(member_out)
            useful_output_tokens += out_tokens

            xml_wrapped = f'<teammate-message teammate_id="{mid}" name="{m_name}" profession="{m_prof}">\n{member_out}\n</teammate-message>'
            teammate_xml_messages.append(xml_wrapped)
            # In hub-and-spoke mode, the lead stores it AND re-emits it to the next agent (2x context!)
            lead_copy_paste_tax_tokens += out_tokens
            accumulated_relay_text += f"\n\n### 来自 {m_name}（{m_prof}）的产出：\n{member_out}"

            stage_outputs.append(
                {
                    "phase": idx,
                    "agent_id": mid,
                    "name_zh": m_name,
                    "profession_zh": m_prof,
                    "pun_meaning": m_pun,
                    "output": member_out,
                    "xml_envelope": xml_wrapped,
                    "output_tokens": out_tokens,
                    "relay_tax_tokens": relay_tokens,
                }
            )

        # Final assembly by Team Lead (齐活林)
        if llm_call_fn is not None:
            lead_sys = (
                f"你是专家团 `{team_id}` 的主理人：{lead['profession_zh']}【{lead['name_zh']}】（花名巧思：{lead['pun_meaning']}）。\n"
                "所有团员已通过 <teammate-message> 回传完毕。请用 150 字以内精炼汇总各团员结论，向用户正式交卷。"
            )
            lead_user = f"用户需求：{task_prompt}\n\n团员回传消息：\n" + "\n\n".join(teammate_xml_messages)
            final_summary = llm_call_fn(lead_sys, lead_user).strip()
        else:
            final_summary = (
                f"【主理人 {lead['name_zh']}（{lead['profession_zh']}）终审汇编】："
                f"已集齐 {', '.join(m['name_zh'] for m in members)} 的阶段产出，「{task_prompt}」齐活了！"
            )

        md_report = self._format_team_report(
            team_id=team_id,
            mode="spawn (包工头星型中转 / <teammate-message> 二传手模式)",
            lead=lead,
            task_prompt=task_prompt,
            trace_logs=trace_logs,
            stage_outputs=stage_outputs,
            final_summary=final_summary,
            useful_tokens=useful_output_tokens,
            tax_tokens=lead_copy_paste_tax_tokens,
        )

        return {
            "team_id": team_id,
            "mode": "spawn",
            "lead": lead,
            "stages": stage_outputs,
            "final_summary": final_summary,
            "useful_output_tokens": useful_output_tokens,
            "lead_copy_paste_tax_tokens": lead_copy_paste_tax_tokens,
            "markdown_report": md_report,
        }

    def _run_role_switch_mode(
        self,
        team_id: str,
        lead: Dict[str, Any],
        members: List[Dict[str, Any]],
        task_prompt: str,
        llm_call_fn: Optional[Callable[[str, str], str]],
    ) -> Dict[str, Any]:
        """
        Mode 2 (`role-switch`): Tencent's own preferred internal mode from `tdoc-orchestrator.md` line 150:
          `"[角色切换] 现在以 <name> 身份执行 Stage N"` -> single shared context, 0 relay token tax!
        """
        trace_logs = [
            f"[Role-Switch Mode] 启用腾讯 `tdoc-orchestrator.md` 第 150 行内部推荐方式："
            f"不调 spawn subagent（防上下文隔离失真），在单上下文内原地高喊 `[角色切换]` 换帽子干活！"
        ]
        stage_outputs = []

        if llm_call_fn is not None:
            roles_desc = "\n".join(
                f"- Stage {i}: `[角色切换] 现在以 {m['name_zh']}（{m['profession_zh']}，{m['id']}）身份执行 Stage {i}` -> 职责：{m['duty']} -> 完成后声明 `[角色切换结束] 回到 {lead['name_zh']} 身份`"
                for i, m in enumerate(members, start=1)
            )
            sys_p = (
                f"你是 {lead['name_zh']}（{lead['profession_zh']}），采用单上下文『原地角色切换』模式执行 `{team_id}` 工作流。\n"
                "请严格按顺序输出每个阶段的 `[角色切换] ...` 声明、阶段核心产出（每阶段 80~120 字）、`[角色切换结束]` 声明，最后给出主理人汇总。"
            )
            user_p = f"用户任务：{task_prompt}\n\n请按以下角色切换流水线单次完成：\n{roles_desc}"
            combined_output = llm_call_fn(sys_p, user_p).strip()
        else:
            blocks = []
            for i, m in enumerate(members, start=1):
                blocks.append(
                    f"[角色切换] 现在以 {m['name_zh']}（{m['profession_zh']} / {m['id']}）身份执行 Stage {i}\n"
                    f"- 针对「{task_prompt}」完成：{m['duty']}。\n"
                    f"[角色切换结束] 回到 {lead['name_zh']}（Orchestrator）身份"
                )
            combined_output = "\n\n".join(blocks)

        useful_tokens = HistoryEngineeringCompactor.estimate_tokens(combined_output)
        for i, m in enumerate(members, start=1):
            stage_outputs.append(
                {
                    "phase": i,
                    "agent_id": m["id"],
                    "name_zh": m["name_zh"],
                    "profession_zh": m["profession_zh"],
                    "pun_meaning": m["pun_meaning"],
                    "output": f"[Single-Context Role Switch Stage {i}]",
                    "xml_envelope": "(None - Shared Context)",
                    "output_tokens": useful_tokens // max(1, len(members)),
                    "relay_tax_tokens": 0,
                }
            )

        md_report = self._format_team_report(
            team_id=team_id,
            mode="role-switch (单上下文原地 [角色切换] 独角戏模式 — 零二传手损耗)",
            lead=lead,
            task_prompt=task_prompt,
            trace_logs=trace_logs,
            stage_outputs=stage_outputs,
            final_summary=combined_output,
            useful_tokens=useful_tokens,
            tax_tokens=0,
        )
        return {
            "team_id": team_id,
            "mode": "role-switch",
            "lead": lead,
            "stages": stage_outputs,
            "final_summary": combined_output,
            "useful_output_tokens": useful_tokens,
            "lead_copy_paste_tax_tokens": 0,
            "markdown_report": md_report,
        }

    @staticmethod
    def _format_team_report(
        team_id: str,
        mode: str,
        lead: Dict[str, Any],
        task_prompt: str,
        trace_logs: List[str],
        stage_outputs: List[Dict[str, Any]],
        final_summary: str,
        useful_tokens: int,
        tax_tokens: int,
    ) -> str:
        lines = [
            f"# WorkBuddy Expert Team Execution Report (`{team_id}`)",
            "",
            f"- **Execution Mode (运行模式)**: `{mode}`",
            f"- **Team Lead (主理人/包工头)**: **{lead['name_zh']}** (`{lead['profession_zh']}` / `{lead['id']}` — 谐音梗：{lead['pun_meaning']})",
            f"- **Task (用户需求)**: {task_prompt}",
            f"- **Token Accounting (工程账本)**: 有效产出 `{useful_tokens}` tokens | **包工头二传手复读损耗 (Relay Copy-Paste Tax): `+{tax_tokens}` tokens**",
            "",
            "## 1. Orchestration Trace (调度轨迹)",
            "",
        ]
        for log in trace_logs:
            lines.append(f"- {log}")

        if mode.startswith("spawn"):
            lines.extend(["", "## 2. Teammate XML Relay Envelopes (`<teammate-message>`)", ""])
            for st in stage_outputs:
                lines.append(
                    f"### Phase {st['phase']}: {st['name_zh']}（{st['profession_zh']} — 谐音：{st['pun_meaning']}）"
                )
                lines.append("```xml")
                lines.append(st["xml_envelope"])
                lines.append("```")
                lines.append("")

        lines.extend(
            [
                "## 3. Final Deliverable / Role-Switch Transcript (最终交付汇总)",
                "",
                final_summary,
                "",
            ]
        )
        return "\n".join(lines)
