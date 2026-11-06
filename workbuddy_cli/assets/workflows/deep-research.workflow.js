export const meta = {
  name: 'deep-research',
  description: 'Deep research harness — fan-out web searches, fetch sources, adversarially verify claims, synthesize a cited report.',
  whenToUse: 'When the user wants a deep, multi-source, fact-checked research report on any topic. BEFORE invoking, check if the question is specific enough to research directly — if underspecified (e.g., "what car to buy" without budget/use-case/region), ask 2-3 clarifying questions to narrow scope. Then pass the refined question as args, weaving the answers in.',
  phases: [{"title":"Scope","detail":"Decompose question (from args) into 5 search angles"},{"title":"Search","detail":"5 parallel WebSearch agents, one per angle"},{"title":"Fetch","detail":"URL-dedup, fetch top 15 sources, extract falsifiable claims"},{"title":"Verify","detail":"3-vote adversarial verification per claim (need 2/3 refutes to kill)"},{"title":"Synthesize","detail":"Merge semantic dupes, rank by confidence, cite sources"}],
}

// deep-research: Scope → pipeline(Search → URL-dedup → Fetch+Extract) → 3-vote Verify → Synthesize
// Model compatibility: no `schema` param in agent() — deepseek-chat doesn't support
// reasoning_effort + structured output simultaneously. Instead, models output JSON text
// and we parse/validate manually.

// ─── JSON extraction + validation helpers (replaces agent schema option) ───
function extractJSON(text) {
  if (typeof text !== 'string') return null
  // Try ```json ... ``` block first, then ``` ... ```, then raw { }
  const patterns = [
    /```json\s*([\s\S]*?)```/,
    /```\s*([\s\S]*?)```/,
    /(\{[\s\S]*\})/,
  ]
  for (const pat of patterns) {
    const m = text.match(pat)
    if (m) {
      try { return JSON.parse(m[1].trim()) } catch {}
    }
  }
  return null
}

function validateJSON(data, schema) {
  if (!data || typeof data !== 'object') return false
  for (const key of (schema.required || [])) {
    if (!(key in data)) return false
    const val = data[key]
    const prop = schema.properties?.[key]
    if (prop) {
      if (prop.type === 'array') {
        if (!Array.isArray(val)) return false
        if (prop.minItems && val.length < prop.minItems) return false
        if (prop.maxItems && val.length > prop.maxItems) return false
        if (prop.items) {
          for (const item of val) {
            if (prop.items.required) {
              for (const r of prop.items.required) {
                if (!(r in item)) return false
              }
            }
            if (prop.items.properties && prop.items.properties.relevance) {
              if (!['high','medium','low'].includes(item.relevance)) return false
            }
            if (prop.items.properties && prop.items.properties.importance) {
              if (!['central','supporting','tangential'].includes(item.importance)) return false
            }
          }
        }
      } else if (prop.type === 'object') {
        if (!val || typeof val !== 'object') return false
      } else if (prop.type === 'string') {
        if (typeof val !== 'string') return false
      } else if (prop.type === 'boolean') {
        if (typeof val !== 'boolean') return false
      }
      if (prop.enum && !prop.enum.includes(val)) return false
    }
  }
  return true
}

function safeParse(text, schema, fallback = null) {
  const parsed = extractJSON(text)
  if (parsed && validateJSON(parsed, schema)) return parsed
  return fallback
}

const VOTES_PER_CLAIM = 3
const REFUTATIONS_REQUIRED = 2
const MAX_FETCH = 15
const MAX_VERIFY_CLAIMS = 25

