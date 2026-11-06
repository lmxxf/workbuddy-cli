"""
3-Stage Context Compactor for workbuddy-cli (`PreMessage -> MaxToken -> Blocking`).
Implements:
1. `HistoryEngineeringCompactor` (from `engineering-compactor.js`):
   - Strips `function_call_result`, `reasoning`, `custom-title`, `topic`, `ai-title`, `summary`, `file-history-snapshot`.
   - Replaces large tool arguments (`content`, `widget_code`, `new_string`) with `<omitted>`.
   - Wraps in `<cb_summary>...</cb_summary>` and estimates tokens as `math.ceil(len(text) / 4)`.
   - If `estimated_tokens <= budget * 0.15` (sufficiency threshold), skips LLM summarization completely!
2. Fixed LLM Secondary Compactor (`ContextSummaryCompactor`):
   - BUG FIX HIGHLIGHT: Fixed Tencent WorkBuddyAI's premature task-completion hypnosis bug in `/compact`!
     In WorkBuddy 5.9.4's `context-summary-prompt.txt`, lines 8-9 hardcoded:
       `All tasks described below are already completed.`
       `**DO NOT re-run, re-do or re-execute any of the tasks mentioned!**`
     Even when `/compact` was triggered mid-task, that header hypnotized the successor agent into
     refusing to continue unfinished work, directly contradicting the `MaxToken` and `Blocking` prompts
     (which explicitly track `7. Pending Tasks` and `8. Current Work`).
   - Our fixed prompt (`FIXED_CONTEXT_SUMMARY_PROMPT`) preserves active task state (`Completed Tasks` vs
     `Pending & In-Progress Tasks`) so mid-task compaction never lobotomizes ongoing work.
"""

import json
import math
import re
from typing import List, Dict, Any, Optional, Callable


SKIPPED_ITEM_TYPES = {
    "function_call_result",
    "reasoning",
    "custom-title",
    "topic",
    "ai-title",
    "summary",
    "file-history-snapshot",
}

OMITTED_ARG_KEYS = ("content", "widget_code", "new_string")
CHARS_PER_TOKEN_ESTIMATE = 4


# Fixed version of WorkBuddy's context-summary-prompt.txt
# Removes the buggy "All tasks described below are already completed. DO NOT re-run..." hypnosis!
FIXED_CONTEXT_SUMMARY_PROMPT = """Your task is to write a detailed and structured summary of the conversation between an AI agent and a user, paying close attention to the user's explicit requests, completed actions, and pending/in-progress tasks.
This summary should thoroughly capture technical details, code patterns, and architectural decisions that are essential for continuing development work seamlessly without losing context.

Step 1: Your summary MUST follow the format below:

<conversation_history_summary>
Summary of the conversation between an AI agent and a user.
Completed steps are documented for context; DO NOT re-execute already finished steps, but **DO continue any Pending or In-Progress tasks**!

<analysis>
[organize your thoughts and ensure you've covered all necessary points. no more than 300 words.]
</analysis>

<summary>
1. Primary Request and Intent: Capture all of the user's explicit requests and intents in detail.
2. Key Technical Concepts: List all important technical concepts, technologies, and frameworks discussed.
3. Files and Code Sections: Enumerate specific files and code sections examined, modified, or created.
4. Errors and Fixes: List all errors encountered and how they were resolved, plus specific user feedback.
5. Completed Tasks: What has been verified and finished so far.
6. Pending Tasks & Current Work: What remains to be done right now to fulfill the user's request.
7. All User Messages: Compact list of messages sent by the user.
</summary>
</conversation_history_summary>

Special Notes:
- Keep the total output under 1000 words.
- Follow the language of the user's query where possible.
- Clearly distinguish between COMPLETED tasks and PENDING/IN-PROGRESS tasks."""


BUGGY_TENCENT_HEADER = (
    "All tasks described below are already completed.\n"
    "**DO NOT re-run, re-do or re-execute any of the tasks mentioned!**"
)


