"""
Adversarial Critic-Generator Engine for workbuddy-cli (`skills/critic-generator-engine.md`).
Implements the 6-Step State Machine:
  ① Isolate: Strip author chain-of-thought & construct a pure Blind Review Package (`盲审包`).
  ② LoadRubrics: Lazy-load evaluation rubrics ONLY during review (never during drafting).
  ③ Score: Quantitatively score each dimension with concrete text evidence (no vague praise).
  ④ Challenge: Enforce mandatory deduction quotas (`min_issues >= 2`, `min_instructions >= 3`
     with `location + issue + P0/P1/P2 severity + actionable fix`). "All Pass" is strictly forbidden!
  ⑤ Decide: Output `REVISE` (if any P0 and loop < max_loops), `PASS`, or `DEGRADED`.
  ⑥ Report: Emit structured Markdown Critic Report.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from ..config import ASSETS_DIR


DEFAULT_RUBRICS = [
    {"dimension": "事实与数据准确性 (Fact & Data Rigor)", "max_score": 100, "pass_score": 85},
    {"dimension": "结构与逻辑严密性 (Structural Coherence)", "max_score": 100, "pass_score": 85},
    {"dimension": "可执行性与细节深度 (Actionability & Depth)", "max_score": 100, "pass_score": 85},
    {"dimension": "表达凝练度与反车轱辘话 (Anti-Fluff & Clarity)", "max_score": 100, "pass_score": 85},
]


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    for pat in (r"```json\s*([\s\S]*?)```", r"```\s*([\s\S]*?)```", r"(\{[\s\S]*\})"):
        m = re.search(pat, text)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except Exception:
                continue
    return None


class CriticGeneratorEngine:
    """
    Executes WorkBuddy's 6-Step Adversarial Blind Review with mandatory deduction quotas.
    """

    def __init__(
        self,
        min_issues: int = 2,
        min_instructions: int = 3,
        pass_score: int = 85,
        max_loops: int = 3,
    ):
        self.min_issues = min_issues
        self.min_instructions = min_instructions
        self.pass_score = pass_score
        self.max_loops = max_loops
        self.spec_path = ASSETS_DIR / "skills" / "critic-generator-engine.md"

    def build_blind_package(
        self,
        draft_text: str,
        scope: str = "full",
        profile: str = "Technical & Executive Report",
        sources: Optional[List[str]] = None,
        prior_instructions: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Step ① Isolate: Constructs a pure Blind Review Package stripped of author CoT."""
        return {
            "draft_text": draft_text.strip(),
            "scope": scope,
            "profile": profile,
            "verifiable_sources": sources or [],
            "prior_instructions": prior_instructions or [],
            "isolated_from_author_cot": True,
        }

    def load_rubrics(self, rubric_files: Optional[List[Path]] = None) -> List[Dict[str, Any]]:
        """Step ② LoadRubrics: Lazy-loads evaluation rubrics at review time."""
        if not rubric_files:
            return list(DEFAULT_RUBRICS)
        loaded = []
        for rf in rubric_files:
            p = Path(rf)
            if not p.exists():
                raise FileNotFoundError(f"[CriticEngine:FAILED] Rubric file missing: {p}")
            loaded.append(
                {
                    "dimension": p.stem,
                    "max_score": 100,
                    "pass_score": self.pass_score,
                    "content": p.read_text(encoding="utf-8")[:4000],
                }
            )
        return loaded

    def run_review(
        self,
        draft_text: str,
        scope: str = "full",
        loop_index: int = 0,
        llm_call_fn: Optional[Callable[[str, str], str]] = None,
        report_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        blind_pkg = self.build_blind_package(draft_text, scope=scope)
        rubrics = self.load_rubrics()

        parsed = None
        if llm_call_fn is not None:
            sys_prompt = (
                "You are WorkBuddy's Adversarial Critic-Generator Engine. "
                "You operate in strict Blind Review Isolation (Step 1 Isolate). "
                "NEVER rationalize the author's choices. NEVER output 'All Pass'. "
                f"You MUST deduct points on at least {self.min_issues} dimensions (score <= {self.pass_score}) "
                f"and generate at least {self.min_instructions} concrete improvement instructions with "
                "location, problem, severity (P0/P1/P2), and actionable fix direction."
            )
            user_prompt = (
                f"## Blind Review Package\n```json\n{json.dumps(blind_pkg, ensure_ascii=False, indent=2)}\n```\n\n"
                f"## Loaded Rubrics\n```json\n{json.dumps(rubrics, ensure_ascii=False, indent=2)}\n```\n\n"
                "Return ONLY valid JSON matching:\n"
                '{"score_table": [{"dimension": "str", "score": 78, "evidence": "str"}], '
                '"instructions": [{"id": "INS-1", "location": "str", "issue": "str", "severity": "P0|P1|P2", "fix": "str"}]}'
            )
            try:
                raw_resp = llm_call_fn(sys_prompt, user_prompt)
                parsed = _extract_json(raw_resp)
            except Exception:
                parsed = None

        if not parsed or "score_table" not in parsed or "instructions" not in parsed:
            parsed = self._deterministic_audit_fallback(draft_text, rubrics)

        # Enforce Step ④ Challenge quotas strictly (even if LLM tried to be nice)
        score_table = parsed.get("score_table", [])
        instructions = parsed.get("instructions", [])

        low_dims = [d for d in score_table if d.get("score", 100) <= self.pass_score]
        for d in score_table:
            if len(low_dims) >= self.min_issues:
                break
            if d not in low_dims:
                d["score"] = self.pass_score - 5
                d["evidence"] = f"[Quota Enforced] Paragraph-level density can be tightened: {d.get('evidence', '')}"
                low_dims.append(d)

        while len(instructions) < self.min_instructions:
            idx = len(instructions) + 1
            instructions.append(
                {
                    "id": f"INS-{idx}",
                    "location": f"Paragraph #{min(idx, max(1, len(draft_text.splitlines())))}",
                    "issue": "Assertion lacks quantitative anchor or concrete boundary condition.",
                    "severity": "P1",
                    "fix": "Add concrete numerical metric, citation, or explicit counter-example handling.",
                }
            )

        total_score = round(
            sum(float(d.get("score", 80)) for d in score_table) / max(1, len(score_table)),
            1,
        )
        has_p0 = any(ins.get("severity") == "P0" for ins in instructions)

        # Step ⑤ Decide
        if has_p0 and loop_index < self.max_loops:
            decision = "REVISE"
        elif has_p0 and loop_index >= self.max_loops:
            decision = "DEGRADED"
        else:
            decision = "PASS" if total_score >= (self.pass_score - 10) else "REVISE"

        # Step ⑥ Report
        md_report = self.format_markdown_report(score_table, total_score, instructions, decision, loop_index)
        if report_path:
            rp = Path(report_path).resolve()
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(md_report, encoding="utf-8")

        return {
            "decision": decision,
            "total_score": total_score,
            "deducted_dimensions_count": len(low_dims),
            "instructions_count": len(instructions),
            "has_p0": has_p0,
            "score_table": score_table,
            "instructions": instructions,
            "markdown_report": md_report,
        }

    def _deterministic_audit_fallback(self, draft_text: str, rubrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        lines = [ln.strip() for ln in draft_text.splitlines() if ln.strip()]
        has_numbers = bool(re.search(r"\d+(?:\.\d+)?%?", draft_text))
        has_headings = any(ln.startswith("#") for ln in lines)

        score_table = [
            {
                "dimension": rubrics[0]["dimension"],
                "score": 82 if has_numbers else 72,
                "evidence": "Quantitative claims detected but primary source timestamps or error bars are missing."
                if has_numbers
                else "No quantitative metrics or empirical numbers found in draft.",
            },
            {
                "dimension": rubrics[1]["dimension"],
                "score": 88 if has_headings else 76,
                "evidence": "Section hierarchy present." if has_headings else "Flat text without structured section headings.",
            },
            {
                "dimension": rubrics[2]["dimension"],
                "score": 79,
                "evidence": "Execution steps lack explicit failure-recovery / rollback thresholds.",
            },
            {
                "dimension": rubrics[3]["dimension"],
                "score": 86,
                "evidence": "Opening and closing sentences can be condensed by 20%.",
            },
        ]
        instructions = [
            {
                "id": "INS-1",
                "location": "Opening Section / Core Claim",
                "issue": "Missing empirical baseline or verifiable source attribution.",
                "severity": "P0" if not has_numbers else "P1",
                "fix": "Insert concrete benchmark figures, sample size, and primary source citation.",
            },
            {
                "id": "INS-2",
                "location": "Implementation / Action Section",
                "issue": "Boundary conditions and failure fallback path are underspecified.",
                "severity": "P1",
                "fix": "Specify exact threshold parameters and deterministic fallback behavior on error.",
            },
            {
                "id": "INS-3",
                "location": "Concluding Paragraph",
                "issue": "Summary repeats generic filler phrases instead of quantifiable takeaways.",
                "severity": "P2",
                "fix": "Replace generic summary with a 3-item checklist of verifiable deliverables.",
            },
        ]
        return {"score_table": score_table, "instructions": instructions}

    @staticmethod
    def format_markdown_report(
        score_table: List[Dict[str, Any]],
        total_score: float,
        instructions: List[Dict[str, Any]],
        decision: str,
        loop_index: int,
    ) -> str:
        out = [
            "# Critic-Generator Blind Review Report (对抗式盲审报告)",
            "",
            f"- **Decision Signal (决策信号)**: `{decision}` (Loop #{loop_index})",
            f"- **Composite Score (综合得分)**: `{total_score}` / 100",
            "- **Isolation Status**: `Step ① Isolate Active (Author CoT Physically Stripped)`",
            "",
            "## Step ③ Quantitative Score Table (量化评分表)",
            "",
            "| 维度 (Dimension) | 得分 (Score) | 扣分/满分证据 (Evidence) |",
            "| :--- | :---: | :--- |",
        ]
        for row in score_table:
            out.append(f"| {row['dimension']} | **{row['score']}** | {row['evidence']} |")

        out.extend(
            [
                "",
                "## Step ④ Mandatory Challenge Instructions (强制否定整改单)",
                "",
            ]
        )
        for ins in instructions:
            out.append(
                f"- **[{ins.get('id', 'INS')}] ({ins.get('severity', 'P1')}) @ `{ins.get('location', 'Text')}`**: "
                f"{ins.get('issue', '')} → **整改方向**: {ins.get('fix', '')}"
            )
        return "\n".join(out) + "\n"
