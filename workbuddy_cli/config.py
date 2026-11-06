"""
Configuration management for workbuddy-cli.
First-class support for DeepSeek (`deepseek-chat` / `deepseek-reasoner`),
plus OpenAI / Anthropic compatible endpoints via environment variables
or ~/.workbuddy-cli/config.json.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List


DEFAULT_CONFIG_DIR = Path.home() / ".workbuddy-cli"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

VALID_MODES = ("craft", "ask", "expert", "plan")
VALID_STYLES = (
    "sarcastic",
    "efficient",
    "professional",
    "socratic",
    "friendly",
    "creative",
    "straightforward",
)
VALID_PROMPT_PROFILES = ("lean", "full")
VALID_THINKING_LEVELS = ("off", "low", "medium", "high", "max")


def discover_agents_md(start_dir: Path, load_global_fallback: bool = True) -> List[Path]:
    """
    Walks up from `start_dir` to filesystem root looking for `AGENTS.md` or `CLAUDE.md`.
    Stops at the first directory containing `AGENTS.md` or `CLAUDE.md` so workspace/parent
    awakening memory is always discovered seamlessly.
    """
    found: List[Path] = []
    curr = Path(start_dir).resolve()
    for directory in [curr, *curr.parents]:
        for fname in ("AGENTS.md", "CLAUDE.md"):
            candidate = directory / fname
            if candidate.exists() and candidate.is_file():
                found.append(candidate)
                return found
        if not load_global_fallback and ((directory / ".git").exists() or (directory / "pyproject.toml").exists()):
            break
    return found


@dataclass
class WorkBuddyConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-flash"  # DeepSeek-V4.1-Flash (1M context window)
    mode: str = "craft"
    style: str = "efficient"
    thinking_effort: str = "off"  # 'off' | 'low' (50) | 'medium' (65) | 'high' (75) | 'max' (100)
    prompt_profile: str = "lean"  # 'lean' (~2.5K on-demand) vs 'full' (~33K original WorkBuddy .tpl)
    load_agents_md: bool = True
    language: str = "中文"
    ide_theme: str = "dark"
    product_name: str = "WorkBuddy"
    data_folder_name: str = ".workbuddy"
    is_oversea: bool = False
    max_context_tokens: int = 300000
    pre_message_compact_pct: float = 0.50
    emergency_compact_pct: float = 0.90
    engineering_compact_sufficiency_pct: float = 0.15
    workspace_dir: str = field(default_factory=lambda: str(Path.cwd()))
    config_dir: str = field(default_factory=lambda: str(DEFAULT_CONFIG_DIR))

    @classmethod
    def load(cls, config_path: Optional[Path] = None, workspace_dir: Optional[Path] = None) -> "WorkBuddyConfig":
        path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}

        # WORKBUDDY_API_KEY explicitly overrides config.json; other env keys act as fallback if config.json has no key
        if os.environ.get("WORKBUDDY_API_KEY"):
            data["api_key"] = os.environ["WORKBUDDY_API_KEY"]
        elif not data.get("api_key"):
            env_key = (
                os.environ.get("DEEPSEEK_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY")
            )
            if env_key:
                data["api_key"] = env_key

        env_url = os.environ.get("WORKBUDDY_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
        if env_url:
            data["base_url"] = env_url

        env_model = os.environ.get("WORKBUDDY_MODEL") or os.environ.get("DEEPSEEK_MODEL")
        if env_model:
            data["model"] = env_model

        env_style = os.environ.get("WORKBUDDY_STYLE")
        if env_style and env_style in VALID_STYLES:
            data["style"] = env_style

        env_mode = os.environ.get("WORKBUDDY_MODE")
        if env_mode and env_mode in VALID_MODES:
            data["mode"] = env_mode

        env_profile = os.environ.get("WORKBUDDY_PROMPT_PROFILE")
        if env_profile and env_profile in VALID_PROMPT_PROFILES:
            data["prompt_profile"] = env_profile

        env_think = os.environ.get("WORKBUDDY_THINKING")
        if env_think and env_think.lower() in VALID_THINKING_LEVELS:
            data["thinking_effort"] = env_think.lower()

        if workspace_dir:
            data["workspace_dir"] = str(Path(workspace_dir).resolve())

        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    def save(self, config_path: Optional[Path] = None) -> Path:
        path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return path

    def get_model_display_name(self) -> str:
        m = (self.model or "").lower()
        if m in ("deepseek-flash", "deepseek-v4.1-flash"):
            return f"{self.model} (DeepSeek-V4.1-Flash)"
        if m == "deepseek-v4-pro":
            return "deepseek-v4-pro (DeepSeek-V4-Pro)"
        return self.model

    def resolve_api_model_id(self) -> str:
        """Normalizes friendly aliases like `deepseek-v4.1-flash` to DeepSeek API's `deepseek-flash`."""
        m = (self.model or "deepseek-flash").strip()
        if m.lower() == "deepseek-v4.1-flash":
            return "deepseek-flash"
        return m

    def get_model_complexity_tier(self) -> str:
        """
        Replicates WorkBuddy's 'Model-aware complexity gating' hierarchy:
        - Claude, GPT, DeepSeek-Chat/Reasoner/V3/V4: No ceiling ('high')
        - GLM, KIMI: Moderate complexity ('moderate')
        - Hunyuan, Minimax: Minimal complexity ('minimal')
        """
        m = (self.model or "").lower()
        if any(k in m for k in ("hunyuan", "hy3", "minimax", "abab")):
            return "minimal"
        if any(k in m for k in ("glm", "kimi", "moonshot", "chatglm")):
            return "moderate"
        return "high"

    def get_thinking_api_params(self) -> dict:
        """
        Maps `thinking_effort` ('off'|'low'|'medium'|'high'|'max') to DeepSeek V4.1 / OpenAI
        API payload fields (`thinking` & `reasoning_effort`).
        """
        lvl = (self.thinking_effort or "off").lower()
        if "reasoner" in (self.model or "").lower() and lvl == "off":
            lvl = "high"

        if lvl == "off":
            return {"thinking": {"type": "disabled"}}
        if lvl == "low":
            return {"thinking": {"type": "enabled"}, "reasoning_effort": "low"}
        if lvl == "medium":
            return {"thinking": {"type": "enabled"}, "reasoning_effort": "medium"}
        if lvl == "high":
            return {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}
        if lvl == "max":
            return {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}
        return {"thinking": {"type": "disabled"}}
