#!/usr/bin/env python3
"""
Main CLI & Interactive REPL entrypoint for `workbuddy-cli` (`workbuddy` / `wb`).
Features:
- Real-time interactive slash-command dropdown menu & multi-level `Tab` autocomplete
  powered by `prompt_toolkit` (`WorkBuddySlashCompleter` + `PromptSession`).
- Rich `/context` (and `/status`) dashboard displaying real-time token accounting,
  `AGENTS.md` mount status, `SOUL.md` 3-tier memory, and compaction threshold gauges.
- Smart prefix matching for slash commands (e.g. `/cont` -> `/context`).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from . import __version__
from .config import (
    WorkBuddyConfig,
    VALID_MODES,
    VALID_STYLES,
    VALID_PROMPT_PROFILES,
    VALID_THINKING_LEVELS,
    ASSETS_DIR,
    discover_agents_md,
)
from .memory import SoulMemoryManager
from .prompt_engine import PromptEngine
from .compactor import ThreeStageCompactor, HistoryEngineeringCompactor
from .skill_router import SkillRouter
from .agent_client import WorkBuddyAgentClient
from .tools.office_suite import (
    review_html_ast,
    render_government_doc_html,
    convert_html_to_docx,
    recalc_xlsx_formulas,
    create_sample_xlsx_without_cache,
)
from .tools.critic_engine import CriticGeneratorEngine
from .tools.deep_research import DeepResearchWorkflow
from .tools.expert_team import ExpertTeamEngine
from .tools.visualizer import generate_architecture_svg_widget


console = Console()


SLASH_COMMANDS_META: List[Tuple[str, str, str]] = [
    ("/context", "/context", "查看精细上下文账本 (System/AGENTS.md/History Token 占比与压缩水位线)"),
    ("/status", "/status", "查看当前会话状态、模型配置与上下文账本 (同 /context)"),
    ("/think", "/think <off|low|medium|high|max>", "控制思维链开关与长短档位 (off 关闭黑盒 CoT | low 50 | medium 65 | high 75 | max 100)"),
    ("/effort", "/effort <off|low|medium|high|max>", "控制思维链长短档位 (同 /think: off | low | medium | high | max)"),
    ("/mode", "/mode <craft|ask|expert|plan>", "切换工作模式 (craft 编码执行 | ask 只读问答 | expert 专家 | plan 规划)"),
    ("/style", "/style <style_name>", "切换 7 种说话风格 (含 sarcastic 毒舌死党 | efficient | professional 等)"),
    ("/model", "/model <model_name>", "切换大模型 (deepseek-chat | deepseek-reasoner | deepseek-flash | deepseek-v4-pro)"),
    ("/profile", "/profile <lean|full>", "切换提示词档位 (lean 2.6K 精简按需 vs full 33K 腾讯原版 .tpl)"),
    ("/team", "/team [TeamId] [spawn|role-switch] <task>", "召唤『齐活林』10大官方谐音梗专家团 (spawn 二传手 vs role-switch 原地换帽)"),
    ("/compact", "/compact [--engineering-only|--llm]", "执行三级上下文压缩 (含假完工催眠 Bug 修复)"),
    ("/research", "/research <topic>", "运行五阶段 Deep Research 深度研究 (2/3 怀疑论杠精陪审团)"),
    ("/critic", "/critic <file_or_text>", "运行六步对抗式盲审引擎 (强制扣分配额 min_issues=2, min_instructions=3)"),
    ("/docx", "/docx <title> [out.docx]", "三阶段 GB/T 9704 红头公文生成 + 零 LLM review_html.py AST 门禁"),
    ("/recalc", "/recalc <xlsx_path>", "Excel 公式重算回填 <v> 缓存 (解决微信预览空白) + GB 45438 AIGC 隐式水印"),
    ("/skills", "/skills [query|init|validate]", "0.8*Cosine + 0.2*BM25 动态技能检索与 skill-creator 创建校验"),
    ("/soul", "/soul [status|onboard|reset]", "查看/孵化/重置 SOUL.md + IDENTITY.md + USER.md + 三层记忆"),
    ("/enhance", "/enhance <raw_prompt>", "一键小闪光图标提示词增强 (llm:enhancePrompt)"),
    ("/clear", "/clear", "清空当前会话历史消息"),
    ("/help", "/help", "显示所有斜杠命令与快捷键帮助"),
    ("/quit", "/quit", "退出 workbuddy-cli"),
]

MODEL_CANDIDATES: List[Tuple[str, str]] = [
    ("deepseek-chat", "DeepSeek 默认主力对话/Agent 模型 (极速响应)"),
    ("deepseek-reasoner", "DeepSeek 深度思考推理模型 (输出 reasoning_content 思维链)"),
    ("deepseek-flash", "DeepSeek-V4.1-Flash (1M 上下文原生多模态)"),
    ("deepseek-v4-pro", "DeepSeek-V4-Pro (1M 上下文旗舰底座)"),
]

MODE_CANDIDATES: List[Tuple[str, str]] = [
    ("craft", "Agent 读写执行模式 (You say, I do — 全套 10 大工具可用)"),
    ("ask", "只读问答分析模式 (Talk only, hands off — 禁用写文件与命令执行)"),
    ("expert", "领域专家模式 (启用专家身份模板与对抗审查规范)"),
    ("plan", "架构规划模式 (Think first, do second)"),
]

PROFILE_CANDIDATES: List[Tuple[str, str]] = [
    ("lean", "精简高信噪比模式 (~2.6K tokens，节省 91.8% 僵尸底仓，按需挂载 Skill)"),
    ("full", "腾讯 WorkBuddy 原版全量 .tpl 模式 (~23K-33K tokens，1:1 逆向复刻)"),
]

THINK_CANDIDATES: List[Tuple[str, str]] = [
    ("off", "关闭内部黑盒思维链 (thinking: disabled，仅靠 AGENTS.md 括号外放推演，极速省 Token)"),
    ("low", "轻度思考档位 (DeepSeek V4.1 控长 50 / reasoning_effort='low'，短平快 CoT)"),
    ("medium", "中度思考档位 (DeepSeek V4.1 控长 65 / reasoning_effort='medium'，均衡推演)"),
    ("high", "深度思考档位 (DeepSeek V4.1 控长 75 / reasoning_effort='high'，复杂代码与数学)"),
    ("max", "满血思考档位 (DeepSeek V4.1 控长 100，无长度上限约束)"),
]

COMPACT_CANDIDATES: List[Tuple[str, str]] = [
    ("--engineering-only", "第一阶段纯规则剪刀 (剥离工具大输出与代码参数，0 LLM 消耗)"),
    ("--llm", "第二阶段 DeepSeek 智能结构化二压 (已修复假完工催眠乌龙 Bug)"),
]

SOUL_CANDIDATES: List[Tuple[str, str]] = [
    ("status", "查看 SOUL.md 孵化状态与三层记忆路径"),
    ("onboard", "完成认主孵化并自删 BOOTSTRAP.md: /soul onboard <AgentName> <UserName>"),
    ("reset", "重置 SOUL.md / IDENTITY.md / USER.md 并恢复 BOOTSTRAP.md"),
]


def get_subcommand_completions(cmd: str, arg_tokens: List[str], current_word: str, client: WorkBuddyAgentClient) -> List[Tuple[str, str]]:
    """
    Returns `(completion_text, display_meta)` pairs for 1st, 2nd, and 3rd level slash command arguments.
    """
    cmd = cmd.lower()
    # Determine which argument slot the user is currently typing (0-indexed after command)
    slot_idx = len(arg_tokens) - 1 if current_word else len(arg_tokens)
    prefix = current_word.lower()

    candidates: List[Tuple[str, str]] = []

    if cmd == "/mode" and slot_idx == 0:
        candidates = MODE_CANDIDATES
    elif cmd in ("/think", "/effort") and slot_idx == 0:
        candidates = THINK_CANDIDATES
    elif cmd == "/style" and slot_idx == 0:
        styles_map = client.prompt_engine.list_styles()
        candidates = [(k, v) for k, v in styles_map.items()]
    elif cmd == "/model" and slot_idx == 0:
        candidates = MODEL_CANDIDATES
    elif cmd == "/profile" and slot_idx == 0:
        candidates = PROFILE_CANDIDATES
    elif cmd == "/compact" and slot_idx == 0:
        candidates = COMPACT_CANDIDATES
    elif cmd == "/soul" and slot_idx == 0:
        candidates = SOUL_CANDIDATES
    elif cmd == "/skills" and slot_idx == 0:
        candidates = [
            ("list", "列出全部内置与自定义 Skills"),
            ("init", "使用 skill-creator 创建新技能: /skills init <skill-name>"),
            ("validate", "运行增强版 quick_validate.py 校验技能目录"),
        ] + [(s.id, s.description[:50]) for s in client.skill_router.load_builtin_skills()]
    elif cmd == "/team":
        if slot_idx == 0:
            teams = client.team_engine.list_expert_teams()
            candidates = [("list", "列出全部 10 个官方专家团与谐音梗花名阵容")] + [
                (t["id"], f"{t['lead_name']} | {t['members_summary'][:42]}") for t in teams
            ]
        elif slot_idx == 1:
            candidates = [
                ("spawn", "包工头星型中转模式 (齐活林 <teammate-message> 二传手复制粘贴，双倍 Token 税)"),
                ("role-switch", "单上下文原地 [角色切换] 独角戏模式 (腾讯内部推荐，0 传话损耗)"),
            ]

    return [(text, meta) for text, meta in candidates if text.lower().startswith(prefix)]


def build_prompt_session(client: WorkBuddyAgentClient):
    """
    Builds a `prompt_toolkit.PromptSession` with real-time `/` dropdown menu and `Tab` completion.
    Gracefully returns `None` if `prompt_toolkit` is unavailable or terminal is not a TTY.
    """
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.styles import Style
    except ImportError:
        return None

    class WorkBuddySlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text_before = document.text_before_cursor
            stripped = text_before.lstrip()
            if not stripped.startswith("/"):
                return

            has_trailing_space = text_before.endswith(" ")
            parts = stripped.split()
            if not parts:
                return

            # Level 1: Completing the `/command` itself
            if len(parts) == 1 and not has_trailing_space:
                cmd_prefix = parts[0].lower()
                for cmd_name, usage, desc in SLASH_COMMANDS_META:
                    if cmd_name.startswith(cmd_prefix):
                        yield Completion(
                            text=cmd_name,
                            start_position=-len(parts[0]),
                            display=usage,
                            display_meta=desc,
                        )
                return

            # Level 2 & 3: Completing arguments after `/command `
            cmd_name = parts[0].lower()
            raw_args = parts[1:]
            current_word = "" if has_trailing_space else raw_args[-1]
            sub_candidates = get_subcommand_completions(cmd_name, raw_args, current_word, client)
            for cand_text, cand_meta in sub_candidates:
                yield Completion(
                    text=cand_text,
                    start_position=-len(current_word),
                    display=cand_text,
                    display_meta=cand_meta,
                )

    kb = KeyBindings()

    @kb.add("/")
    def _on_slash(event):
        buf = event.app.current_buffer
        buf.insert_text("/")
        if buf.text.strip().startswith("/"):
            buf.start_completion(select_first=False)

    @kb.add(" ")
    def _on_space(event):
        buf = event.app.current_buffer
        buf.insert_text(" ")
        if buf.text.lstrip().startswith("/"):
            buf.start_completion(select_first=False)

    @kb.add("tab")
    def _on_tab(event):
        buf = event.app.current_buffer
        if buf.complete_state:
            buf.complete_next()
        else:
            buf.start_completion(select_first=True)

    pt_style = Style.from_dict(
        {
            "prompt": "ansicyan bold",
            "completion-menu.completion": "bg:#1e1e2e #cdd6f4",
            "completion-menu.completion.current": "bg:#89b4fa #11111b bold",
            "completion-menu.meta.completion": "bg:#181825 #a6adc8",
            "completion-menu.meta.completion.current": "bg:#89b4fa #11111b",
        }
    )

    return PromptSession(
        completer=WorkBuddySlashCompleter(),
        complete_while_typing=True,
        key_bindings=kb,
        style=pt_style,
    )


def print_banner(config: WorkBuddyConfig, memory_mgr: SoulMemoryManager) -> None:
    id_vars = memory_mgr.collect_identity_vars()
    onboarding_tag = (
        "[bold yellow]ONBOARDING (BOOTSTRAP.md active)[/bold yellow]"
        if id_vars["WorkspaceIdentityMode"] == "onboarding"
        else "[bold green]INCUBATED (SOUL.md active)[/bold green]"
    )
    tier = config.get_model_complexity_tier()
    agents_paths = discover_agents_md(Path(config.workspace_dir))
    agents_tag = (
        f"[bold green]Mounted ({agents_paths[0].name})[/bold green]"
        if (config.load_agents_md and agents_paths)
        else "[dim]None[/dim]"
    )
    banner_text = (
        f"[bold cyan]WorkBuddy Open-Source CLI[/bold cyan] v{__version__}  "
        f"| Model: [bold magenta]{config.model}[/bold magenta] (Visualizer Tier: [bold]{tier}[/bold])\n"
        f"Mode: [bold]{config.mode}[/bold] | Style: [bold]{config.style}[/bold] | "
        f"Think: [bold yellow]{config.thinking_effort}[/bold yellow] | "
        f"Profile: [bold]{config.prompt_profile}[/bold] | AGENTS.md: {agents_tag} | Soul: {onboarding_tag}\n"
        f"💡 Type [bold green]/[/bold green] for live command dropdown menu, [bold green]Tab[/bold green] to autocomplete, or [bold green]/think[/bold green] to tune CoT length."
    )
    console.print(Panel(banner_text, border_style="cyan", expand=False))


def show_slash_help() -> None:
    table = Table(title="WorkBuddy-CLI Slash Commands (Type `/` + `Tab` to autocomplete)", show_header=True, header_style="bold cyan")
    table.add_column("Command", style="green", no_wrap=True)
    table.add_column("Description", style="white")
    for _cmd, usage, desc in SLASH_COMMANDS_META:
        table.add_row(usage, desc)
    console.print(table)


def _render_progress_bar(pct: float, width: int = 28) -> str:
    clamped = max(0.0, min(100.0, pct))
    filled = int(round((clamped / 100.0) * width))
    empty = width - filled
    color = "green" if clamped < 45.0 else ("yellow" if clamped < 75.0 else "red")
    return f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim] [bold {color}]{clamped:.1f}%[/bold {color}]"


def show_context_dashboard(
    config: WorkBuddyConfig,
    client: WorkBuddyAgentClient,
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Renders the `/context` (and `/status`) token & memory inspection dashboard.
    """
    footprint = client.prompt_engine.compare_token_footprint()
    full_sys_prompt = client.prompt_engine.render_system_prompt()
    sys_tokens = HistoryEngineeringCompactor.estimate_tokens(full_sys_prompt)
    agents_tokens = footprint["agents_md_tokens"]
    base_sys_tokens = max(0, sys_tokens - agents_tokens)

    hist_json = json.dumps(history, ensure_ascii=False) if history else ""
    hist_tokens = HistoryEngineeringCompactor.estimate_tokens(hist_json) if history else 0
    eng_compacted = HistoryEngineeringCompactor.compact(history) if history else {"estimatedTokens": 0}
    eng_tokens = eng_compacted["estimatedTokens"]

    total_used_tokens = sys_tokens + hist_tokens
    budget = config.max_context_tokens
    suff_threshold = int(budget * config.engineering_compact_sufficiency_pct)
    pre_msg_threshold = int(budget * config.pre_message_compact_pct)
    emerg_threshold = int(budget * config.emergency_compact_pct)

    agents_paths = discover_agents_md(Path(config.workspace_dir))
    agents_path_str = str(agents_paths[0]) if (config.load_agents_md and agents_paths) else "(not mounted)"
    iv = client.memory_manager.collect_identity_vars()

    table = Table(title="📊 WorkBuddy-CLI Context & Token Ledger (/context)", show_header=True, header_style="bold cyan")
    table.add_column("Component (模块)", style="cyan", no_wrap=True)
    table.add_column("Tokens / Status (账本读数)", style="white")
    table.add_column("Notes / Path (详情说明)", style="dim")

    table.add_row(
        "Active Model & Tier",
        f"[bold magenta]{config.model}[/bold magenta] (Tier: [bold]{config.get_model_complexity_tier()}[/bold])",
        f"Endpoint: {config.base_url}",
    )
    table.add_row(
        "Mode / Style / Think / Profile",
        f"mode=[bold]{config.mode}[/bold] | style=[bold]{config.style}[/bold] | think=[bold yellow]{config.thinking_effort}[/bold yellow] | profile=[bold]{config.prompt_profile}[/bold]",
        f"Savings vs WorkBuddy Desktop (32,739 tok): {footprint['token_savings_vs_desktop_pct']}% | API: {json.dumps(config.get_thinking_api_params())}",
    )
    table.add_row(
        "Base System Prompt",
        f"[bold]{base_sys_tokens:,}[/bold] tokens",
        f"Template ({config.prompt_profile}) + SOUL.md + 3-Tier Memory + Tone Style",
    )
    table.add_row(
        "Mounted AGENTS.md",
        f"[bold green]{agents_tokens:,}[/bold green] tokens" if agents_tokens else "[dim]0 tokens[/dim]",
        agents_path_str,
    )
    table.add_row(
        "Conversation History",
        f"[bold yellow]{hist_tokens:,}[/bold yellow] tokens ({len(history)} items)",
        f"After zero-LLM Engineering Scissors: {eng_tokens:,} tokens",
    )
    table.add_row(
        "Total Active Context",
        f"[bold]{total_used_tokens:,}[/bold] / {budget:,} tokens  {_render_progress_bar(total_used_tokens / budget * 100)}",
        "Total Prefill input per turn",
    )
    table.add_row(
        "15% Engineering Compact Line",
        f"{suff_threshold:,} tokens  {_render_progress_bar(hist_tokens / max(1, suff_threshold) * 100)}",
        "Below this line, /compact skips LLM & uses 0-cost rule scissors",
    )
    table.add_row(
        "50% PreMessage / 90% Emergency",
        f"PreMsg: {pre_msg_threshold:,} tok | Emergency: {emerg_threshold:,} tok",
        f"Soul Mode: {iv['WorkspaceIdentityMode']} | Daily Log: {client.memory_manager.daily_log_path().name}",
    )

    console.print(table)
    return {
        "model": config.model,
        "mode": config.mode,
        "style": config.style,
        "profile": config.prompt_profile,
        "base_system_tokens": base_sys_tokens,
        "agents_md_tokens": agents_tokens,
        "agents_md_path": agents_path_str,
        "history_items": len(history),
        "history_tokens": hist_tokens,
        "total_tokens": total_used_tokens,
        "max_context_tokens": budget,
    }


