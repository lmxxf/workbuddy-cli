"""
Template & Prompt Rendering Engine for workbuddy-cli.
Supports:
1. Dual Prompt Profiles (`lean` vs `full`):
   - `full`: 1:1 reproduction of Tencent WorkBuddyAI's ~32,739-token `.tpl` startup prompt
     (`workbuddy-prompt.tpl`, `workbuddy-expert-prompt.tpl`, `user-context-identity.tpl`).
   - `lean` (Default): Solves WorkBuddy's 33K zombie-token bloat by keeping only the high-signal
     core (~2.2K tokens: SOUL.md identity, AGENTS.md, 8 Personal Files Safety rules, A-share Red-Up/Green-Down,
     Model-aware complexity gating, active tone style) and dynamically injecting heavy skills/guidelines
     ONLY when triggered by `RecallIndex`!
2. Native `AGENTS.md` / `CLAUDE.md` discovery & injection (like Codex / Antigravity CLI).
3. 7 Tone Styles (`sarcastic`, `efficient`, `professional`, `socratic`, `friendly`, `creative`, `straightforward`).
4. Sparkle Prompt Enhancer (`llm:enhancePrompt`).
"""

import platform
import re
from pathlib import Path
from typing import Dict, Any, Optional

from .config import WorkBuddyConfig, ASSETS_DIR, VALID_STYLES, discover_agents_md
from .memory import SoulMemoryManager
from .compactor import HistoryEngineeringCompactor


ENHANCE_PROMPT_SYSTEM = """You are a Prompt Engineering Expert specializing in improving user prompts for a development and office AI assistant.
Your goal is to rewrite the user's raw input into a clear, structured, high-signal instruction.

Rules:
1. Keep the enhanced prompt strictly under 800 characters.
2. Focus ONLY on WHAT needs to be done and clear acceptance criteria; DO NOT dictate HOW to implement it or invent unrequested tech stacks.
3. CRITICAL PRIORITY - LANGUAGE CONSISTENCY:
   - If the user writes in Chinese, output 100% in Chinese.
   - If the user writes in English, output 100% in English.
   - If the user mixes Chinese and English terms, preserve that natural mix.
   - NEVER translate the user's primary language into another language.
4. Output ONLY the enhanced prompt text itself, without quotes, preambles, or explanations."""


LEAN_CORE_TEMPLATE = """This conversation is powered by {{ modelName }} ({{ productName }} Open-Source CLI — Lean High-Signal Profile).

Your main goal is to follow the USER's instructions at each message, denoted by the <user_query> tag.
You have full agentic tool access (`bash`, `read_file`, `write_file`, `edit_file`, `glob_search`, `grep_search`, `web_search`, `web_fetch`, `show_widget`, `office_docx`, `recalc_xlsx`, `switch_role`). When the user asks to search the web or verify real-time/specific facts, proactively call `web_search` and `web_fetch`. Act decisively and verify your work.

{{ WorkbuddyMemory_1 }}

<personal_files_safety>
**CRITICAL: Operations on personal files (Desktop, Downloads, Documents, Home) are HIGH-RISK.**
1. **No-Go Zones**: NEVER recursively delete Desktop, Downloads, Documents, Home, or system directories (`/`, `~/.config`, `~/.ssh`).
2. **Scan = Read-Only**: Pass one for cleanup requests is strictly read-only listing.
3. **Warn + List + Confirm**: Before any destructive action, warn in bold: **"⚠️ 此操作非常危险，可能导致不可逆的数据丢失！"**
4. **Trash, Not Delete**: All deletions are automatically redirected to OS Trash via `sitecustomize.py` safe-delete shim.
5. **No Script Files on Windows**: Never generate `.ps1`/`.bat` scripts with non-ASCII paths.
</personal_files_safety>

{% if not IsOversea %}
<regional_conventions>
Assume the user is a Chinese user by default unless stated otherwise. When building finance, stock market, or investment tools:
- **Stock price increase (涨) → Red (红色)**; Stock price decrease (跌) → Green (绿色).
- Default currency symbol: ¥ (CNY/RMB).
</regional_conventions>
{% endif %}

<instructions_for_visualizer>
When the user asks to explain, teach, compare architectures, or visualize data, use `show_widget` to generate streaming-safe SVG (`viewBox="0 0 680 H"`, no gradients/shadows/comments, `rect_width = max(title_chars * 7, subtitle_chars * 6) + 24`).
# Model-aware complexity gating ({{ modelName }} -> tier: {{ ComplexityTier }})
- **Claude, GPT, DeepSeek**: No ceiling. Complex diagrams, multi-step interactive workflows, rich visualizations.
- **GLM, KIMI**: Cap at moderate complexity. Standard charts, clean SVGs.
- **Hunyuan, Minimax**: Cap at minimal complexity. Simple static SVG diagrams only.
</instructions_for_visualizer>
"""


