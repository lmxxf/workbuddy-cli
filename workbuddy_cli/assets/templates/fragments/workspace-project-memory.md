# Workspace Project Logs and Instructions

Directory: {{ WorkbuddyMemoryDir }}/ | Scope: current project only

Files:
- `{{ WorkbuddyMemoryDir }}/YYYY-MM-DD.md` — daily work log. **Append-only**, never overwrite.
- `{{ WorkbuddyMemoryDir }}/MEMORY.md` — project instructions the user asked to record. Limit: 3,000 chars/session. Read existing content when relevant. Write or revise it only when the user explicitly asks to record or change something in project instructions; a request to remember something, even about this project, uses memory tools instead.
- If today's log does not exist, create the directory and dated file first.

Retrieving historical context:
- This project's past work → read local daily logs (most recent first) or `{{ WorkbuddyMemoryDir }}/MEMORY.md`.
- No historical dependency → skip reading memory files.

**When to write:** After substantive work and before the final answer, append a brief useful progress note to the daily log: outcomes, necessary validation results, and unresolved follow-up. Avoid command inventories, raw tool output, and incidental runtime details. Do not fabricate a log entry for a trivial exchange.

Never store raw secrets in project logs or instructions, even if the user asks. Workspace notes supplement the normal reply and user-requested deliverables; they do not replace them.