// ─── Schemas (for validation, not agent() calls) ───
const SCOPE_SCHEMA = {
  type: "object", required: ["question", "angles", "summary"],
  properties: {
    question: { type: "string" },
    summary: { type: "string" },
    angles: { type: "array", minItems: 3, maxItems: 6, items: {
      type: "object", required: ["label", "query"],
      properties: { label: { type: "string" }, query: { type: "string" }, rationale: { type: "string" } },
    }},
  },
}
const SEARCH_SCHEMA = {
  type: "object", required: ["results"],
  properties: {
    results: { type: "array", maxItems: 6, items: {
      type: "object", required: ["url", "title", "relevance"],
      properties: {
        url: { type: "string" }, title: { type: "string" }, snippet: { type: "string" },
        relevance: { enum: ["high", "medium", "low"] },
      },
    }},
  },
}
const EXTRACT_SCHEMA = {
  type: "object", required: ["claims", "sourceQuality"],
  properties: {
    sourceQuality: { enum: ["primary", "secondary", "blog", "forum", "unreliable"] },
    publishDate: { type: "string" },
    claims: { type: "array", maxItems: 5, items: {
      type: "object", required: ["claim", "quote", "importance"],
      properties: { claim: { type: "string" }, quote: { type: "string" }, importance: { enum: ["central", "supporting", "tangential"] } },
    }},
  },
}
const VERDICT_SCHEMA = {
  type: "object", required: ["refuted", "evidence", "confidence"],
  properties: {
    refuted: { type: "boolean" }, evidence: { type: "string" },
    confidence: { enum: ["high", "medium", "low"] }, counterSource: { type: "string" },
  },
}
const REPORT_SCHEMA = {
  type: "object", required: ["summary", "findings", "caveats"],
  properties: {
    summary: { type: "string" },
    findings: { type: "array", items: {
      type: "object", required: ["claim", "confidence", "sources", "evidence"],
      properties: {
        claim: { type: "string" }, confidence: { enum: ["high", "medium", "low"] },
        sources: { type: "array", items: { type: "string" } }, evidence: { type: "string" }, vote: { type: "string" },
      },
    }},
    caveats: { type: "string" },
    openQuestions: { type: "array", items: { type: "string" } },
  },
}

// ─── Phase 0: Scope — decompose question into search angles ───
phase("Scope")
const QUESTION = (typeof args === "string" && args.trim()) || ""
if (!QUESTION) {
  return { error: "No research question provided. Pass it as args: Workflow({name: 'deep-research', args: '<question>'})." }
}
const scope = await agent(
  "Decompose this research question into complementary search angles.\n\n" +
  "## Question\n" + QUESTION + "\n\n" +
  "## Task\n" +
  "Generate 5 distinct web search queries that together cover the question from different angles. Pick angles that suit the question's domain. Examples:\n" +
  "- broad/primary  · academic/technical  · recent news  · contrarian/skeptical  · practitioner/implementation\n" +
  "- For medical: anatomy · common causes · serious differentials · authoritative refs · red flags\n" +
  "- For tech: state-of-art · benchmarks · limitations · industry adoption · cost/tradeoffs\n\n" +
  "Make queries specific enough to surface high-signal results. Avoid redundancy.\n" +
  "Return ONLY valid JSON (no markdown, no explanation) matching this schema:\n" +
  '{"question": "string", "summary": "string", "angles": [{"label": "string", "query": "string", "rationale": "string"}]}\n' +
  "with 3-6 angles. The JSON object only — nothing before or after.",
  { label: "scope", model: "lite" }
)
const scopeParsed = safeParse(scope, SCOPE_SCHEMA)
if (!scopeParsed) {
  return "# Deep Research Report\n\n**Error:** Scope agent returned no result — cannot decompose the research question."
}
log("Q: " + QUESTION.slice(0, 80) + (QUESTION.length > 80 ? "…" : ""))
log("Decomposed into " + scopeParsed.angles.length + " angles: " + scopeParsed.angles.map(a => a.label).join(", "))

// ─── Dedup state — accumulates across searchers as they complete ───
const normURL = u => {
  try {
    const p = new URL(u)
    return (p.hostname.replace(/^www\./, "") + p.pathname.replace(/\/$/, "")).toLowerCase()
  } catch { return u.toLowerCase() }
}
const seen = new Map()
const dupes = []
const budgetDropped = []
const relRank = { high: 0, medium: 1, low: 2 }
let fetchSlots = MAX_FETCH

