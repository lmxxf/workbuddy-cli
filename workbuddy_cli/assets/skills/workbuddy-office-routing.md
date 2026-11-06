---
name: workbuddy-office-routing
display_name_zh: Office 文件路由
display_name_en: Office Routing
description: Load this Skill before handling local files such as pdf (read / summarize / ask → the `workbuddy-pdf` Skill), doc/docx/dot/wps/wpt, xls/xlsx/xlt/csv/tsv, or ppt/pptx/pps/pot, and before creating a new local document, spreadsheet, or presentation. Load first whenever the user uploads, mentions, previews, reads, edits, or asks to create such a local file, to decide whether to use the PDF Skill, the local office editing Skill, the local spreadsheet agent, the spreadsheet generation Skill, or the PPT Skill (`workbuddy-pptx` for generate / understand / edit). Text-based outputs such as speech scripts, talking points, copywriting, summaries, reports, or meeting minutes should default to local DOCX unless the user explicitly specifies another local format such as markdown or plain text. Other file types are out of scope.
author: Tencent Docs
version: "0.1.9"
user-invocable: false
---

# Local Office/WPS Routing

> **This is the gate you MUST read before handling local files — reading, summarizing, searching, or answering questions about a PDF, or working with doc/docx/dot/wps/wpt, xls/xlsx/xlt/csv/tsv, or ppt/pptx/pps/pot — AND before generating/creating any new local document, spreadsheet, or presentation.** This Skill only describes local file operations. It routes **content** work only — reading a document's content into context, editing, creating, transforming, and the like. Simply opening, previewing, or presenting a document for the user to *view* is the host's preview/present surface, not content work — call the host preview/present tool directly instead of routing it through this Skill.

## Host document context

The host injects a `<tencent_docs_editor_context>` block that surfaces local documents (e.g. `<active_document type="local" .../>`, `<local_files>`). Route each surfaced document by the file-type rules below.

