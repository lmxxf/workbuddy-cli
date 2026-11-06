#!/usr/bin/env python3
"""
Main CLI & Interactive REPL entrypoint for `workbuddy-cli` (`workbuddy` / `wb`).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from . import __version__
from .config import WorkBuddyConfig, VALID_MODES, VALID_STYLES, VALID_PROMPT_PROFILES, ASSETS_DIR
from .memory import SoulMemoryManager, append_invisible_run_marker, decode_invisible_run_marker
from .prompt_engine import PromptEngine
from .compactor import ThreeStageCompactor, HistoryEngineeringCompactor, FIXED_CONTEXT_SUMMARY_PROMPT
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


def print_banner(config: WorkBuddyConfig, memory_mgr: SoulMemoryManager) -> None:
    id_vars = memory_mgr.collect_identity_vars()
    onboarding_tag = (
        "[bold yellow]ONBOARDING (BOOTSTRAP.md active)[/bold yellow]"
        if id_vars["WorkspaceIdentityMode"] == "onboarding"
        else "[bold green]INCUBATED (SOUL.md active)[/bold green]"
    )
    tier = config.get_model_complexity_tier()
    banner_text = (
        f"[bold cyan]WorkBuddy Open-Source CLI[/bold cyan] v{__version__}  "
        f"| Model: [bold magenta]{config.model}[/bold magenta] (Visualizer Tier: [bold]{tier}[/bold])\n"
        f"Mode: [bold]{config.mode}[/bold] | Style: [bold]{config.style}[/bold] | "
        f"Prompt Profile: [bold]{config.prompt_profile}[/bold] | Soul: {onboarding_tag}\n"
        f"Type [bold green]/help[/bold green] for slash commands, or ask anything directly."
    )
    console.print(Panel(banner_text, border_style="cyan", expand=False))


def show_slash_help() -> None:
    table = Table(title="WorkBuddy-CLI Slash Commands", show_header=True, header_style="bold cyan")
    table.add_column("Command", style="green", no_wrap=True)
    table.add_column("Description", style="white")
    rows = [
        ("/mode <craft|ask|expert|plan>", "Switch working mode (Agent Craft, Read-Only Ask, Expert, Plan)"),
        ("/style <style_name>", f"Switch tone style: {', '.join(VALID_STYLES)} (includes sarcastic roaster!)"),
        ("/model <model_name>", "Switch LLM model (e.g. deepseek-chat, deepseek-reasoner)"),
        ("/profile <lean|full>", "Switch prompt profile: lean (~2.2K on-demand) vs full (~33K original .tpl)"),
        ("/team [TeamId] [spawn|role-switch] <task>", "Run Expert Team (齐活林/许清楚/高见远/寇豆码/严过关) in hub-spawn or in-place role-switch mode"),
        ("/compact [--engineering-only|--llm]", "Run 3-stage context compactor (with fixed task-completion hypnosis bug)"),
        ("/research <topic>", "Run 5-phase Deep Research workflow with 2/3 skeptical jury verification"),
        ("/critic <file_or_text>", "Run 6-step Critic-Generator blind review (mandatory min_issues=2, min_instructions=3)"),
        ("/docx <title> [out.docx]", "Run 3-stage GB/T 9704 red-header Docx pipeline + 0-LLM review_html AST gate"),
        ("/recalc <xlsx_path>", "Recalculate Excel formulas (<f> -> <v> cache) + GB 45438-2025 AIGC implicit label"),
        ("/skills [query|init|validate]", "Search skills via 0.8*Cosine+0.2*BM25 or manage skills via skill-creator"),
        ("/soul [status|onboard|reset]", "Inspect or onboard SOUL.md + IDENTITY.md + USER.md + 3-tier memory"),
        ("/enhance <raw_prompt>", "Rewrite prompt via WorkBuddy's sparkle Prompt Enhancer (llm:enhancePrompt)"),
        ("/quit, /exit", "Exit interactive session"),
    ]
    for cmd, desc in rows:
        table.add_row(cmd, desc)
    console.print(table)


def handle_slash_command(
    raw_line: str,
    config: WorkBuddyConfig,
    client: WorkBuddyAgentClient,
    history: List[Dict[str, Any]],
) -> bool:
    """Returns True if session should continue, False if exiting."""
    parts = raw_line.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/quit", "/exit", "/q"):
        console.print("[dim]Goodbye from WorkBuddy-CLI![/dim]")
        return False

    if cmd == "/help":
        show_slash_help()
        return True

    if cmd == "/mode":
        if arg.lower() in VALID_MODES:
            config.mode = arg.lower()
            console.print(f"[green]✓ Switched mode to:[/green] [bold]{config.mode}[/bold]")
        else:
            console.print(f"Current mode: [bold]{config.mode}[/bold]. Available: {', '.join(VALID_MODES)}")
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
            console.print(f"Current model: [bold]{config.model}[/bold]")
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
        if not arg:
            for item in client.skill_router.load_builtin_skills():
                console.print(f"- [bold cyan]{item.id}[/bold cyan]: {item.description}")
        elif arg.startswith("init "):
            sname = arg[5:].strip()
            from .assets.skills import skill_creator  # fallback via subprocess
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

    console.print(f"[yellow]Unknown slash command: {cmd}. Type /help for available commands.[/yellow]")
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
    parser.add_argument("--reasoner", action="store_true", help="Shortcut to use deepseek-reasoner")
    parser.add_argument("--prompt-profile", choices=VALID_PROMPT_PROFILES, help="Prompt profile: lean (~2.2K) vs full (~33K .tpl)")
    parser.add_argument("--token-audit", action="store_true", help="Compare startup token footprint (lean vs full 33K WorkBuddy)")
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
    if args.prompt_profile:
        config.prompt_profile = args.prompt_profile

    client = WorkBuddyAgentClient(config)

    if args.token_audit:
        audit = client.prompt_engine.compare_token_footprint()
        console.print_json(data=audit)
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

    # Interactive REPL
    print_banner(config, client.memory_manager)
    history: List[Dict[str, Any]] = []
    while True:
        try:
            user_in = console.input(f"\n[bold cyan]wb ({config.mode}/{config.style})>[/bold cyan] ").strip()
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