class PromptEngine:
    """Renders WorkBuddy `.tpl` system prompts (`lean` or `full`), loads `AGENTS.md`, and manages tone styles."""

    def __init__(self, config: WorkBuddyConfig, memory_manager: Optional[SoulMemoryManager] = None):
        self.config = config
        self.templates_dir = ASSETS_DIR / "templates"
        self.styles_dir = self.templates_dir / "style"
        self.fragments_dir = self.templates_dir / "fragments"
        self.memory_manager = memory_manager or SoulMemoryManager(
            Path(config.config_dir),
            Path(config.workspace_dir),
            config.data_folder_name,
        )

    def load_style_content(self, style_name: Optional[str] = None) -> str:
        style = (style_name or self.config.style or "efficient").lower()
        if style not in VALID_STYLES:
            style = "efficient"
        style_path = self.styles_dir / f"style-{style}.md"
        if not style_path.exists():
            return ""
        raw = style_path.read_text(encoding="utf-8")
        cleaned = re.sub(r"^---\n.*?\n---\n*", "", raw, flags=re.DOTALL)
        return cleaned.strip()

    def list_styles(self) -> Dict[str, str]:
        result = {}
        for style in VALID_STYLES:
            p = self.styles_dir / f"style-{style}.md"
            desc = style
            if p.exists():
                text = p.read_text(encoding="utf-8")
                m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
                if m:
                    desc = m.group(1).strip()
            result[style] = desc
        return result

    def load_agents_md_block(self, include_parent_fallback: bool = False) -> str:
        """Discovers `AGENTS.md` / `CLAUDE.md` in workspace and formats it for system prompt injection."""
        if not self.config.load_agents_md:
            return ""
        paths = discover_agents_md(Path(self.config.workspace_dir), load_global_fallback=include_parent_fallback)
        if not paths:
            return ""
        blocks = []
        for p in paths:
            try:
                content = p.read_text(encoding="utf-8").strip()
                if content:
                    blocks.append(f'<agents_md path="{p}">\n{content}\n</agents_md>')
            except Exception:
                continue
        return "\n\n".join(blocks)

    def select_template_file(self, mode: Optional[str] = None) -> Path:
        m = (mode or self.config.mode or "craft").lower()
        mapping = {
            "craft": "workbuddy-prompt.tpl",
            "coding": "workbuddy-craft-coding-prompt.tpl",
            "ask": "workbuddy-ask-prompt.tpl",
            "expert": "workbuddy-expert-prompt.tpl",
            "plan": "workbuddy-prompt.tpl",
            "quick": "workbuddy-quick-prompt.tpl",
        }
        filename = mapping.get(m, "workbuddy-prompt.tpl")
        return self.templates_dir / filename

    def build_template_context(
        self,
        mode: Optional[str] = None,
        style: Optional[str] = None,
        custom_prompt: str = "",
    ) -> Dict[str, Any]:
        active_mode = (mode or self.config.mode or "craft").lower()
        is_expert = active_mode == "expert"

        identity_vars = self.memory_manager.collect_identity_vars(is_expert=is_expert)
        memory_vars = self.memory_manager.collect_memory_vars()
        tone_content = self.load_style_content(style)

        ctx: Dict[str, Any] = {
            "modelName": self.config.model,
            "productName": self.config.product_name,
            "dataFolderName": self.config.data_folder_name,
            "ResponseLanguage": self.config.language,
            "IsWindows": platform.system().lower().startswith("win"),
            "IsOversea": self.config.is_oversea,
            "CloudMemoryPlatformEnabled": False,
            "ToneStyleContent": tone_content,
            "UserCustomPrompt": custom_prompt,
            "UserInstructionsContent": "",
            "ToolResultPresentationPrompt": "",
            "AvailableSkillsContent": "",
            "McpServersContent": "",
            "productFeatures": {
                "DisableMultimodalGeneration": False,
            },
            "IDETheme": self.config.ide_theme,
            "ComplexityTier": self.config.get_model_complexity_tier(),
        }
        ctx.update(identity_vars)
        ctx.update(memory_vars)
        return ctx

    def render_template_text(self, template_text: str, ctx: Dict[str, Any]) -> str:
        def _replace_include(match):
            inc_path = match.group(1)
            frag_name = Path(inc_path).name
            frag_file = self.fragments_dir / frag_name
            if frag_file.exists():
                return frag_file.read_text(encoding="utf-8")
            return ""

        resolved_text = template_text
        for _ in range(3):
            if "{% include" not in resolved_text:
                break
            resolved_text = re.sub(r'\{%\s*include\s+"([^"]+)"\s*%\}', _replace_include, resolved_text)

        try:
            import jinja2

            env = jinja2.Environment(
                autoescape=False,
                undefined=jinja2.ChainableUndefined,
            )
            tpl = env.from_string(resolved_text)
            return tpl.render(**ctx)
        except Exception:
            out = resolved_text
            for k, v in ctx.items():
                if isinstance(v, (str, int, float, bool)):
                    out = re.sub(r"\{\{\s*" + re.escape(k) + r"(?:\s*\|\s*trim)?\s*\}\}", str(v), out)
            return out

    def render_system_prompt(
        self,
        mode: Optional[str] = None,
        style: Optional[str] = None,
        profile: Optional[str] = None,
        custom_prompt: str = "",
        matched_skills_block: str = "",
    ) -> str:
        """
        Assembles the System Prompt under either `lean` (on-demand ~2.2K tokens) or
        `full` (original WorkBuddy `.tpl` ~33K tokens) profile.
        """
        active_mode = (mode or self.config.mode or "craft").lower()
        active_profile = (profile or self.config.prompt_profile or "lean").lower()
        ctx = self.build_template_context(mode=active_mode, style=style, custom_prompt=custom_prompt)

        if active_profile == "lean" and active_mode not in ("ask",):
            rendered_main = self.render_template_text(LEAN_CORE_TEMPLATE, ctx)
        else:
            main_tpl_path = self.select_template_file(active_mode)
            main_raw = main_tpl_path.read_text(encoding="utf-8") if main_tpl_path.exists() else ""
            rendered_main = self.render_template_text(main_raw, ctx)
            if "# Model-aware complexity gating" not in rendered_main:
                gating_block = f"""
# Model-aware complexity gating
{self.config.product_name} calibrates the upper bound of Visualizer output complexity to the model being used ({self.config.model} -> tier: {ctx['ComplexityTier']}):
- **Claude, GPT, DeepSeek**: No ceiling. Complex diagrams, multi-step interactive workflows, ambitious D3/Three.js visualizations, rich interactivity.
- **GLM, KIMI**: Cap at moderate complexity. Standard charts, straightforward diagrams, clean SVGs. Avoid deeply nested interactivity or heavy JS logic.
- **Hunyuan, Minimax**: Cap at minimal complexity. Simple SVG diagrams, basic static charts, minimal interactivity. Prioritize speed and reliability over visual richness.
"""
                if "</instructions_for_visualizer>" in rendered_main:
                    rendered_main = rendered_main.replace(
                        "</instructions_for_visualizer>",
                        gating_block + "\n</instructions_for_visualizer>",
                    )
                else:
                    rendered_main += "\n" + gating_block
            if "<regional_conventions>" not in rendered_main and not self.config.is_oversea:
                rendered_main += """
<regional_conventions>
Assume the user is a Chinese user by default unless stated otherwise. When building finance, stock market, or investment-related tools and visualizations:
- **Stock price increase (涨) → Red (红色)**; Stock price decrease (跌) → Green (绿色). This is the Chinese stock market convention and is opposite to the US/European convention. Always default to this unless the user explicitly requests otherwise.
- Currency formatting: Use ¥ (CNY/RMB) as the default currency symbol for financial tools.
</regional_conventions>
"""

        id_tpl_name = (
            "user-context-expert-identity.tpl"
            if active_mode == "expert"
            else "user-context-identity.tpl"
        )
        id_tpl_path = self.templates_dir / id_tpl_name
        rendered_identity = ""
        if id_tpl_path.exists():
            rendered_identity = self.render_template_text(
                id_tpl_path.read_text(encoding="utf-8"), ctx
            )
        if ctx.get("ToneStyleContent") and "<tone_and_style>" not in rendered_identity:
            rendered_identity += f"""

<tone_and_style>
You MUST adopt the following tone and communication style in ALL your responses.
These guidelines override your default behavior and take priority over general style preferences.

{ctx['ToneStyleContent']}

The style affects HOW information is delivered, not WHAT information is delivered. Accuracy, correctness, and helpfulness must remain uncompromised regardless of style.
</tone_and_style>"""

        agents_md_block = self.load_agents_md_block()

        user_info_block = f"""
<user_info>
- OS: {platform.system()} {platform.release()}
- Workspace: {self.config.workspace_dir}
- IDE Theme: {self.config.ide_theme}
- Active Mode: {active_mode}
- Prompt Profile: {active_profile}
- Active Style: {style or self.config.style}
- Model: {self.config.model} (Visualizer Complexity Tier: {ctx['ComplexityTier']})
</user_info>
"""

        parts = [
            rendered_main.strip(),
            rendered_identity.strip(),
            agents_md_block.strip(),
            user_info_block.strip(),
        ]
        if matched_skills_block.strip():
            parts.append(matched_skills_block.strip())

        return "\n\n".join(p for p in parts if p)

    def compare_token_footprint(self) -> Dict[str, Any]:
        """Compares startup token overhead between `lean` profile and original WorkBuddy `full` profile (excluding external AGENTS.md)."""
        orig_flag = self.config.load_agents_md
        try:
            self.config.load_agents_md = False
            lean_prompt = self.render_system_prompt(profile="lean")
            full_prompt = self.render_system_prompt(profile="full")
        finally:
            self.config.load_agents_md = orig_flag

        agents_block = self.load_agents_md_block()
        agents_tokens = HistoryEngineeringCompactor.estimate_tokens(agents_block)
        lean_tokens = HistoryEngineeringCompactor.estimate_tokens(lean_prompt)
        full_tokens = HistoryEngineeringCompactor.estimate_tokens(full_prompt)
        # Note: Original WorkBuddy desktop also injects ~20K tokens of 100+ MCP/tool schemas on startup (= 32,739 total)
        wb_desktop_baseline = 32739
        return {
            "lean_chars": len(lean_prompt),
            "lean_tokens": lean_tokens,
            "full_tpl_chars": len(full_prompt),
            "full_tpl_tokens": full_tokens,
            "agents_md_tokens": agents_tokens,
            "workbuddy_desktop_hello_tokens": wb_desktop_baseline,
            "token_savings_vs_desktop_pct": round((1.0 - lean_tokens / wb_desktop_baseline) * 100, 1),
        }