If the context block already injected a `file_id` for a document, follow the **Injected `file_id`** rule in [file_id resolution](#file_id-resolution-local-documents).

## Supported Local Formats

Use these extensions to decide whether this routing Skill applies:

| Type | Supported local file extensions |
|---|---|
| doc | `.doc` `.dot` `.wps` `.wpt` `.docx` `.dotx` `.docm` `.dotm` |
| sheet | `.xls` `.xlt` `.xlsx` `.xltx` `.xlsm` `.xltm` `.csv` `.tsv` |
| slide | `.ppt` `.pps` `.pot` `.pptx` `.ppsx` `.potx` `.pptm` `.ppsm` `.potm` |

Macro-enabled files (`.docm` `.dotm` `.xlsm` `.xltm` `.pptm` `.ppsm` `.potm`) can be opened as their corresponding doc/sheet/slide type, but macros are not executed. WPS-specific `.et` `.ett` `.dps` `.dpt` are not supported; ask the user to save them as `.xlsx` or `.pptx` first.

## New Local File Creation

When the user asks to **generate / create / produce** a new document, spreadsheet, or presentation, produce a local Office/WPS-type file and route by file type. New local PPT (from scratch or from materials) uses **`workbuddy-pptx`** — see [Local PPT](#local-ppt-generate--understand--edit).

### Format classification (prerequisite step)

When the output the user requests is essentially structured textual content — such as speech scripts, talking points, copywriting, summaries, reports, or meeting minutes — always classify it as a doc first, then apply the local DOCX creation path.
Do not default to Markdown or plain text.
Only when the user explicitly specifies another local non-DOCX format (e.g. "generate markdown" or "plain text is fine") is this rule overridden.
This rule does not affect outputs that clearly belong to sheet (e.g. "make a spreadsheet") or ppt (e.g. "make a PPT").

## Existing Local Documents

> Note: This section applies to **existing local** documents that need to be read or edited. For **new** document creation, see "New Local File Creation" above.

Every task resolves by file type and task nature:

1. **Local PPT** — generate from scratch or from materials, understand / Q&A an existing deck, or edit an existing pptx (including follow-up edits after generation) → use the **`workbuddy-pptx`** Skill. Do **not** load `workbuddy-local-office-edit` for PPT.
2. **Local doc single-file edits** → load the **`workbuddy-local-office-edit`** Skill and operate through it.
3. **Local DOCX/Word creation from scratch, or an abstract whole-document beautification of an existing DOCX/Word file** → use the **`workbuddy-docx`** plugin (from-scratch creation → `full_pipeline`; whole-document abstract beautification → `beauty_only`). See the DOCX/Word sections below for the exact triggers and out-of-scope cases.
4. **Creating a new workbook** — the user's intent is to produce a brand-new `.xlsx` file at a **new file path** (independent from any source file), regardless of whether reference materials (including source spreadsheet files used strictly as read-only references) are attached → use the **`workbuddy-sheet-generation`** Skill. See "Creating a new workbook" below.
5. **Any task that touches an existing workbook** — editing existing cells, **adding / removing / renaming sheets inside it**, analyzing, aggregating, cleaning, reformatting, or otherwise modifying the source workbook in place (the source `.xlsx` file itself is the deliverable) → follow the sheet routing rules below (never `workbuddy-sheet-generation`).
6. **Local PDF reading** — summarizing, searching, or answering questions about a PDF's content → use the **`workbuddy-pdf`** Skill. See [Local PDF](#local-pdf-read--understand) below.

## Local PDF (read / understand)

Reading, summarizing, searching, or answering questions about a local PDF's content → use the **`workbuddy-pdf`** Skill, handing it the file path and the user's request. That Skill owns the extraction and its page-level visual checks — do not extract the PDF by any other means.

Out of scope for this route: previewing a PDF for the user to view (the host's preview surface, per [Showing a document to the user](#showing-a-document-to-the-user-preview)), and **producing or editing PDF files — unsupported in this release: do not attempt it via browser printing, pip-installed converters, or any other tool; tell the user it is unsupported and offer a non-PDF deliverable instead.** When a PDF is attached as **material** for another route (e.g. `workbuddy-pptx` materials, `workbuddy-sheet-generation` references, DOCX creation from source materials), hand it to that route's Skill — those Skills parse their own materials.

## Local PPT (generate / understand / edit)

All local PPT content work goes through `workbuddy-pptx`. Invoke that Skill and follow its routing table:

- **Generate from scratch** or **from source materials** (DOCX, XLSX, PPT, PDF, etc.) → `workbuddy-pptx`. When materials are supplied, that Skill has built-in material parsing; do not parse those materials by any other means.
- **Understand / Q&A** an existing PPT (what a page says, overall structure) → `workbuddy-pptx`.
- **Edit** an existing pptx (change a title, change one page, add/remove slides, follow-up edits after generation) → `workbuddy-pptx`.

Do **not** send PPT tasks to `workbuddy-local-office-edit`. Word / Excel edits stay on the doc and sheet routes below.

## Creating a new workbook

Whenever the user asks to **produce a new workbook** — signaled by authoring verbs such as 生成 / 制作 / 新建 / 做一份…表 / 整理成 Excel / 汇总成一份新表 applied to a spreadsheet — strictly use the `workbuddy-sheet-generation` Skill. The decisive condition is the **user's intent to produce a brand-new `.xlsx` file at a new file path**, not whether reference materials are attached: the content requirement may be pure text, or it may reference local materials — supported local reference types are PDF, DOCX, PPTX, and source spreadsheet files (`.xlsx` / `.xls` / `.csv` / `.tsv`) used strictly as read-only content references. When a source spreadsheet is supplied, apply the **intent test** below to distinguish "produce a NEW `.xlsx` file from these numbers" (route here) from "modify this workbook in place — including adding a new sheet inside it" (route to the sheet routes below). In every case hand the raw requirement and any referenced materials to the Skill and let it parse them; do **not** pre-parse those supported materials by any other means.

### Intent test (only when a source spreadsheet is supplied)

Route to `workbuddy-sheet-generation` **only if all** of the following hold:
- **New-file wording**: the user asks for a **new `.xlsx` file** (a separate workbook on disk) — e.g. "根据这个 xlsx **再生成一份新表**", "帮我基于这份 csv **整理成一份**销售统计表", "把这份数据做成一张**新的**汇总表". Look for verbs like 生成 / 新建 / 做一份 / 整理成 / 输出 / 另存 combined with a "new / another / separate" qualifier applied to **the file**, not to a sheet inside an existing workbook.
- **Read-only source**: the source workbook is used purely as a content reference; its own cells and sheet structure are not modified.
- **Deliverable is an independent file**: the primary deliverable is a fresh `.xlsx` at a **new file path different from the source**, not an in-place modification of the source workbook. **Adding a new sheet inside the existing workbook is an in-place edit, not generation** — it stays with the sheet routes below. Analysis output counts as generation **only when** the user explicitly asks for it as a separate NEW file (e.g. "汇总成一份新表"); the same analysis expressed as edits, annotations, or an added sheet inside the source is an edit, not generation.

If the intent test fails (any modify-in-place / add-sheet-to-source / analyze-source / clean-source wording), do **not** route here — fall through to the sheet routing rules below.

Out of scope (do **not** send here):
- The user's intent is to modify the source workbook in place — e.g. "改这份 xlsx", "在这个表里加一列", "在这个工作簿里加一个汇总 sheet", "透视一下这份数据", "帮我清洗这个 csv". These stay on the sheet routes below (`workbuddy-sheetagent` for data-dependent work, the `workbuddy-local-office-edit` Skill for deterministic edits).
- The requested output is not a spreadsheet (doc / ppt / text) — follow its own creation route above.
- The only reference material is a type this Skill cannot parse — e.g. an **image**, an archive, or any format other than PDF/DOCX/PPTX/XLSX/XLS/CSV/TSV. Do **not** hand such material to the Skill. Instead read its content into a plain-text requirement yourself first (e.g. read the numbers out of an image), then route that resulting pure-text request here as a normal workbook creation. If no usable content can be extracted, tell the user which inputs are supported (plain text, or PDF/DOCX/PPTX/XLSX/XLS/CSV/TSV references) rather than routing here.

## Local DOCX/Word creation from scratch

Whenever the user asks to **produce a new DOCX/Word file from zero** — signaled by authoring verbs such as 生成 / 写 / 起草 / 撰写 / 新建 / 重写 (重写 is treated as from-scratch creation here) applied to a document — strictly use the `workbuddy-docx` plugin. This is not restricted to specialized verticals: it covers ordinary everyday documents as well as recognizable professional genres such as research report (研报), annual report (年报), academic paper (论文), official/government document (公文), contract (合同), business report (商务报告), meeting minutes (会议纪要). In every case the plugin produces a complete document with an auto-generated cover page and professional, context-appropriate layout/typography; avoid assembling such documents by any other means.

This route is for **from-scratch creation only**: the plugin does **not** ingest source materials (DOCX, XLSX, PPT, PDF, etc.). If the user supplies source materials to be turned into a document, do not route here — fall back to the standard DOCX/Word creation path via the `workbuddy-local-office-edit` Skill. Editing an existing DOCX/Word file likewise stays with `workbuddy-local-office-edit`.

Concretely, the Orchestrator inside `workbuddy-docx` MUST decide `full_pipeline` directly at Stage 0 — no deliberation, no extra intent probing, no detour through lighter stages.

## Whole-document beautification of an existing DOCX (abstract styling)

When the user has already provided a single content document A AND asks for an **abstract, whole-document** beautification — expressions like "美化一下" / "更专业" / "更好看" / "排版优化" that require the AI to make design decisions without naming specific style values — AND **no** separate independent style-reference document B is attached, AND the request does **not** scope the beautification to a specific part of the document (e.g. "美化这个表格" / "美化这一段" / "调整第 X 节的样式"), use the `workbuddy-docx` plugin.

In this case the Orchestrator inside `workbuddy-docx` MUST decide `beauty_only` directly at Stage 0 — no deliberation, no extra intent probing, no detour through other stages.

Out of scope for this route (do **not** send here):
- The user provided a style-reference document B alongside A (that is a different routing decision, not this one).
- The user scoped the beautification to a specific fragment — a named table, a paragraph, a section, a page, etc. Localized style edits stay with the `workbuddy-local-office-edit` Skill.
- The user specified concrete style values (fonts, sizes, colors, spacing, etc.) — that is a direct edit, not an abstract beautification.

## Sheet Files (spreadsheets)

**Prerequisite**: this section only handles tasks where the source workbook **is modified in place** — editing cells, adding / removing / renaming sheets inside it, analyzing, pivoting, cleaning, reformatting, or any other transformation whose deliverable is the source `.xlsx` file itself. Tasks whose intent is to produce a **new `.xlsx` file at a new path** — including those with a source spreadsheet used only as a read-only reference — belong to `workbuddy-sheet-generation`; see "Creating a new workbook" above (and its intent test) for the routing rule and examples.

Resolve local sheet tasks by task nature. The `workbuddy-local-office-edit` Skill is allowed only for a small, bounded set of deterministic edits; complex or data-dependent local tasks MUST use `workbuddy-sheetagent`.

**Decide from the request TEXT alone, never from the data.** Apply this one test to the user's wording:

> Is the request a direct, deterministic edit — its operation type is fixed by the wording (format / border / merge / insert-delete rows·cols·cells / row-height·col-width / filter / sort / sheet add-delete-move / a formula written into a named cell) — and its target is either an explicit address or a label you can pin down by a single match?

- **Yes** → operate through the `workbuddy-local-office-edit` Skill.
- **Other sheet content work** → `workbuddy-sheetagent`. No deliberation, no investigation.

Match the work to the tool:

| Route here | When the local sheet task is |
|------------|------------------|
| `workbuddy-local-office-edit` Skill | A semantically unambiguous read/write completing in **a small, bounded set of deterministic calls** — e.g. reading or writing one specific cell/range, sorting one column (operate through the Skill) |
| `workbuddy-sheetagent` | Data analysis · aggregation · pivot · stats, cross-sheet linkage, formula building, data cleaning, conditional formatting across ranges, or anything needing you to understand the data before deciding how to edit. For these local tasks, use `workbuddy-sheetagent`; do not handle them through the `workbuddy-local-office-edit` Skill |

For local sheet files, the `workbuddy-local-office-edit` Skill is a right route for any direct, deterministic edit that passes the routing test above. Locating is reading the file only to find where the operation applies or what its current state is. This covers any lookup whose answer is a determinate address or value the file already contains. It is allowed on the local route and does not push the task to `workbuddy-sheetagent`. Understanding the data — reading values to decide what the edit should be: what a previous edit did, why something renders wrong, which rows qualify under a condition you must infer, or how to aggregate / compare / clean — is the data-dependence test failing, and goes to `workbuddy-sheetagent`. Diagnosis, comparison, and verification are the subagent's job, exactly like data discovery — they are not part of routing. Delegating means **invoking the `workbuddy-sheetagent` skill first** — call the Skill tool with the name `workbuddy-sheetagent` — and spawning the `sheet-agent` subagent only as it instructs; do **not** spawn `sheet-agent` directly, even though the subagent is visible on the Agent tool. `workbuddy-sheetagent` counts as unavailable **only** if that Skill call itself fails with a not-found / unknown-skill error; only then fall back to the `workbuddy-local-office-edit` Skill.

**Atomic sheetagent delegation:** For one user request, if a local sheet task should enter `workbuddy-sheetagent`, hand it the entire spreadsheet task — do not split the request by doing preparatory reads, partial writes, formatting, or cleanup through the `workbuddy-local-office-edit` Skill and then delegating only the remaining work. The only local calls allowed before delegating are the ones [file_id resolution](#file_id-resolution-local-documents) needs — nothing that touches document content. Note that tasks whose intent is to **produce a new `.xlsx` file at a new path** are not sheetagent tasks at all; they belong to `workbuddy-sheet-generation` per the intent test above. Adding a sheet inside an existing workbook, on the other hand, **stays with sheetagent** — that is an in-place edit, not generation. Once `workbuddy-sheetagent` is the route (or even a candidate), resolve the `file_id`, then **invoke the `workbuddy-sheetagent` skill and follow its delegation contract** — do not spawn the `sheet-agent` subagent directly — forwarding the resolved `file_id`, the absolute path, and the user's request verbatim; the subagent only consumes a live `file_id` and must not open files or resolve paths itself. If the task involves another spreadsheet (e.g. comparing with, or restoring formats from, an original file), resolve that file's `file_id` the same way and pass **both** ids with their paths — do not read or inspect either file's content yourself. Saving after the subagent finishes stays with you, not the subagent — per the `workbuddy-local-office-edit` flow.

Between resolving the `file_id` and delegating, make **no other** local call. Do not call `sheet_get_sheet_info`, do not read cells or ranges, do not pre-locate the data, and do not "look at the data first to understand it" — data discovery (sheets, headers, ranges) is the subagent's job, and any pre-reading splits the task (see [Atomic sheetagent delegation](#sheet-files-spreadsheets) above). If a plan you formed before reading this Skill included "read the data, then delegate", drop the read step. If the subagent rejects the `file_id` you passed, re-check it per [file_id resolution](#file_id-resolution-local-documents) and re-delegate; do **not** switch to reading the data yourself.

### Examples

> These illustrate the *pattern* — judge a request by which description fits, not by whether its wording matches an example.

**Examples → local `workbuddy-local-office-edit` Skill**
- Read / write / format a named cell or range — e.g. "Read A1:D10", "Set B2 to 100", "Bold A1"
- A deterministic operation whose target is a concrete, addressable part of the sheet  — e.g. "Sort the 'Price' column ascending", "Set all column widths to 120px"

**Examples → `workbuddy-sheet-generation` Skill (intent = produce a new `.xlsx` file)**
- Pure-text requirement — e.g. "做一份 6 月销售统计表", "帮我生成一张项目排期表".
- Content referenced from a non-spreadsheet material — e.g. "根据这份 PDF 整理成一个 Excel 表格", "把这个 Word 里的数据做成表格" (hand the material to the Skill; do not pre-parse it).
- Content referenced from a **source spreadsheet** used strictly as read-only reference, output is a **separate new `.xlsx` file** — e.g. "根据这个 xlsx **再生成一份新表**", "基于这份 csv **另出一张**汇总表" (intent test passes: user wants a NEW file, not to modify the source).

**Examples → local `workbuddy-sheetagent`**
- Editing / analyzing / pivoting / cleaning **the source workbook itself** — e.g. "在这个 xlsx 里加一列合计", "透视这份数据", "帮我清洗这个 csv"; the source `.xlsx` is the deliverable, not a content reference.
- **Adding / removing / renaming sheets inside an existing workbook** — e.g. "在这个 xlsx 里加一个汇总 sheet", "给这份工作簿再加一张月度对比表", "删掉这个表里的空白 sheet"; the workbook is modified in place, so this is an edit, not generation.
- **Any** pivot-table create or edit — e.g. "Build a pivot table"; it always requires reading the source data first.
- Ambiguous scope that needs judgment — e.g. "Clean up this table".
- Layout restructuring on the source — e.g. "Move this column"; it needs to read the current structure first.

## file_id resolution (local documents)

`file_id` identifies an open local editor instance — never invent one from a path or filename. This section only fixes **when** each entry applies; the calling style, workflow, and error handling are owned by the routed Skill's own documentation.

- **Injected `file_id`** — if the context block already injected one (e.g. `<active_document type="local" ... file_id="..."/>`), use it directly. The document already has a live host-owned editor/preview instance — do **not** reopen or re-present it.
- **Existing PPT, no injected id** — resolve it through the **`workbuddy-pptx`** Skill's documented flow (`get_pool_status` / `present_files` / `open_file`), then do the content work through that Skill.
- **Existing doc/sheet, no injected id** — resolve it through the **`workbuddy-local-office-edit`** Skill's documented flow (`get_pool_status` to find an already-open instance, `open_file` otherwise), then do the content work through that Skill.
- **Brand-new document (no file on disk yet)** — there is nothing to resolve; do **not** call `get_pool_status` / `open_file` on a path that does not exist. Creating the file and its first save are owned by the routed Skill (e.g. `workbuddy-pptx`, `workbuddy-sheet-generation`) or the host's create flow; once the file exists on disk, subsequent PPT edits stay with `workbuddy-pptx`, and subsequent doc/sheet edits re-enter here on the matching route above.

## Showing a document to the user (preview)

Previewing is the **host's preview surface**, not a content channel and not part of [file_id resolution](#file_id-resolution-local-documents). Present a local document to the user, per the host's preview instructions, whenever they should see it:

- **After creating a new local document** through a routed Skill (e.g. `workbuddy-pptx`, `workbuddy-sheet-generation`, `workbuddy-sheetagent`), open it so the user can immediately see and work with the result.
- **After finishing edits** on a document that is not already visible to the user, once it is saved.

Do **not** re-preview a document the context block already injected with a live `file_id`: it already has a host-owned preview instance.
