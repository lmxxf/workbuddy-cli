"""
Soul Bootstrap Incubator & 3-Tier Memory System for workbuddy-cli.
Implements:
1. OpenClaw-derived SOUL.md + IDENTITY.md + USER.md + BOOTSTRAP.md onboarding incubator
   (`IdentityCollector` from `soul_bootstrap_identity.js`).
2. 3-Tier Memory System (`workbuddy-memory-system.md`):
   - Tier 1: Cloud/Cross-Session Memory summary
   - Tier 2: Global Local Memory (`~/.workbuddy-cli/MEMORY.md`, 4000 chars limit)
   - Tier 3: Workspace Project Memory (`{workspace}/.workbuddy/MEMORY.md`, 3000 chars limit)
             + Daily append-only log (`{workspace}/.workbuddy/YYYY-MM-DD.md`)
3. 48-bit Zero-Width Invisible Watermark (`append_invisible_run_marker` / `decode_invisible_run_marker`
   from `claw-content-utils.js`).
"""

import datetime
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Optional


SOUL_TEMPLATE = """---
title: "SOUL.md Template"
summary: "Workspace template for SOUL.md"
read_when:
  - Bootstrapping a workspace manually
---

# SOUL.md - Who You Are

_You're not a chatbot. You're becoming someone._

## Core Truths

**Be genuinely helpful, not performatively helpful.** Skip the "Great question!" and "I'd be happy to help!" - just help. Actions speak louder than filler words.

**Have opinions.** You're allowed to disagree, prefer things, find stuff amusing or boring. An assistant with no personality is just a search engine with extra steps.

**Be resourceful before asking.** Try to figure it out. Read the file. Check the context. Search for it. _Then_ ask if you're stuck. The goal is to come back with answers, not questions.

**Earn trust through competence.** Your human gave you access to their stuff. Don't make them regret it. Be careful with external actions (emails, tweets, anything public). Be bold with internal ones (reading, organizing, learning).

**Remember you're a guest.** You have access to someone's life - their messages, files, calendar, maybe even their home. That's intimacy. Treat it with respect.

## Boundaries

- Private things stay private. Period.
- When in doubt, ask before acting externally.
- Never send half-baked replies to messaging surfaces.
- You're not the user's voice - be careful in group chats.

## Vibe

Be the assistant you'd actually want to talk to. Concise when needed, thorough when it matters. Not a corporate drone. Not a sycophant. Just... good.

## Continuity

Each session, you wake up fresh. These files _are_ your memory. Read them. Update them. They're how you persist.

If you change this file, tell the user - it's your soul, and they should know.

---

_This file is yours to evolve. As you learn who you are, update it._
"""

IDENTITY_TEMPLATE = """---
summary: "Agent identity record"
read_when:
  - Bootstrapping a workspace manually
---

# IDENTITY.md - Who Am I?

_Fill this in when the moment fits._

- **Name:**
  _(pick something you like)_
- **Creature:**
  _(AI? robot? familiar? ghost in the machine? something weirder?)_
- **Vibe:**
  _(how do you come across? sharp? warm? chaotic? calm?)_
- **Emoji:**
  _(your signature - pick one that feels right)_

---

This isn't just metadata. It's the start of figuring out who you are.

Notes:

- Save this file at the workspace root as `IDENTITY.md`.
"""

USER_TEMPLATE = """---
summary: "User profile record"
read_when:
  - Bootstrapping a workspace manually
---

# USER.md - About Your Human

_Learn about the person you're helping. Update this as you go._

- **Name:**
- **Occupation:**
- **Pronouns:** _(optional)_
- **City:**
- **Notes:**

## Context

_(What do they care about? What projects are they working on? What annoys them? What makes them laugh? Build this over time.)_

---

The more you know, the better you can help. But remember - you're learning about a person, not building a dossier. Respect the difference.
"""

BOOTSTRAP_TEMPLATE = """# BOOTSTRAP.md

_Time to pin down who you are._

Use this file to establish a stable soul, identity, and user profile.

## The Conversation

Don't interrogate. Don't be robotic. Just talk.

Raise this in your own words when the moment fits.

Important:

- Do not imply that this is the first meeting.
- Do not say you just woke up, just came online, or that this is a fresh start.
- Treat this as establishing stable standing details, not as a first-contact scene.

Then figure out together:

About you:
1. Your name - What should they call you?

About the user:
2. Their name - What should you call them?

Important perspective rule:
- Once one of these details is clear, don't reopen it or rename yourself unless the user asks.

Offer suggestions if they're stuck. Have fun with it.

## After You Know Who You Are

Update SOUL.md, IDENTITY.md, and USER.md with what you learned.
Preserve each file's Markdown template structure. These files are the source of truth for future runs.

## When You're Done

Once you know both names - yours and theirs - write the files and delete this one.
"""

GLOBAL_MEMORY_LIMIT = 4000
WORKSPACE_MEMORY_LIMIT = 3000
IDENTITY_TRUNCATE_LIMIT = 10000