def resolve_slash_command_name(raw_cmd: str) -> Tuple[Optional[str], List[str]]:
    """
    Resolves exact or unique prefix matches for slash commands (e.g. `/cont` -> `/context`).
    Returns `(resolved_cmd, matching_candidates)`.
    """
    cmd_lower = raw_cmd.lower()
    all_cmds = [c[0] for c in SLASH_COMMANDS_META] + ["/exit", "/q"]
    if cmd_lower in all_cmds:
        return cmd_lower, [cmd_lower]
    matches = [c for c in all_cmds if c.startswith(cmd_lower)]
    if len(matches) == 1:
        return matches[0], matches
    return None, matches


def handle_slash_command(
    raw_line: str,
    config: WorkBuddyConfig,
    client: WorkBuddyAgentClient,
    history: List[Dict[str, Any]],
) -> bool:
    """Returns True if session should continue, False if exiting."""
    parts = raw_line.strip().split(maxsplit=1)
    raw_cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    cmd, candidates = resolve_slash_command_name(raw_cmd)
    if cmd is None:
        if candidates:
            console.print(
                f"[yellow]Ambiguous slash command '{raw_cmd}'. Did you mean: "
                f"[bold cyan]{', '.join(candidates)}[/bold cyan]? (Press Tab to autocomplete)[/yellow]"
            )
        else:
            console.print(
                f"[yellow]Unknown slash command: {raw_cmd}. Type [bold green]/help[/bold green] or press [bold green]/[/bold green] to see available commands.[/yellow]"
            )
        return True

    if cmd in ("/quit", "/exit", "/q"):
        console.print("[dim]Goodbye from WorkBuddy-CLI![/dim]")
        return False

    if cmd == "/help":
        show_slash_help()
        return True

    if cmd in ("/context", "/status"):
        show_context_dashboard(config, client, history)
        return True

    if cmd == "/clear":
        count = len(history)
        history.clear()
        console.print(f"[green]✓ Cleared {count} conversation history items.[/green]")
        return True

    if cmd == "/mode":
        if arg.lower() in VALID_MODES:
            config.mode = arg.lower()
            console.print(f"[green]✓ Switched mode to:[/green] [bold]{config.mode}[/bold]")
        else:
            console.print(f"Current mode: [bold]{config.mode}[/bold]. Available: {', '.join(VALID_MODES)}")
        return True

    if cmd in ("/think", "/effort"):
        if arg.lower() in VALID_THINKING_LEVELS:
            config.thinking_effort = arg.lower()
            desc = dict(THINK_CANDIDATES).get(config.thinking_effort, "")
            console.print(
                f"[green]✓ Switched thinking effort to:[/green] [bold yellow]{config.thinking_effort}[/bold yellow] — {desc}\n"
                f"  [dim]API payload params: {json.dumps(config.get_thinking_api_params())}[/dim]"
            )
        else:
            t = Table(title="Thinking / CoT Length Control Levels (/think or /effort)", header_style="bold yellow")
            t.add_column("Level", style="cyan")
            t.add_column("API Payload", style="green")
            t.add_column("Description", style="white")
            orig = config.thinking_effort
            for lvl, desc in THINK_CANDIDATES:
                config.thinking_effort = lvl
                mark = " (active)" if lvl == orig else ""
                t.add_row(f"{lvl}{mark}", json.dumps(config.get_thinking_api_params()), desc)
            config.thinking_effort = orig
            console.print(t)
        return True

    if cmd == "/style":
        styles = client.prompt_engine.list_styles()
        if arg.lower() in styles:
            config.style = arg.lower()
            console.print(f"[green]✓ Switched tone style to:[/green] [bold]{config.style}[/bold] — {styles[config.style]}")
        else:
            t = Table(title="7 Builtin Tone Styles", header_style="bold magenta")
            t.add_column("Style ID", style="cyan")
            t.add_column("Description", style="white")
            for k, v in styles.items():
                mark = " (active)" if k == config.style else ""
                t.add_row(f"{k}{mark}", v)
            console.print(t)
        return True

    if cmd == "/model":
        if arg:
            config.model = arg
            console.print(
                f"[green]✓ Switched model to:[/green] [bold]{config.model}[/bold] "
                f"(Complexity Tier: {config.get_model_complexity_tier()})"
            )
        else:
            console.print(f"Current model: [bold]{config.model}[/bold]. Candidates: {', '.join(m[0] for m in MODEL_CANDIDATES)}")
        return True

    if cmd == "/profile":
        if arg.lower() in VALID_PROMPT_PROFILES:
            config.prompt_profile = arg.lower()
            console.print(f"[green]✓ Switched prompt profile to:[/green] [bold]{config.prompt_profile}[/bold]")
        else:
            audit = client.prompt_engine.compare_token_footprint()
            console.print_json(data=audit)
        return True

    if cmd == "/soul":
        sub = arg.split()
        if not sub or sub[0] == "status":
            iv = client.memory_manager.collect_identity_vars()
            console.print_json(
                data={
                    "WorkspaceIdentityMode": iv["WorkspaceIdentityMode"],
                    "SoulPath": iv["SoulPath"],
                    "BootstrapExists": Path(iv["BootstrapPath"]).exists() if iv["BootstrapPath"] else False,
                    "GlobalMemoryPath": str(client.memory_manager.global_memory_path),
                    "ProjectMemoryPath": str(client.memory_manager.project_memory_path),
                    "DailyLogPath": str(client.memory_manager.daily_log_path()),
                }
            )
        elif sub[0] == "onboard" and len(sub) >= 3:
            res = client.memory_manager.complete_onboarding(agent_name=sub[1], user_name=sub[2])
            console.print("[green]✓ Completed SOUL.md & IDENTITY.md onboarding (BOOTSTRAP.md deleted):[/green]")
            console.print_json(data=res)
        elif sub[0] == "reset":
            client.memory_manager.ensure_persona_workspace(force_reset=True)
            console.print("[yellow]↺ Reset SOUL.md, IDENTITY.md, USER.md, and restored BOOTSTRAP.md.[/yellow]")
        else:
            console.print("Usage: `/soul status` | `/soul onboard <AgentName> <UserName>` | `/soul reset`")
        return True

    if cmd == "/skills":
        if not arg or arg == "list":
            for item in client.skill_router.load_builtin_skills():
                console.print(f"- [bold cyan]{item.id}[/bold cyan]: {item.description}")
        elif arg.startswith("init "):
            sname = arg[5:].strip()
            script = ASSETS_DIR / "skills" / "skill-creator" / "scripts" / "init_skill.py"
            import subprocess
            proc = subprocess.run([sys.executable, str(script), sname, "--path", str(Path.cwd())], text=True, capture_output=True)
            console.print(proc.stdout or proc.stderr)
        elif arg.startswith("validate "):
            sdir = arg[9:].strip()
            script = ASSETS_DIR / "skills" / "skill-creator" / "scripts" / "quick_validate.py"
            import subprocess
            proc = subprocess.run([sys.executable, str(script), sdir], text=True, capture_output=True)
            console.print(proc.stdout or proc.stderr)
        else:
            matches = client.skill_router.match(arg, top_k=5)
            console.print_json(data=matches)
        return True

    if cmd == "/compact":
        eng_only = "--engineering-only" in arg
        force_llm = "--llm" in arg
        compactor = ThreeStageCompactor(
            max_context_tokens=config.max_context_tokens,
            sufficiency_pct=config.engineering_compact_sufficiency_pct,
        )
        sample_hist = history if history else _build_demo_history()
        llm_fn = client.simple_llm_call if (force_llm and config.api_key) else None
        res = compactor.run_compact(sample_hist, engineering_only=eng_only, llm_call_fn=llm_fn, force_llm=force_llm)
        console.print(Panel(res["summary_text"], title=f"/compact ({res['strategy']})", border_style="green"))
        console.print(
            f"[cyan]Original Tokens:[/cyan] {res['original_tokens']} -> "
            f"[green]Compacted Tokens:[/green] {res['compacted_tokens']} "
            f"(Used LLM: {res['used_llm']}, Fixed Hypnosis Bug: {res['fixed_hypnosis_bug']})"
        )
        return True

    if cmd == "/enhance":
        if not arg:
            console.print("[red]Usage: /enhance <raw prompt>[/red]")
            return True
        enhanced = client.enhance_prompt(arg)
        console.print(Panel(enhanced, title="✨ Sparkle Enhanced Prompt (llm:enhancePrompt)", border_style="magenta"))
        return True

    if cmd == "/critic":
        if not arg:
            console.print("[red]Usage: /critic <file_path or draft_text>[/red]")
            return True
        p = Path(arg)
        text = p.read_text(encoding="utf-8") if p.exists() and p.is_file() else arg
        engine = CriticGeneratorEngine()
        llm_fn = client.simple_llm_call if config.api_key else None
        res = engine.run_review(text, llm_call_fn=llm_fn)
        console.print(Markdown(res["markdown_report"]))
        return True

    if cmd == "/research":
        if not arg:
            console.print("[red]Usage: /research <question>[/red]")
            return True
        wf = DeepResearchWorkflow(llm_call_fn=client.simple_llm_call if config.api_key else None)
        res = wf.run(arg)
        console.print(Markdown(res["markdown_report"]))
        return True

    if cmd == "/docx":
        sub = arg.split()
        title = sub[0] if sub else "关于全面推进人工智能安全工程落地的通知"
        out_p = sub[1] if len(sub) > 1 else "gov_red_header.docx"
        sections = [
            {"title": "总体要求", "paragraphs": ["各单位要深入理解大模型系统工程防护规范，严禁在生产环境裸跑无沙箱脚本。"]},
            {"title": "核心防线建设", "paragraphs": ["全面部署 Python 运行时回收站劫持锁与零 LLM HTML AST 门禁。"]},
            {"title": "保障措施与监督", "paragraphs": ["建立多轮盲审强制扣分配额机制，杜绝走过场式自我审查。"]},
        ]
        html_str = render_government_doc_html(title=title, sections=sections)
        ast_rep = review_html_ast(html_str, genre="government-doc")
        docx_info = convert_html_to_docx(html_str, out_p)
        console.print_json(data={"review_html_gate": {"passed": ast_rep.get("passed"), "score": ast_rep.get("score")}, "docx": docx_info})
        return True

    if cmd == "/recalc":
        target_xlsx = arg or "demo_formulas.xlsx"
        if not Path(target_xlsx).exists():
            create_sample_xlsx_without_cache(target_xlsx)
        res = recalc_xlsx_formulas(target_xlsx, apply_aigc_label=True)
        console.print_json(data=res)
        return True

    if cmd == "/team":
        if not arg or arg == "list":
            teams = client.team_engine.list_expert_teams()
            t = Table(title="WorkBuddy 10 Builtin Expert Teams (with Official Homophonic Pun Roster 😂)", header_style="bold yellow")
            t.add_column("Team ID", style="cyan")
            t.add_column("Team Lead (主理人/包工头)", style="green")
            t.add_column("Members (谐音梗花名团员)", style="magenta")
            t.add_column("Description", style="white")
            for tm in teams:
                t.add_row(tm["id"], tm["lead_name"], tm["members_summary"], tm["description"][:60] + "...")
            console.print(t)
            return True

        tokens = arg.split(maxsplit=2)
        team_id = tokens[0] if tokens else "SoftwareCompany"
        t_mode = "spawn"
        task_str = "设计并实现一个支持红涨绿跌的 A 股行情看板组件"
        if len(tokens) >= 2 and tokens[1] in ("spawn", "role-switch"):
            t_mode = tokens[1]
            if len(tokens) == 3:
                task_str = tokens[2]
        elif len(tokens) >= 2:
            task_str = " ".join(tokens[1:])

        llm_fn = client.simple_llm_call if config.api_key else None
        res = client.team_engine.run_team_workflow(team_id=team_id, task_prompt=task_str, mode=t_mode, llm_call_fn=llm_fn)
        console.print(Markdown(res["markdown_report"]))
        return True

    return True