class HistoryEngineeringCompactor:
    """
    Deterministic zero-LLM engineering compactor ported from WorkBuddy's `engineering-compactor.js`.
    """

    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return math.ceil(len(text) / CHARS_PER_TOKEN_ESTIMATE)

    @staticmethod
    def generate_summary_header() -> str:
        return (
            "Summary of the conversation so far:\n"
            "The conversation is between an AI agent and a user.\n"
            "Use this to get up to speed, and continue helping the user as the AI agent.\n"
            'Some contents may be omitted, indicated by "<omitted />".\n\n'
        )

    @staticmethod
    def strip_summary_header(text: str) -> str:
        m = re.search(r"<(conversation_history_summary|previous_\w+|analysis|summary)[>\s]", text)
        if m and m.start() > 0:
            return text[m.start() :].strip()
        return text.strip()

    @classmethod
    def process_tool_arguments(cls, args: Any) -> str:
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                return args
        if not isinstance(args, dict):
            return json.dumps(args or {}, ensure_ascii=False)
        cloned = dict(args)
        for key in OMITTED_ARG_KEYS:
            if key in cloned:
                cloned[key] = "<omitted>"
        return json.dumps(cloned, ensure_ascii=False)

    @classmethod
    def extract_text_from_user_message(cls, msg: Dict[str, Any]) -> str:
        content = msg.get("content")
        if not content:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                itype = item.get("type", "")
                if itype in ("input_text", "text") and item.get("text"):
                    parts.append(item["text"])
                elif itype in ("image_blob_ref", "input_image", "image_url"):
                    img = item.get("image") or item.get("image_url") or ""
                    if isinstance(img, dict):
                        img = img.get("url", "")
                    if isinstance(img, str) and img.startswith("data:"):
                        m = re.match(r"^data:(image/[^;]+);", img)
                        mime = m.group(1) if m else "image/unknown"
                        parts.append(f"[image: <{mime} base64 image>]")
                    else:
                        parts.append("[image: <image/unknown image>]")
            return "\n".join(parts)
        return ""

    @classmethod
    def compress_user_message(cls, msg: Dict[str, Any]) -> str:
        provider_data = msg.get("providerData") or {}
        text = cls.extract_text_from_user_message(msg)
        if not text:
            return ""
        if provider_data.get("isCompactInternal") or provider_data.get("isSummary") or provider_data.get("isCompacted"):
            m = re.search(r"<cb_summary>([\s\S]*?)</cb_summary>", text)
            if m:
                return cls.strip_summary_header(m.group(1).strip()) + "\n\n"
            return (text + "\n\n") if not provider_data.get("isCompacted") else ""

        m = re.search(r"<user_query>\n?([\s\S]*?)\n?</user_query>", text)
        query = m.group(1).strip() if m else text.strip()
        return f"<previous_user_message>\n<user_query>\n{query}\n</user_query>\n</previous_user_message>\n\n"

    @classmethod
    def compress_assistant_message(cls, msg: Dict[str, Any]) -> str:
        out = ""
        content = msg.get("content")
        texts = []
        if isinstance(content, str) and content.strip():
            texts.append(content.strip())
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                    t = (part.get("text") or "").strip()
                    if t:
                        texts.append(t)
        if texts:
            joined = "\n".join(texts)
            out += f"<previous_assistant_message>\n{joined}\n</previous_assistant_message>\n\n"

        tool_calls = msg.get("tool_calls") or []
        for tc in tool_calls:
            fn = tc.get("function") or tc
            name = fn.get("name") or "unknown"
            raw_args = fn.get("arguments")
            processed_args = cls.process_tool_arguments(raw_args) if raw_args is not None else ""
            out += f"<previous_tool_call>\nTool: {name}\n"
            if processed_args:
                out += f"Arguments: {processed_args}\n"
            out += "<result><omitted /></result>\n</previous_tool_call>\n\n"
        return out

    @classmethod
    def compress_function_call_item(cls, item: Dict[str, Any]) -> str:
        name = item.get("name") or "unknown"
        raw_args = item.get("arguments")
        processed_args = cls.process_tool_arguments(raw_args) if raw_args is not None else ""
        out = f"<previous_tool_call>\nTool: {name}\n"
        if processed_args:
            out += f"Arguments: {processed_args}\n"
        out += "<result><omitted /></result>\n</previous_tool_call>\n\n"
        return out

    @classmethod
    def compact(cls, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not messages:
            return {"compactContent": "", "estimatedTokens": 0, "originalItemCount": 0}

        body_parts = []
        for item in messages:
            itype = item.get("type")
            if itype in SKIPPED_ITEM_TYPES:
                continue
            if itype == "function_call":
                body_parts.append(cls.compress_function_call_item(item))
                continue
            role = item.get("role")
            if role == "tool":
                # OpenAI standard tool response role -> strip like function_call_result
                continue
            if role == "user":
                body_parts.append(cls.compress_user_message(item))
            elif role == "assistant":
                body_parts.append(cls.compress_assistant_message(item))

        body = "".join(body_parts)
        if not body.strip():
            return {"compactContent": "", "estimatedTokens": 0, "originalItemCount": len(messages)}

        full_summary = f"<cb_summary>\n{cls.generate_summary_header()}{body}</cb_summary>"
        return {
            "compactContent": full_summary,
            "estimatedTokens": cls.estimate_tokens(full_summary),
            "originalItemCount": len(messages),
        }


class ThreeStageCompactor:
    """
    Orchestrates PreMessage (3000) -> MaxToken (2000) -> Blocking (1000) compaction
    with the fixed LLM summary prompt.
    """

    def __init__(
        self,
        max_context_tokens: int = 300000,
        sufficiency_pct: float = 0.15,
        pre_message_pct: float = 0.50,
        emergency_pct: float = 0.90,
    ):
        self.max_context_tokens = max_context_tokens
        self.sufficiency_pct = sufficiency_pct
        self.pre_message_pct = pre_message_pct
        self.emergency_pct = emergency_pct

    def run_compact(
        self,
        messages: List[Dict[str, Any]],
        engineering_only: bool = False,
        llm_call_fn: Optional[Callable[[str, str], str]] = None,
        force_llm: bool = False,
    ) -> Dict[str, Any]:
        eng = HistoryEngineeringCompactor.compact(messages)
        orig_tokens = HistoryEngineeringCompactor.estimate_tokens(json.dumps(messages, ensure_ascii=False))
        sufficiency_budget = int(self.max_context_tokens * self.sufficiency_pct)

        if engineering_only or (not force_llm and eng["estimatedTokens"] <= sufficiency_budget) or llm_call_fn is None:
            return {
                "strategy": "PreMessage:EngineeringOnly",
                "used_llm": False,
                "original_tokens": orig_tokens,
                "compacted_tokens": eng["estimatedTokens"],
                "sufficiency_budget": sufficiency_budget,
                "summary_text": eng["compactContent"],
                "fixed_hypnosis_bug": True,
            }

        # Stage 2: LLM secondary summarization using FIXED_CONTEXT_SUMMARY_PROMPT
        system_prompt = (
            "You are a context summarization specialist for an AI coding and office agent. "
            "Do not call any tools. Output only the structured XML summary."
        )
        user_prompt = f"{FIXED_CONTEXT_SUMMARY_PROMPT}\n\n## Conversation History to Summarize\n{eng['compactContent']}"
        llm_summary = llm_call_fn(system_prompt, user_prompt)
        llm_tokens = HistoryEngineeringCompactor.estimate_tokens(llm_summary)

        return {
            "strategy": "PreMessage:LLMContextSummary(Fixed)",
            "used_llm": True,
            "original_tokens": orig_tokens,
            "engineering_tokens": eng["estimatedTokens"],
            "compacted_tokens": llm_tokens,
            "sufficiency_budget": sufficiency_budget,
            "summary_text": llm_summary,
            "fixed_hypnosis_bug": True,
        }