// ─── Prompts ───
const SEARCH_PROMPT = (angle) =>
  "## Web Searcher: " + angle.label + "\n\n" +
  "Research question: \"" + QUESTION + "\"\n\n" +
  "Your angle: **" + angle.label + "** — " + (angle.rationale || "") + "\n" +
  "Search query: `" + angle.query + "`\n\n" +
  "## Task\nUse WebSearch with the query above (or a refined version). Return the top 4-6 most relevant results.\n" +
  "Rank by relevance to the ORIGINAL question, not just the search query. Skip obvious SEO spam/content farms.\n" +
  "Include a short snippet capturing why each result is relevant.\n\n" +
  "Return ONLY valid JSON (no markdown, no explanation) matching:\n" +
  '{"results": [{"url": "string", "title": "string", "snippet": "string", "relevance": "high|medium|low"}]}\n' +
  "with 4-6 results. The JSON object only — nothing before or after."

const FETCH_PROMPT = (source, angle) =>
  "## Source Extractor\n\n" +
  "Research question: \"" + QUESTION + "\"\n\n" +
  "Fetch and extract key claims from this source:\n" +
  "**URL:** " + source.url + "\n**Title:** " + source.title + "\n**Found via:** " + angle + " search\n\n" +
  "## Task\n1. Use WebFetch to retrieve the page content.\n" +
  "2. Assess source quality: primary research/institution? secondary reporting? blog/opinion? forum? unreliable?\n" +
  "3. Extract 2-5 FALSIFIABLE claims that bear on the research question. Each claim must:\n" +
  "   - be a concrete, checkable statement (not vague generalities)\n" +
  "   - include a direct quote from the source as support\n" +
  "   - be rated central/supporting/tangential to the research question\n" +
  "4. Note publish date if available.\n\n" +
  "If the fetch fails or the page is irrelevant/paywalled, return claims: [] and sourceQuality: \"unreliable\".\n\n" +
  "Return ONLY valid JSON (no markdown, no explanation) matching:\n" +
  '{"sourceQuality": "primary|secondary|blog|forum|unreliable", "publishDate": "string", "claims": [{"claim": "string", "quote": "string", "importance": "central|supporting|tangential"}]}\n' +
  "with 2-5 claims per source. The JSON object only — nothing before or after."

const VERIFY_PROMPT = (claim, v) =>
  "## Adversarial Claim Verifier (voter " + (v + 1) + "/" + VOTES_PER_CLAIM + ")\n\n" +
  "Be SKEPTICAL. Try to REFUTE this claim. ≥" + REFUTATIONS_REQUIRED + "/" + VOTES_PER_CLAIM + " refutations kill it.\n\n" +
  "## Research question\n" + QUESTION + "\n\n" +
  "## Claim under review\n\"" + claim.claim + "\"\n\n" +
  "**Source:** " + claim.sourceUrl + " (" + claim.sourceQuality + ")\n" +
  "**Supporting quote:** \"" + claim.quote + "\"\n\n" +
  "## Checklist\n" +
  "1. Is the claim actually supported by the quote, or is it an overreach/misread?\n" +
  "2. WebSearch for contradicting evidence — does any credible source dispute or heavily qualify this?\n" +
  "3. Is the source quality sufficient for the claim's strength? (extraordinary claims need primary sources)\n" +
  "4. Is the claim outdated? (check dates — old claims about fast-moving fields are suspect)\n" +
  "5. Is this a marketing claim / press release / cherry-picked benchmark / forum speculation?\n\n" +
  "**refuted=true** if: unsupported by quote / contradicted / low-quality source for strong claim / outdated / marketing fluff.\n" +
  "**refuted=false** ONLY if: claim is well-supported, current, and source quality matches claim strength.\n" +
  "Default to refuted=true if uncertain.\n\n" +
  "Return ONLY valid JSON (no markdown, no explanation) matching:\n" +
  '{"refuted": true|false, "evidence": "string", "confidence": "high|medium|low", "counterSource": "string"}\n' +
  "The JSON object only — nothing before or after. Evidence MUST be specific."

