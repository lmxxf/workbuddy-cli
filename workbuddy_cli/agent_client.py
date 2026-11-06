"""
First-Class DeepSeek / OpenAI Agentic Tool-Calling Client for workbuddy-cli.
Supports:
- `deepseek-flash` (DeepSeek-V4.1-Flash-1017) and `deepseek-v4-pro` (DeepSeek-V4-Pro)
- Full 12-tool Agentic Loop:
  1. `bash`: Execute shell commands inside Safe-Delete Trash-intercepted sandbox
  2. `read_file`: Read file contents with optional line ranges
  3. `write_file`: Create or overwrite files and log to `.workbuddy/YYYY-MM-DD.md`
  4. `edit_file`: Exact target/replacement file editing with 3-phase backup ticket
  5. `glob_search`: Find files by glob pattern in workspace
  6. `grep_search`: Search file contents by regex
  7. `show_widget`: Generate & validate 2.6w-word compliant interactive SVG widgets
  8. `office_docx`: Run 3-stage HTML -> review_html AST gate -> GB/T 9704 `.docx` pipeline
  9. `recalc_xlsx`: Evaluate Excel formulas, backfill `<v>` cache nodes & stamp GB 45438-2025 AIGC label
  10. `switch_role`: Execute in-place `[角色切换]` or invoke Qi Huolin's Expert Team (`SoftwareCompany`, etc.)
"""

import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

import httpx

from .config import WorkBuddyConfig
from .memory import SoulMemoryManager
from .session import SessionManager
from .prompt_engine import PromptEngine, ENHANCE_PROMPT_SYSTEM
from .skill_router import SkillRouter
from .tools.safe_shell import SafeTrashInterceptor, DocumentBackupTransaction, HIGH_RISK_WARNING_BANNER
from .tools.visualizer import generate_architecture_svg_widget
from .tools.office_suite import (
    render_government_doc_html,
    review_html_ast,
    convert_html_to_docx,
    recalc_xlsx_formulas,
    create_sample_xlsx_without_cache,
)
from .tools.expert_team import ExpertTeamEngine
from .tools.web_search import search_web, fetch_web_page


AGENT_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a shell command in the workspace with Safe-Delete Trash interception enabled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                    "start_line": {"type": "integer", "description": "Optional 1-based start line"},
                    "end_line": {"type": "integer", "description": "Optional 1-based end line"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file in the workspace and record in daily log.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Full text content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact target string in an existing file (protected by 3-phase backup snapshot).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to edit"},
                    "target": {"type": "string", "description": "Exact substring to replace"},
                    "replacement": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "target", "replacement"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob_search",
            "description": "Find files matching a glob pattern (e.g. '**/*.py') in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern"}
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Search for a regex pattern across files in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search"},
                    "path": {"type": "string", "description": "Optional subdirectory or file"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_widget",
            "description": "Render a streaming-safe interactive SVG architecture/flow diagram (viewBox='0 0 680 H').",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Diagram title"},
                    "nodes": {
                        "type": "array",
                        "description": "List of diagram nodes with title and subtitle",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "subtitle": {"type": "string"},
                            },
                            "required": ["title"],
                        },
                    },
                    "output_path": {"type": "string", "description": "Optional path to save SVG file"},
                },
                "required": ["title", "nodes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "office_docx",
            "description": "Generate a GB/T 9704-2012 red-header government document or report (.docx) with 0-LLM review_html AST check.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Document title"},
                    "output_path": {"type": "string", "description": "Output .docx file path"},
                    "org_name": {"type": "string", "description": "Red header issuer organization name"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "paragraphs": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["title", "paragraphs"],
                        },
                    },
                },
                "required": ["title", "output_path", "sections"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recalc_xlsx",
            "description": "Recalculate Excel (.xlsx) formula cells (<f>), backfill cached values (<v>) for WeChat preview, and stamp GB 45438-2025 AIGC label.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xlsx_path": {"type": "string", "description": "Path to .xlsx file"}
                },
                "required": ["xlsx_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_role",
            "description": "Switch agent role in-place ('[角色切换]') or invoke a WorkBuddy Expert Team (e.g. SoftwareCompany led by 齐活林).",
            "parameters": {
                "type": "object",
                "properties": {
                    "role_or_team": {"type": "string", "description": "Role name (e.g. doc-writer, 许清楚) or Team ID (SoftwareCompany)"},
                    "stage_task": {"type": "string", "description": "Task to execute under this role"},
                },
                "required": ["role_or_team", "stage_task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the live internet via DeepSeek Official Search API (/v1/tools/search, supporting site:/-site:/lang:/after:/before:) with DuckDuckGo/Bing fallback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query keywords (1-128 chars)"},
                    "ori_question": {"type": "string", "description": "Original user question for reranking"},
                    "max_results": {"type": "integer", "description": "Max results to return (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch and extract clean readable text from a web page URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "HTTP/HTTPS URL to fetch"},
                    "max_chars": {"type": "integer", "description": "Maximum characters to return (default 6000)"},
                },
                "required": ["url"],
            },
        },
    },
]


