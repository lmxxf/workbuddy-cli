"""
Session Persistence & `/resume` Lifecycle Manager for workbuddy-cli.
Stores conversations in `~/.workbuddy-cli/sessions/<session_id>.json`,
enabling automatic per-turn persistence, `/resume` (by ID, `#index`, or `latest`),
`/sessions` listing, `/new` session reset, and `/rename` title customization.
"""

import datetime
import json
import re
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from .config import WorkBuddyConfig
from .compactor import HistoryEngineeringCompactor


def _clean_user_query(raw_text: str) -> str:
    if not raw_text:
        return ""
    m = re.search(r"<user_query>\n?([\s\S]*?)\n?</user_query>", raw_text)
    cleaned = m.group(1).strip() if m else raw_text.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


class SessionManager:
    """Manages persistent conversation sessions in `~/.workbuddy-cli/sessions/`."""

    def __init__(self, config_dir: str | Path):
        self.config_dir = Path(config_dir).resolve()
        self.sessions_dir = self.config_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.current_session_id: str = self.generate_session_id()
        self.current_title: str = ""
        self.created_at: str = datetime.datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def generate_session_id() -> str:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        short_hex = uuid.uuid4().hex[:4]
        return f"{stamp}-{short_hex}"

    def start_new_session(self, title: str = "") -> str:
        self.current_session_id = self.generate_session_id()
        self.current_title = title.strip()
        self.created_at = datetime.datetime.now().isoformat(timespec="seconds")
        return self.current_session_id

    def session_file(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def derive_title(self, history: List[Dict[str, Any]]) -> str:
        if self.current_title:
            return self.current_title
        for msg in history:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    txt = _clean_user_query(content)
                    if txt:
                        return txt[:48] + ("…" if len(txt) > 48 else "")
        return "Untitled Session"

    def save_session(
        self,
        config: WorkBuddyConfig,
        history: List[Dict[str, Any]],
        session_id: Optional[str] = None,
    ) -> Path:
        """Saves the active conversation history and metadata atomically."""
        sid = session_id or self.current_session_id
        self.current_session_id = sid
        title = self.derive_title(history)
        now_str = datetime.datetime.now().isoformat(timespec="seconds")

        user_turns = sum(1 for m in history if m.get("role") == "user")
        hist_tokens = HistoryEngineeringCompactor.estimate_tokens(
            json.dumps(history, ensure_ascii=False)
        ) if history else 0

        payload = {
            "session_id": sid,
            "title": title,
            "created_at": self.created_at,
            "updated_at": now_str,
            "workspace_dir": config.workspace_dir,
            "model": config.model,
            "mode": config.mode,
            "style": config.style,
            "thinking_effort": config.thinking_effort,
            "prompt_profile": config.prompt_profile,
            "user_turns": user_turns,
            "message_count": len(history),
            "estimated_tokens": hist_tokens,
            "history": history,
        }

        target = self.session_file(sid)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(target)
        return target

    def list_sessions(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Lists saved sessions sorted by `updated_at` descending (newest first)."""
        items: List[Dict[str, Any]] = []
        if not self.sessions_dir.exists():
            return items
        for f in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                items.append(
                    {
                        "session_id": data.get("session_id", f.stem),
                        "title": data.get("title") or "Untitled Session",
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "workspace_dir": data.get("workspace_dir", ""),
                        "model": data.get("model", "deepseek-chat"),
                        "mode": data.get("mode", "craft"),
                        "style": data.get("style", "efficient"),
                        "thinking_effort": data.get("thinking_effort", "off"),
                        "user_turns": data.get("user_turns", 0),
                        "message_count": data.get("message_count", 0),
                        "estimated_tokens": data.get("estimated_tokens", 0),
                        "file_path": str(f),
                    }
                )
            except Exception:
                continue
        items.sort(key=lambda x: (x.get("updated_at", ""), x.get("session_id", "")), reverse=True)
        return items[:limit]

    def resolve_and_load(self, target_spec: str = "latest") -> Optional[Dict[str, Any]]:
        """
        Resolves a session by:
          - `"latest"` (most recent session)
          - 1-based index `"1"`, `"#1"`, `"2"`, etc. from `list_sessions()`
          - Exact `session_id` or unique prefix/substring match
        Returns the full session dict (including `history`) or `None`.
        """
        spec = (target_spec or "latest").strip()
        sessions = self.list_sessions(limit=100)
        if not sessions:
            return None

        chosen_id: Optional[str] = None
        if spec.lower() in ("latest", "last"):
            chosen_id = sessions[0]["session_id"]
        else:
            idx_str = spec.lstrip("#")
            if idx_str.isdigit():
                idx = int(idx_str) - 1
                if 0 <= idx < len(sessions):
                    chosen_id = sessions[idx]["session_id"]

        if not chosen_id:
            # Try exact match or prefix match on session_id or title
            for s in sessions:
                if s["session_id"] == spec or s["session_id"].startswith(spec):
                    chosen_id = s["session_id"]
                    break
            if not chosen_id:
                for s in sessions:
                    if spec.lower() in s["session_id"].lower() or spec.lower() in s["title"].lower():
                        chosen_id = s["session_id"]
                        break

        if not chosen_id:
            return None

        f = self.session_file(chosen_id)
        if not f.exists():
            return None
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            self.current_session_id = data.get("session_id", chosen_id)
            self.current_title = data.get("title", "")
            self.created_at = data.get("created_at", self.created_at)
            return data
        except Exception:
            return None

    def delete_session(self, target_spec: str) -> bool:
        loaded = self.resolve_and_load(target_spec)
        if not loaded:
            return False
        sid = loaded["session_id"]
        f = self.session_file(sid)
        if f.exists():
            f.unlink()
            return True
        return False