// ─── Pipeline: search → dedup → fetch+extract (no barrier) ───
const searchResults = await pipeline(
  scopeParsed.angles,

  angle => agent(SEARCH_PROMPT(angle), {
    label: "search:" + angle.label, phase: "Search", model: "lite"
  }).then(r => {
    const parsed = safeParse(r, SEARCH_SCHEMA)
    if (!parsed) return null
    log(angle.label + ": " + parsed.results.length + " results")
    return { angle: angle.label, results: parsed.results }
  }),

  searchResult => {
    const sorted = [...searchResult.results].sort((a, b) => relRank[a.relevance] - relRank[b.relevance])
    const novel = sorted.filter(r => {
      const key = normURL(r.url)
      if (seen.has(key)) {
        dupes.push({ ...r, angle: searchResult.angle, dupOf: seen.get(key) })
        return false
      }
      if (fetchSlots <= 0 && relRank[r.relevance] >= 1) {
        budgetDropped.push({ ...r, angle: searchResult.angle })
        return false
      }
      seen.set(key, { angle: searchResult.angle, title: r.title })
      fetchSlots--
      return true
    })
    if (novel.length < searchResult.results.length) {
      log(searchResult.angle + ": " + novel.length + " novel (" + (searchResult.results.length - novel.length) + " filtered)")
    }
    return parallel(
      novel.map(source => () => {
        // host 仅用作 agent label,解析失败也不阻断流程。
        // search agent 返回的 url 经常不规范:缺 scheme 的裸域名 / markdown 链接
        // 片段 / 整段标题塞进 url 字段。三层兜底,实在拿不到才回落 "unknown"。
        let host = "unknown"
        const raw = String(source.url || "").trim()
        try {
          host = new URL(raw).hostname.replace(/^www\./, "")
        } catch {
          // 1) 缺 scheme 的裸域名 → 补 https:// 再试
          try {
            host = new URL("https://" + raw.replace(/^\/+/, "")).hostname.replace(/^www\./, "")
          } catch {
            // 2) markdown 链接片段 / 杂乱字符串 → 正则抓第一个 host-like token。
            //    `\b` 边界让 ".com)" / ".com," 这类后跟标点的也能命中。
            const m = raw.match(/([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})\b/i)
            if (m) host = m[1].replace(/^www\./, "")
          }
        }
        return agent(FETCH_PROMPT(source, searchResult.angle), {
          label: "fetch:" + host,
          phase: "Fetch", model: "lite",
        }).then(ext => {
          const parsed = safeParse(ext, EXTRACT_SCHEMA)
          if (!parsed) return null
          return {
            url: source.url, title: source.title, angle: searchResult.angle,
            sourceQuality: parsed.sourceQuality, publishDate: parsed.publishDate,
            claims: parsed.claims.map(c => ({ ...c, sourceUrl: source.url, sourceQuality: parsed.sourceQuality })),
          }
        }).catch(e => {
          log("fetch failed: " + source.url + " — " + (e.message || e))
          return { url: source.url, title: source.title, angle: searchResult.angle, sourceQuality: "unreliable", claims: [] }
        })
      })
    )
  }
)

const allSources = searchResults.flat().filter(Boolean)
const allClaims = allSources.flatMap(s => s.claims)
const impRank = { central: 0, supporting: 1, tangential: 2 }
const qualRank = { primary: 0, secondary: 1, blog: 2, forum: 3, unreliable: 4 }

const rankedClaims = [...allClaims]
  .sort((a, b) => (impRank[a.importance] - impRank[b.importance]) || (qualRank[a.sourceQuality] - qualRank[b.sourceQuality]))
  .slice(0, MAX_VERIFY_CLAIMS)

log("Fetched " + allSources.length + " sources → " + allClaims.length + " claims → verifying top " + rankedClaims.length)