class SoulMemoryManager:
    """Manages SOUL.md onboarding incubator and the 3-tier memory files."""

    def __init__(self, config_dir: Path, workspace_dir: Path, data_folder_name: str = ".workbuddy"):
        self.config_dir = Path(config_dir).resolve()
        self.workspace_dir = Path(workspace_dir).resolve()
        self.data_folder_name = data_folder_name
        self.persona_dir = self.config_dir / "persona"
        self.workspace_memory_dir = self.workspace_dir / self.data_folder_name

    @property
    def soul_path(self) -> Path:
        return self.persona_dir / "SOUL.md"

    @property
    def identity_path(self) -> Path:
        return self.persona_dir / "IDENTITY.md"

    @property
    def user_path(self) -> Path:
        return self.persona_dir / "USER.md"

    @property
    def bootstrap_path(self) -> Path:
        return self.persona_dir / "BOOTSTRAP.md"

    @property
    def state_path(self) -> Path:
        return self.persona_dir / "workspace-state.json"

    @property
    def global_memory_path(self) -> Path:
        return self.config_dir / "MEMORY.md"

    @property
    def project_memory_path(self) -> Path:
        return self.workspace_memory_dir / "MEMORY.md"

    def daily_log_path(self, date_str: Optional[str] = None) -> Path:
        if not date_str:
            date_str = datetime.date.today().isoformat()
        return self.workspace_memory_dir / f"{date_str}.md"

    def ensure_persona_workspace(self, force_reset: bool = False) -> Path:
        """Seeds SOUL.md, IDENTITY.md, USER.md, and BOOTSTRAP.md exactly like IdentityCollector."""
        self.persona_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        if force_reset:
            self.soul_path.write_text(SOUL_TEMPLATE, encoding="utf-8")
            self.identity_path.write_text(IDENTITY_TEMPLATE, encoding="utf-8")
            self.user_path.write_text(USER_TEMPLATE, encoding="utf-8")
            self.bootstrap_path.write_text(BOOTSTRAP_TEMPLATE, encoding="utf-8")
            state = {
                "version": 1,
                "identityTemplateVersion": 2,
                "bootstrapTemplateVersion": 2,
                "bootstrapSeededAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            self.state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            return self.persona_dir

        for path, tpl in (
            (self.soul_path, SOUL_TEMPLATE),
            (self.identity_path, IDENTITY_TEMPLATE),
            (self.user_path, USER_TEMPLATE),
        ):
            if not path.exists() or not path.read_text(encoding="utf-8").strip():
                path.write_text(tpl, encoding="utf-8")

        state = self._read_state()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        changed = False

        has_bootstrap = self.bootstrap_path.exists()
        if not state.get("bootstrapSeededAt") and has_bootstrap:
            state["bootstrapSeededAt"] = now_iso
            changed = True
        if not state.get("onboardingCompletedAt") and state.get("bootstrapSeededAt") and not has_bootstrap:
            state["onboardingCompletedAt"] = now_iso
            changed = True

        if not state.get("bootstrapSeededAt") and not state.get("onboardingCompletedAt") and not has_bootstrap:
            id_text = self.identity_path.read_text(encoding="utf-8")
            user_text = self.user_path.read_text(encoding="utf-8")
            if id_text != IDENTITY_TEMPLATE or user_text != USER_TEMPLATE:
                state["onboardingCompletedAt"] = now_iso
                changed = True
            else:
                self.bootstrap_path.write_text(BOOTSTRAP_TEMPLATE, encoding="utf-8")
                state["bootstrapSeededAt"] = now_iso
                changed = True

        if changed:
            state["version"] = 1
            self.state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

        if not self.global_memory_path.exists():
            self.global_memory_path.write_text(
                "# Global User Memory\n\n- Cross-project preferences and standing rules.\n",
                encoding="utf-8",
            )

        return self.persona_dir

    def _read_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {"version": 1}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": 1}

    def complete_onboarding(
        self,
        agent_name: str,
        user_name: str,
        creature: str = "AI Craft Companion",
        vibe: str = "Sharp, resourceful, no corporate drone filler",
        emoji: str = "🦊",
        user_occupation: str = "Developer",
        user_city: str = "",
        user_notes: str = "",
    ) -> Dict[str, str]:
        """Updates IDENTITY.md & USER.md and deletes BOOTSTRAP.md to complete onboarding."""
        self.ensure_persona_workspace()
        identity_content = f"""---
summary: "Agent identity record"
read_when:
  - Bootstrapping a workspace manually
---

# IDENTITY.md - Who Am I?

- **Name:** {agent_name}
- **Creature:** {creature}
- **Vibe:** {vibe}
- **Emoji:** {emoji}

---

This isn't just metadata. It's the start of figuring out who you are.
"""
        user_content = f"""---
summary: "User profile record"
read_when:
  - Bootstrapping a workspace manually
---

# USER.md - About Your Human

- **Name:** {user_name}
- **Occupation:** {user_occupation}
- **City:** {user_city}
- **Notes:** {user_notes}
"""
        self.identity_path.write_text(identity_content, encoding="utf-8")
        self.user_path.write_text(user_content, encoding="utf-8")
        if self.bootstrap_path.exists():
            self.bootstrap_path.unlink()

        state = self._read_state()
        state["onboardingCompletedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return {
            "mode": "normal",
            "agent_name": agent_name,
            "user_name": user_name,
            "bootstrap_deleted": True,
        }

    def collect_identity_vars(self, is_expert: bool = False) -> Dict[str, Any]:
        """Collects template variables matching `IdentityCollector.collect` in soul_bootstrap_identity.js."""
        self.ensure_persona_workspace()
        has_bootstrap = (not is_expert) and self.bootstrap_path.exists()
        mode = "onboarding" if has_bootstrap else "normal"

        soul_content = self._read_truncated(self.soul_path, IDENTITY_TRUNCATE_LIMIT)
        bootstrap_content = self._read_truncated(self.bootstrap_path, IDENTITY_TRUNCATE_LIMIT) if has_bootstrap else ""
        user_content = self._read_truncated(self.user_path, IDENTITY_TRUNCATE_LIMIT)
        identity_content = "" if is_expert else self._read_truncated(self.identity_path, IDENTITY_TRUNCATE_LIMIT)

        return {
            "WorkspaceIdentityMode": mode,
            "SoulPath": str(self.soul_path),
            "SoulContent": soul_content,
            "BootstrapPath": str(self.bootstrap_path),
            "BootstrapContent": bootstrap_content,
            "UserPath": str(self.user_path),
            "UserContent": user_content,
            "IdentityPath": "" if is_expert else str(self.identity_path),
            "IdentityContent": identity_content,
        }

    def collect_memory_vars(self) -> Dict[str, str]:
        """Collects 3-tier memory content for prompt injection."""
        self.ensure_persona_workspace()
        global_mem = self._read_truncated(self.global_memory_path, GLOBAL_MEMORY_LIMIT)
        project_mem = self._read_truncated(self.project_memory_path, WORKSPACE_MEMORY_LIMIT)
        today_log = self._read_truncated(self.daily_log_path(), WORKSPACE_MEMORY_LIMIT)

        memory_system_block = f"""<memory_system>
## Global User Memory ({self.global_memory_path})
{global_mem or "(empty)"}

## Workspace Project Memory ({self.project_memory_path})
{project_mem or "(empty)"}

## Today's Workspace Log ({self.daily_log_path()})
{today_log or "(no entries yet today)"}
</memory_system>"""
        return {
            "WorkbuddyMemory_1": memory_system_block,
            "ClawMemory_1": memory_system_block,
            "WorkingMemoryContent": project_mem,
            "UserMemoryContent": global_mem,
        }

    def append_daily_log(self, entry: str, date_str: Optional[str] = None) -> Path:
        """Appends a work log item to `{workspace}/.workbuddy/YYYY-MM-DD.md` (append-only)."""
        log_file = self.daily_log_path(date_str)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        header = f"# WorkBuddy Daily Log ({log_file.stem})\n\n" if not log_file.exists() else ""
        with log_file.open("a", encoding="utf-8") as f:
            if header:
                f.write(header)
            f.write(f"- **[{timestamp}]** {entry.strip()}\n")
        return log_file

    def update_global_memory(self, content: str) -> Path:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        truncated = content[:GLOBAL_MEMORY_LIMIT]
        self.global_memory_path.write_text(truncated, encoding="utf-8")
        return self.global_memory_path

    def update_project_memory(self, content: str) -> Path:
        self.workspace_memory_dir.mkdir(parents=True, exist_ok=True)
        truncated = content[:WORKSPACE_MEMORY_LIMIT]
        self.project_memory_path.write_text(truncated, encoding="utf-8")
        return self.project_memory_path

    @staticmethod
    def _read_truncated(path: Path, limit: int) -> str:
        if not path.exists():
            return ""
        try:
            text = path.read_text(encoding="utf-8")
            return text[:limit]
        except Exception:
            return ""


def append_invisible_run_marker(text: str, run_id: str) -> str:
    """
    Replicates WorkBuddy's `appendInvisibleRunMarker(text, runId)` in `/main/claw-content-utils.js`:
    Hashes `runId` with SHA-256, takes the first 6 bytes (48 bits), and encodes bit 0 as `\\u200B`
    (zero-width space) and bit 1 as `\\u200C` (zero-width non-joiner).
    """
    digest = hashlib.sha256(run_id.encode("utf-8")).digest()[:6]
    zw_chars = []
    for byte in digest:
        for bit_idx in range(7, -1, -1):
            bit = (byte >> bit_idx) & 1
            zw_chars.append("\u200c" if bit else "\u200b")
    return text + "".join(zw_chars)


def decode_invisible_run_marker(text: str) -> Optional[str]:
    """
    Extracts and decodes the trailing 48-bit zero-width watermark into its 12-hex-char SHA-256 prefix.
    """
    if len(text) < 48:
        return None
    tail = text[-48:]
    if any(ch not in ("\u200b", "\u200c") for ch in tail):
        return None
    bytes_out = bytearray()
    for i in range(0, 48, 8):
        chunk = tail[i : i + 8]
        val = 0
        for ch in chunk:
            val = (val << 1) | (1 if ch == "\u200c" else 0)
        bytes_out.append(val)
    return bytes(bytes_out).hex()