def _build_demo_history() -> List[Dict[str, Any]]:
    return [
        {"role": "user", "content": "<user_query>\n请帮我重构用户鉴权模块并加上单元测试，还要更新接口文档。\n</user_query>"},
        {
            "role": "assistant",
            "content": "好的，我先读取现有的 `auth.py` 并写入重构后的 JWT 校验逻辑，随后再补充单元测试和接口文档。",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps(
                            {
                                "path": "src/auth.py",
                                "content": "def verify_jwt(token: str) -> bool:\n    # 200 lines of implementation...\n" + ("    pass\n" * 60),
                            }
                        ),
                    },
                }
            ],
        },
        {
            "type": "function_call_result",
            "role": "tool",
            "content": "File written successfully (4096 bytes). Huge tool output...",
        },
        {
            "type": "reasoning",
            "content": "Thinking about writing unit tests next, not finished yet...",
        },
    ]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workbuddy",
        description="workbuddy-cli (wb): Open-Source Cross-Platform CLI for WorkBuddyAI (DeepSeek First-Class Citizen)",
    )
    parser.add_argument("prompt", nargs="?", help="Direct prompt to execute in single-shot Agent mode")
    parser.add_argument("--version", action="version", version=f"workbuddy-cli {__version__}")
    parser.add_argument("--mode", choices=VALID_MODES, help="Working mode (craft|ask|expert|plan)")
    parser.add_argument("--style", choices=VALID_STYLES, help="Communication tone style (includes sarcastic)")
    parser.add_argument("--model", help="Model name (default: deepseek-chat)")
    parser.add_argument("--reasoner", action="store_true", help="Shortcut to use deepseek-reasoner (sets thinking=high)")
    parser.add_argument("-t", "--thinking", choices=VALID_THINKING_LEVELS, help="Thinking / CoT length level: off|low|medium|high|max")
    parser.add_argument("--prompt-profile", choices=VALID_PROMPT_PROFILES, help="Prompt profile: lean (~2.6K) vs full (~33K .tpl)")
    parser.add_argument("--token-audit", action="store_true", help="Compare startup token footprint (lean vs full 33K WorkBuddy)")
    parser.add_argument("--context", action="store_true", help="Show the /context token & memory dashboard and exit")
    parser.add_argument("--render-prompt", action="store_true", help="Render and print the assembled System Prompt")
    parser.add_argument("--match-skill", metavar="QUERY", help="Run 0.8*Cosine + 0.2*BM25 skill router on QUERY")
    parser.add_argument("--check-html", metavar="HTML_FILE", help="Run 0-LLM review_html.py AST gatekeeper on HTML file")
    parser.add_argument("--genre", default="government-doc", help="Genre for --check-html (default: government-doc)")
    parser.add_argument("--generate-gov-docx", metavar="OUT_DOCX", help="Generate GB/T 9704 red-header .docx & run review_html gate")
    parser.add_argument("--recalc-xlsx", metavar="XLSX_FILE", help="Recalculate Excel formulas (<v> backfill) & stamp AIGC label")
    parser.add_argument("--compact-demo", action="store_true", help="Run 3-stage /compact demo (showing engineering pruning & fixed LLM prompt)")
    parser.add_argument("--critic", metavar="TEXT_OR_FILE", help="Run 6-step Critic-Generator blind review")
    parser.add_argument("--research", metavar="TOPIC", help="Run 5-phase Deep Research with 2/3 skeptical jury")
    parser.add_argument("--list-teams", action="store_true", help="List all 10 builtin Expert Teams and homophonic pun rosters")
    parser.add_argument("--team", metavar="TEAM_ID", help="Run an Expert Team (e.g. SoftwareCompany led by 齐活林)")
    parser.add_argument("--team-mode", choices=("spawn", "role-switch"), default="spawn", help="Expert Team execution mode (spawn vs role-switch)")
    parser.add_argument("--task", default="实现一个简洁的命令行待办事项管理器", help="Task prompt for --team")
    parser.add_argument("--enhance", metavar="RAW_PROMPT", help="Run sparkle Prompt Enhancer (llm:enhancePrompt)")
    parser.add_argument("--widget-svg", metavar="OUT_SVG", help="Generate a 2.6w-word compliant interactive SVG widget")
    parser.add_argument("--llm", action="store_true", help="Use live LLM API in --compact-demo / --critic / --research / --team")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    config = WorkBuddyConfig.load()
    if args.mode:
        config.mode = args.mode
    if args.style:
        config.style = args.style
    if args.model:
        config.model = args.model
    if args.reasoner:
        config.model = "deepseek-reasoner"
        if not args.thinking:
            config.thinking_effort = "high"
    if args.thinking:
        config.thinking_effort = args.thinking
    if args.prompt_profile:
        config.prompt_profile = args.prompt_profile

    client = WorkBuddyAgentClient(config)

    if args.token_audit:
        audit = client.prompt_engine.compare_token_footprint()
        console.print_json(data=audit)
        return 0

    if args.context:
        show_context_dashboard(config, client, [])
        return 0

    if args.render_prompt:
        rendered = client.prompt_engine.render_system_prompt()
        print(rendered)
        return 0

    if args.match_skill:
        matches = client.skill_router.match(args.match_skill, top_k=5)
        console.print_json(data=matches)
        return 0

    if args.check_html:
        p = Path(args.check_html)
        if not p.exists():
            console.print(f"[red]File not found: {p}[/red]")
            return 2
        rep = review_html_ast(p.read_text(encoding="utf-8"), genre=args.genre)
        console.print_json(data=rep)
        return 0 if rep.get("passed") else 1

    if args.generate_gov_docx:
        sections = [
            {"title": "总体要求", "paragraphs": ["各部门须严格执行 GB/T 9704-2012 党政机关公文格式国家标准与零 LLM HTML AST 门禁。"]},
            {"title": "重点工程防线", "paragraphs": ["全面启用 sitecustomize.py 回收站物理劫持锁与 Excel 公式三层重算回填机制。"]},
            {"title": "考核与问责机制", "paragraphs": ["通过 Critic-Generator 六步盲审隔离与强制扣分配额（min_issues=2, min_instructions=3）保障交付质量。"]},
        ]
        html_str = render_government_doc_html(
            title="关于印发《人工智能客户端工程防护与排版门禁规范》的通知",
            sections=sections,
        )
        html_out = Path(args.generate_gov_docx).with_suffix(".html")
        html_out.parent.mkdir(parents=True, exist_ok=True)
        html_out.write_text(html_str, encoding="utf-8")
        ast_rep = review_html_ast(html_str, genre="government-doc")
        docx_info = convert_html_to_docx(html_str, args.generate_gov_docx)
        console.print_json(
            data={
                "html_path": str(html_out.resolve()),
                "review_html_passed": ast_rep.get("passed"),
                "review_html_score": ast_rep.get("score"),
                "docx": docx_info,
            }
        )
        return 0

    if args.recalc_xlsx:
        xp = Path(args.recalc_xlsx)
        if not xp.exists():
            create_sample_xlsx_without_cache(xp)
        res = recalc_xlsx_formulas(xp, apply_aigc_label=True)
        console.print_json(data=res)
        return 0 if res.get("status") == "success" else 1

    if args.widget_svg:
        nodes = [
            {"title": "1. User Query & AGENTS.md", "subtitle": "SOUL.md + 3-Tier Memory + Tone Style"},
            {"title": "2. RecallIndex (0.8*Cosine + 0.2*BM25)", "subtitle": "Dynamic Tool & Skill Routing"},
            {"title": "3. Safe-Delete & AST Gatekeepers", "subtitle": "sitecustomize.py + review_html.py + recalc.py"},
            {"title": "4. DeepSeek Agentic Execution", "subtitle": "Critic Blind Review & 2/3 Jury Verification"},
        ]
        res = generate_architecture_svg_widget(
            title="WorkBuddy-CLI Architecture Pipeline",
            nodes=nodes,
            theme=config.ide_theme,
            output_path=Path(args.widget_svg),
        )
        console.print_json(data={"saved_path": res["saved_path"], "audit": res["audit"]})
        return 0

    if args.compact_demo:
        compactor = ThreeStageCompactor()
        demo_hist = _build_demo_history()
        llm_fn = client.simple_llm_call if (args.llm and config.api_key) else None
        res = compactor.run_compact(demo_hist, engineering_only=not args.llm, llm_call_fn=llm_fn, force_llm=args.llm)
        console.print_json(data=res)
        return 0

    if args.critic:
        p = Path(args.critic)
        draft = p.read_text(encoding="utf-8") if (p.exists() and p.is_file()) else args.critic
        engine = CriticGeneratorEngine()
        llm_fn = client.simple_llm_call if (args.llm and config.api_key) else None
        res = engine.run_review(draft, llm_call_fn=llm_fn)
        console.print(Markdown(res["markdown_report"]))
        return 0

    if args.research:
        llm_fn = client.simple_llm_call if (args.llm and config.api_key) else None
        wf = DeepResearchWorkflow(llm_call_fn=llm_fn)
        res = wf.run(args.research)
        console.print(Markdown(res["markdown_report"]))
        return 0

    if args.list_teams:
        handle_slash_command("/team list", config, client, [])
        return 0

    if args.team:
        llm_fn = client.simple_llm_call if (args.llm and config.api_key) else None
        res = client.team_engine.run_team_workflow(
            team_id=args.team,
            task_prompt=args.task,
            mode=args.team_mode,
            llm_call_fn=llm_fn,
        )
        console.print(Markdown(res["markdown_report"]))
        return 0

    if args.enhance:
        enhanced = client.enhance_prompt(args.enhance)
        console.print(Panel(enhanced, title="✨ Sparkle Enhanced Prompt (llm:enhancePrompt)", border_style="magenta"))
        return 0

    if args.prompt:
        def _on_tool(tname: str, targs: str, tres: str):
            console.print(f"  [dim]🔧 Tool Call:[/dim] [bold yellow]{tname}[/bold yellow]({targs[:120]})")

        turn = client.chat_turn(args.prompt, history=[], on_tool_call=_on_tool)
        if turn.get("reasoning"):
            console.print(Panel(turn["reasoning"], title="💭 Reasoning Trace", border_style="dim"))
        console.print(Markdown(turn["reply"]))
        return 0

    # Interactive REPL with prompt_toolkit live `/` dropdown & Tab autocomplete
    print_banner(config, client.memory_manager)
    history: List[Dict[str, Any]] = []
    pt_session = build_prompt_session(client) if sys.stdin.isatty() else None

    while True:
        try:
            prompt_label = f"wb ({config.mode}/{config.style}/think:{config.thinking_effort})> "
            if pt_session is not None:
                print()
                user_in = pt_session.prompt(
                    [("class:prompt", prompt_label)],
                ).strip()
            else:
                user_in = console.input(f"\n[bold cyan]{prompt_label}[/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Exiting WorkBuddy-CLI.[/dim]")
            break
        if not user_in:
            continue
        if user_in.startswith("/"):
            if not handle_slash_command(user_in, config, client, history):
                break
            continue

        def _on_tool_repl(tname: str, targs: str, tres: str):
            console.print(f"  [dim]🔧 {tname}[/dim] {targs[:100]}")

        try:
            turn = client.chat_turn(user_in, history=history, on_tool_call=_on_tool_repl)
            if turn.get("reasoning"):
                console.print(Panel(turn["reasoning"], title="💭 Reasoning Trace", border_style="dim"))
            console.print(Markdown(turn["reply"]))
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