// ─── Report formatter: convert structured data to readable Markdown ───
function formatReport(data) {
  const lines = []
  lines.push("# Deep Research Report")
  lines.push("")
  lines.push("**Question:** " + data.question)
  lines.push("")

  if (data.summary) {
    lines.push("## Summary")
    lines.push("")
    lines.push(data.summary)
    lines.push("")
  }

  if (data.findings && data.findings.length > 0) {
    lines.push("## Key Findings")
    lines.push("")
    data.findings.forEach(function(f, i) {
      var conf = f.confidence === 'high' ? '[HIGH]' : f.confidence === 'medium' ? '[MEDIUM]' : '[LOW]'
      lines.push("### " + (i + 1) + ". " + f.claim)
      lines.push("")
      lines.push("- **Confidence:** " + conf + (f.vote ? " (vote: " + f.vote + ")" : ""))
      if (f.evidence) lines.push("- **Evidence:** " + f.evidence)
      if (f.sources && f.sources.length > 0) {
        lines.push("- **Sources:** " + f.sources.join(", "))
      }
      lines.push("")
    })
  }

  if (data.refuted && data.refuted.length > 0) {
    lines.push("## Refuted Claims")
    lines.push("")
    data.refuted.forEach(function(r) {
      lines.push("- ~~" + r.claim + "~~ (vote: " + r.vote + ", source: " + r.source + ")")
    })
    lines.push("")
  }

  if (data.caveats) {
    lines.push("## Caveats")
    lines.push("")
    lines.push(data.caveats)
    lines.push("")
  }

  if (data.openQuestions && data.openQuestions.length > 0) {
    lines.push("## Open Questions")
    lines.push("")
    data.openQuestions.forEach(function(q) { lines.push("- " + q) })
    lines.push("")
  }

  if (data.stats) {
    var s = data.stats
    lines.push("---")
    lines.push("*Stats: " + (s.angles || 0) + " angles, " + (s.sourcesFetched || s.sources || 0) + " sources fetched, " + (s.claimsExtracted || s.claims || 0) + " claims extracted, " + (s.confirmed || 0) + " confirmed, " + (s.killed || 0) + " refuted, " + (s.agentCalls || 0) + " agent calls*")
  }

  return lines.join("\n")
}

if (rankedClaims.length === 0) {
  return formatReport({
    question: QUESTION,
    summary: "No claims extracted. " + allSources.length + " sources fetched, all empty/failed. " + dupes.length + " URL dupes, " + budgetDropped.length + " budget-dropped.",
    findings: [], refuted: [],
    stats: { angles: scopeParsed.angles.length, sources: allSources.length, claims: 0 },
  })
}

// ─── Verify: 3-vote adversarial ───
// Barrier here is intentional — claim pool must be fully assembled before ranking/verification.
phase("Verify")
const voted = (await parallel(
  rankedClaims.map(claim => () =>
    parallel(
      Array.from({ length: VOTES_PER_CLAIM }, (_, v) => () =>
          agent(VERIFY_PROMPT(claim, v), {
            label: "v" + v + ":" + claim.claim.slice(0, 40),
            phase: "Verify", model: "lite",
          }).then(text => safeParse(text, VERDICT_SCHEMA))
      )
    ).then(verdicts => {
      // A vote can be null (user-skip or agent error) — treat as abstain.
      const valid = verdicts.filter(Boolean)
      const refuted = valid.filter(v => v.refuted).length
      // Survive only if the claim was actually adjudicated: a quorum of
      // valid votes AND fewer than REFUTATIONS_REQUIRED refuting. Too many
      // abstentions = unverified, which must NOT pass into the report
      // (otherwise all-abstain → refuted=0 → false survive).
      const abstained = VOTES_PER_CLAIM - valid.length
      const survives = valid.length >= REFUTATIONS_REQUIRED && refuted < REFUTATIONS_REQUIRED
      log("\"" + claim.claim.slice(0, 50) + "…\": " + (valid.length - refuted) + "-" + refuted + (abstained > 0 ? " (" + abstained + " abstain)" : "") + " " + (survives ? "✓" : "✗"))
      return { ...claim, verdicts: valid, refutedVotes: refuted, survives }
    })
  )
)).filter(Boolean)

const confirmed = voted.filter(c => c.survives)
const killed = voted.filter(c => !c.survives)
log("Verify done: " + voted.length + " claims → " + confirmed.length + " confirmed, " + killed.length + " killed")