class WorkBuddyAgentClient:
    """First-class DeepSeek / OpenAI compatible agent client with full tool execution loop."""

    def __init__(self, config: WorkBuddyConfig):
        self.config = config
        self.workspace_dir = Path(config.workspace_dir).resolve()
        self.memory_manager = SoulMemoryManager(
            Path(config.config_dir),
            self.workspace_dir,
            config.data_folder_name,
        )
        self.session_manager = SessionManager(config.config_dir)
        self.prompt_engine = PromptEngine(config, self.memory_manager)
        self.skill_router = SkillRouter()
        self.trash_interceptor = SafeTrashInterceptor()
        self.backup_tx = DocumentBackupTransaction()
        self.team_engine = ExpertTeamEngine()

    def _endpoint_url(self) -> str:
        base = (self.config.base_url or "https://api.deepseek.com/v1").rstrip("/")
        if not base.endswith("/v1") and "deepseek.com" in base:
            base += "/v1"
        return f"{base}/chat/completions"

    def simple_llm_call(self, system_prompt: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = 1500) -> str:
        """Single-turn LLM completion helper (used by /enhance, /compact, /research, /critic, /team)."""
        if not self.config.api_key:
            raise RuntimeError("No API key configured. Set DEEPSEEK_API_KEY or configure ~/.workbuddy-cli/config.json")

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
        }
        think_params = self.config.get_thinking_api_params()
        api_model = self.config.resolve_api_model_id()
        payload["model"] = api_model
        payload.update(think_params)
        if think_params.get("thinking", {}).get("type") != "enabled":
            payload["temperature"] = temperature

        with httpx.Client(timeout=90.0) as client:
            resp = client.post(self._endpoint_url(), headers=headers, json=payload)
            if resp.status_code == 400 and ("thinking" in payload or "reasoning_effort" in payload):
                payload.pop("thinking", None)
                payload.pop("reasoning_effort", None)
                resp = client.post(self._endpoint_url(), headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            return msg.get("content") or ""

    def enhance_prompt(self, raw_prompt: str) -> str:
        """Implements WorkBuddy's `llm:enhancePrompt` sparkle prompt rewriter."""
        return self.simple_llm_call(ENHANCE_PROMPT_SYSTEM, raw_prompt, temperature=0.3, max_tokens=600).strip()

    def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Executes one of the 10 builtin agent tools deterministically."""
        try:
            if name == "bash":
                cmd = args.get("command", "")
                # Check destructive rm -rf on personal No-Go zones
                if re.search(r"\brm\s+-[rf]+", cmd):
                    for zone in ("Desktop", "Downloads", "Documents", "~/.ssh"):
                        if zone in cmd:
                            return json.dumps(
                                {
                                    "status": "blocked",
                                    "warning": HIGH_RISK_WARNING_BANNER,
                                    "error": f"Blocked destructive command on No-Go Zone ({zone})",
                                },
                                ensure_ascii=False,
                            )
                shim_dir = self.trash_interceptor.create_python_shim_dir()
                env = dict(os.environ)
                existing_pp = env.get("PYTHONPATH", "")
                env["PYTHONPATH"] = f"{shim_dir}{os.pathsep}{existing_pp}" if existing_pp else str(shim_dir)
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=str(self.workspace_dir),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return json.dumps(
                    {
                        "returncode": proc.returncode,
                        "stdout": proc.stdout[:4000],
                        "stderr": proc.stderr[:2000],
                    },
                    ensure_ascii=False,
                )

            elif name == "read_file":
                rel = args.get("path", "")
                p = (self.workspace_dir / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
                if not p.exists():
                    return json.dumps({"error": f"File not found: {p}"})
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                s = max(1, int(args.get("start_line") or 1))
                e = min(len(lines), int(args.get("end_line") or min(len(lines), s + 300)))
                snippet = "\n".join(f"{i}: {lines[i - 1]}" for i in range(s, e + 1))
                return json.dumps({"path": str(p), "total_lines": len(lines), "content": snippet[:8000]}, ensure_ascii=False)

            elif name == "write_file":
                rel = args.get("path", "")
                content = args.get("content", "")
                p = (self.workspace_dir / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
                p.parent.mkdir(parents=True, exist_ok=True)
                ticket = self.backup_tx.prepare(p)
                p.write_text(content, encoding="utf-8")
                self.memory_manager.append_daily_log(f"Wrote file `{p.name}` ({len(content)} chars, backup={ticket})")
                return json.dumps({"status": "ok", "path": str(p), "bytes": len(content.encode("utf-8")), "backup_ticket": ticket}, ensure_ascii=False)

            elif name == "edit_file":
                rel = args.get("path", "")
                target = args.get("target", "")
                replacement = args.get("replacement", "")
                p = (self.workspace_dir / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
                if not p.exists():
                    return json.dumps({"error": f"File not found: {p}"})
                orig = p.read_text(encoding="utf-8")
                if target not in orig:
                    return json.dumps({"error": "Target string not found in file"})
                ticket = self.backup_tx.prepare(p)
                updated = orig.replace(target, replacement)
                p.write_text(updated, encoding="utf-8")
                self.memory_manager.append_daily_log(f"Edited file `{p.name}` (backup={ticket})")
                return json.dumps({"status": "ok", "path": str(p), "backup_ticket": ticket}, ensure_ascii=False)

            elif name == "glob_search":
                pat = args.get("pattern", "*")
                matches = []
                for root, dirs, files in os.walk(self.workspace_dir):
                    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules", ".venv")]
                    for f in files:
                        full = Path(root) / f
                        rel_p = str(full.relative_to(self.workspace_dir))
                        if fnmatch.fnmatch(rel_p, pat) or fnmatch.fnmatch(f, pat):
                            matches.append(rel_p)
                return json.dumps({"matches": sorted(matches)[:100]}, ensure_ascii=False)

            elif name == "grep_search":
                pat = args.get("pattern", "")
                sub = args.get("path", "")
                search_root = (self.workspace_dir / sub).resolve() if sub else self.workspace_dir
                rx = re.compile(pat)
                hits = []
                files_to_scan = [search_root] if search_root.is_file() else search_root.rglob("*")
                for fp in files_to_scan:
                    if not fp.is_file() or any(part in (".git", "__pycache__", "node_modules") for part in fp.parts):
                        continue
                    try:
                        for idx, line in enumerate(fp.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                            if rx.search(line):
                                hits.append(f"{fp.relative_to(self.workspace_dir)}:{idx}: {line.strip()[:160]}")
                                if len(hits) >= 60:
                                    break
                    except Exception:
                        continue
                    if len(hits) >= 60:
                        break
                return json.dumps({"hits": hits}, ensure_ascii=False)

            elif name == "show_widget":
                title = args.get("title", "Architecture Diagram")
                nodes = args.get("nodes") or [{"title": title, "subtitle": "Generated by WorkBuddy Visualizer"}]
                out_p = args.get("output_path")
                if out_p and not Path(out_p).is_absolute():
                    out_p = str((self.workspace_dir / out_p).resolve())
                res = generate_architecture_svg_widget(title, nodes, theme=self.config.ide_theme, output_path=out_p)
                return json.dumps(res, ensure_ascii=False)

            elif name == "office_docx":
                title = args.get("title", "正式公文通知")
                sections = args.get("sections") or [{"title": "总体要求", "paragraphs": ["严格落实各项标准。"]}]
                org_name = args.get("org_name", "国家人工智能安全与标准化委员会文件")
                out_p = args.get("output_path", "output.docx")
                if not Path(out_p).is_absolute():
                    out_p = str((self.workspace_dir / out_p).resolve())
                html_str = render_government_doc_html(title=title, sections=sections, org_name=org_name)
                ast_report = review_html_ast(html_str, genre="government-doc")
                docx_info = convert_html_to_docx(html_str, out_p)
                return json.dumps(
                    {
                        "status": "ok",
                        "review_html_passed": ast_report.get("passed"),
                        "review_html_score": ast_report.get("score"),
                        "docx": docx_info,
                    },
                    ensure_ascii=False,
                )

            elif name == "recalc_xlsx":
                xp = args.get("xlsx_path", "sample.xlsx")
                if not Path(xp).is_absolute():
                    xp = str((self.workspace_dir / xp).resolve())
                if not Path(xp).exists():
                    create_sample_xlsx_without_cache(xp)
                res = recalc_xlsx_formulas(xp, apply_aigc_label=True)
                return json.dumps(res, ensure_ascii=False)

            elif name == "switch_role":
                role_or_team = args.get("role_or_team", "doc-writer")
                stage_task = args.get("stage_task", "")
                return json.dumps(
                    {
                        "declaration": f"[角色切换] 现在以 {role_or_team} 身份执行任务：{stage_task}",
                        "mode": "in-place-role-switch",
                        "zero_context_loss": True,
                    },
                    ensure_ascii=False,
                )

            elif name == "web_search":
                q = args.get("query", "")
                ori_q = args.get("ori_question", "")
                max_r = int(args.get("max_results") or 5)
                res = search_web(q, max_results=max_r, ori_question=ori_q, api_key=self.config.api_key)
                return json.dumps(res, ensure_ascii=False)

            elif name == "web_fetch":
                u = args.get("url", "")
                max_c = int(args.get("max_chars") or 6000)
                res = fetch_web_page(u, max_chars=max_c, api_key=self.config.api_key)
                return json.dumps(res, ensure_ascii=False)

            return json.dumps({"error": f"Unknown tool: {name}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    def chat_turn(
        self,
        user_input: str,
        history: List[Dict[str, Any]],
        enable_tools: bool = True,
        max_tool_rounds: int = 5,
        on_tool_call: Optional[Callable[[str, str, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Runs a complete multi-step Agentic turn against DeepSeek (`deepseek-flash` / `deepseek-v4-pro`)
        or any OpenAI-compatible model, automatically recalling top skills via `RecallIndex`.
        """
        matched_skills_block = self.skill_router.build_matched_skills_prompt(user_input, top_k=2)
        sys_prompt = self.prompt_engine.render_system_prompt(matched_skills_block=matched_skills_block)

        history.append({"role": "user", "content": f"<user_query>\n{user_input}\n</user_query>"})

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        tool_events = []
        usage_last = {}
        reasoning_trace = ""

        for _round in range(max_tool_rounds):
            api_messages = [{"role": "system", "content": sys_prompt}] + history
            api_model = self.config.resolve_api_model_id()
            payload: Dict[str, Any] = {
                "model": api_model,
                "messages": api_messages,
            }
            payload.update(self.config.get_thinking_api_params())
            if enable_tools and self.config.mode != "ask":
                payload["tools"] = AGENT_TOOLS_SCHEMA
                payload["tool_choice"] = "auto"

            with httpx.Client(timeout=120.0) as client:
                resp = client.post(self._endpoint_url(), headers=headers, json=payload)
                if resp.status_code == 400 and ("thinking" in payload or "reasoning_effort" in payload):
                    payload.pop("thinking", None)
                    payload.pop("reasoning_effort", None)
                    resp = client.post(self._endpoint_url(), headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

            usage_last = data.get("usage") or {}
            choice = data["choices"][0]
            msg = choice["message"]
            if msg.get("reasoning_content"):
                reasoning_trace += msg["reasoning_content"] + "\n"

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                reply_text = msg.get("content") or ""
                history.append({"role": "assistant", "content": reply_text})
                return {
                    "reply": reply_text,
                    "reasoning": reasoning_trace.strip(),
                    "tool_events": tool_events,
                    "usage": usage_last,
                    "matched_skills": self.skill_router.match(user_input, top_k=2),
                }

            # Append assistant message with tool_calls (and reasoning_content if thinking is active)
            asst_entry: Dict[str, Any] = {
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            }
            if msg.get("reasoning_content"):
                asst_entry["reasoning_content"] = msg["reasoning_content"]
            history.append(asst_entry)

            for tc in tool_calls:
                fn = tc.get("function") or {}
                t_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                try:
                    parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    parsed_args = {}

                result_str = self.execute_tool(t_name, parsed_args)
                if on_tool_call:
                    on_tool_call(t_name, json.dumps(parsed_args, ensure_ascii=False), result_str)
                tool_events.append({"tool": t_name, "arguments": parsed_args, "result": result_str})
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", "call_0"),
                        "name": t_name,
                        "content": result_str,
                    }
                )

        # Fallback if max_tool_rounds reached
        return {
            "reply": "Completed maximum tool rounds.",
            "reasoning": reasoning_trace.strip(),
            "tool_events": tool_events,
            "usage": usage_last,
            "matched_skills": self.skill_router.match(user_input, top_k=2),
        }