if (confirmed.length === 0) {
  return formatReport({
    question: QUESTION,
    summary: "All " + voted.length + " claims refuted by adversarial verification. Research inconclusive — sources may be low-quality or claims overstated.",
    findings: [],
    refuted: killed.map(c => ({ claim: c.claim, vote: (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes, source: c.sourceUrl })),
    stats: { angles: scopeParsed.angles.length, sources: allSources.length, claims: allClaims.length, confirmed: 0, killed: killed.length },
  })
}

// ─── Synthesize ───
phase("Synthesize")
const confRank = { high: 0, medium: 1, low: 2 }
const block = confirmed.map((c, i) => {
  const best = c.verdicts.filter(v => !v.refuted).sort((a, b) => confRank[a.confidence] - confRank[b.confidence])[0]
  return "### [" + i + "] " + c.claim + "\n" +
    "Vote: " + (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes + " · Source: " + c.sourceUrl + " (" + c.sourceQuality + ")\n" +
    "Quote: \"" + c.quote + "\"\nVerifier evidence (" + best.confidence + "): " + best.evidence + "\n"
}).join("\n")

const killedBlock = killed.length > 0
  ? "\n## Refuted claims (for transparency)\n" +
    killed.map(c => "- \"" + c.claim + "\" (" + c.sourceUrl + ", vote " + (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes + ")").join("\n")
  : ""

const reportText = await agent(
  "## Synthesis: research report\n\n" +
  "**Question:** " + QUESTION + "\n\n" +
  confirmed.length + " claims survived " + VOTES_PER_CLAIM + "-vote adversarial verification. Merge semantic duplicates and synthesize.\n\n" +
  "## Confirmed claims\n" + block + "\n" + killedBlock + "\n\n" +
  "## Instructions\n" +
  "1. Identify claims that say the same thing — merge them, combine their sources.\n" +
  "2. Group related claims into coherent findings. Each finding should directly address the research question.\n" +
  "3. Assign confidence per finding: high (multiple primary sources, unanimous votes), medium (secondary sources or split votes), low (single source or blog-quality).\n" +
  "4. Write a 3-5 sentence executive summary answering the research question.\n" +
  "5. Note caveats: what's uncertain, what sources were weak, what time-sensitivity applies.\n" +
  "6. List 2-4 open questions that emerged but weren't answered.\n\n" +
  "Return ONLY valid JSON (no markdown, no explanation) matching:\n" +
  '{"summary": "string", "findings": [{"claim": "string", "confidence": "high|medium|low", "sources": ["string"], "evidence": "string", "vote": "string"}], "caveats": "string", "openQuestions": ["string"]}\n' +
  "The JSON object only — nothing before or after.",
  { label: "synthesize", model: "lite" }
)
const report = safeParse(reportText, REPORT_SCHEMA)

if (!report) {
  // Synthesis skipped/errored — salvage the verified claims raw rather
  // than throwing on report.findings and discarding the whole run.
  return formatReport({
    question: QUESTION,
    summary: "Synthesis step was skipped or failed — returning " + confirmed.length + " verified claims unmerged.",
    findings: confirmed.map(c => ({ claim: c.claim, confidence: "medium", sources: [c.sourceUrl], evidence: c.quote, vote: (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes })),
    refuted: killed.map(c => ({ claim: c.claim, vote: (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes, source: c.sourceUrl })),
    stats: { angles: scopeParsed.angles.length, sourcesFetched: allSources.length, claimsExtracted: allClaims.length, confirmed: confirmed.length, killed: killed.length, agentCalls: 1 + scopeParsed.angles.length + allSources.length + (voted.length * VOTES_PER_CLAIM) + 1 },
  })
}

return formatReport({
  question: QUESTION,
  ...report,
  refuted: killed.map(c => ({ claim: c.claim, vote: (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes, source: c.sourceUrl })),
  stats: {
    angles: scopeParsed.angles.length,
    sourcesFetched: allSources.length,
    claimsExtracted: allClaims.length,
    claimsVerified: voted.length,
    confirmed: confirmed.length,
    killed: killed.length,
    afterSynthesis: report.findings.length,
    agentCalls: 1 + scopeParsed.angles.length + allSources.length + (voted.length * VOTES_PER_CLAIM) + 1,
  },
})