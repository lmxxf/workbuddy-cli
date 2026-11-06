"""
Comprehensive Automated Test Suite for `workbuddy-cli`.
Verifies all 10 reverse-engineered & enhanced subsystems.
"""

import json
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from workbuddy_cli.config import WorkBuddyConfig, discover_agents_md
from workbuddy_cli.memory import (
    SoulMemoryManager,
    append_invisible_run_marker,
    decode_invisible_run_marker,
)
from workbuddy_cli.prompt_engine import PromptEngine
from workbuddy_cli.compactor import (
    HistoryEngineeringCompactor,
    ThreeStageCompactor,
    FIXED_CONTEXT_SUMMARY_PROMPT,
    BUGGY_TENCENT_HEADER,
)
from workbuddy_cli.skill_router import SkillRouter, RecallIndex, SkillItem
from workbuddy_cli.tools.safe_shell import (
    SafeTrashInterceptor,
    DocumentBackupTransaction,
    HIGH_RISK_WARNING_BANNER,
)
from workbuddy_cli.tools.visualizer import (
    compute_box_dimensions,
    audit_widget_code,
    generate_architecture_svg_widget,
)
from workbuddy_cli.tools.office_suite import (
    review_html_ast,
    fix_sims4_cover_centering_bug,
    render_government_doc_html,
    convert_html_to_docx,
    create_sample_xlsx_without_cache,
    recalc_xlsx_formulas,
    SML_NS,
)
from workbuddy_cli.tools.critic_engine import CriticGeneratorEngine
from workbuddy_cli.tools.deep_research import (
    DeepResearchWorkflow,
    extract_json,
    extract_host_three_tier,
)
from workbuddy_cli.tools.expert_team import ExpertTeamEngine


class TestWorkBuddyCLI(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.cfg_dir = self.root / ".workbuddy-cli"
        self.ws_dir = self.root / "workspace"
        self.ws_dir.mkdir(parents=True, exist_ok=True)
        self.config = WorkBuddyConfig(
            api_key="test-key",
            model="deepseek-chat",
            mode="craft",
            style="sarcastic",
            prompt_profile="lean",
            config_dir=str(self.cfg_dir),
            workspace_dir=str(self.ws_dir),
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_01_soul_bootstrap_and_3tier_memory_and_watermark(self):
        mgr = SoulMemoryManager(self.cfg_dir, self.ws_dir)
        mgr.ensure_persona_workspace()

        # Initially in onboarding mode with BOOTSTRAP.md present
        vars_init = mgr.collect_identity_vars()
        self.assertEqual(vars_init["WorkspaceIdentityMode"], "onboarding")
        self.assertTrue(mgr.bootstrap_path.exists())
        self.assertIn("You're not a chatbot", vars_init["SoulContent"])

        # Complete onboarding -> updates IDENTITY.md & USER.md and deletes BOOTSTRAP.md
        res = mgr.complete_onboarding(agent_name="Suzaku", user_name="Zero")
        self.assertEqual(res["mode"], "normal")
        self.assertFalse(mgr.bootstrap_path.exists())

        vars_after = mgr.collect_identity_vars()
        self.assertEqual(vars_after["WorkspaceIdentityMode"], "normal")
        self.assertIn("Suzaku", vars_after["IdentityContent"])
        self.assertIn("Zero", vars_after["UserContent"])

        # Daily append-only log
        log_file = mgr.append_daily_log("Implemented DeepSeek agent loop")
        self.assertTrue(log_file.exists())
        self.assertIn("Implemented DeepSeek agent loop", log_file.read_text(encoding="utf-8"))

        # 48-bit Zero-Width Invisible Watermark
        marked = append_invisible_run_marker("Hello Enterprise WeChat", "run-20261106-xyz")
        self.assertEqual(len(marked), len("Hello Enterprise WeChat") + 48)
        decoded_hex = decode_invisible_run_marker(marked)
        self.assertIsNotNone(decoded_hex)
        self.assertEqual(len(decoded_hex), 12)

    def test_02_prompt_engine_styles_gating_and_agents_md(self):
        # Create an AGENTS.md in workspace
        (self.ws_dir / "AGENTS.md").write_text("# Custom Agent Rules\nAlways write clean Python.", encoding="utf-8")
        found = discover_agents_md(self.ws_dir)
        self.assertEqual(len(found), 1)

        engine = PromptEngine(self.config)
        styles = engine.list_styles()
        self.assertEqual(len(styles), 7)
        self.assertIn("sarcastic", styles)

        # Render full vs lean prompt
        full_prompt = engine.render_system_prompt(mode="expert", style="sarcastic", profile="full")
        self.assertIn("Model-aware complexity gating", full_prompt)
        self.assertIn("Stock price increase (涨) → Red (红色)", full_prompt)
        self.assertIn("No Script Files on Windows", full_prompt)
        self.assertIn("Sarcastic Roaster", full_prompt)
        self.assertIn("Always write clean Python.", full_prompt)

        # Model complexity tier gating check
        self.config.model = "hunyuan-lite"
        self.assertEqual(self.config.get_model_complexity_tier(), "minimal")
        self.config.model = "glm-4"
        self.assertEqual(self.config.get_model_complexity_tier(), "moderate")
        self.config.model = "deepseek-chat"
        self.assertEqual(self.config.get_model_complexity_tier(), "high")

        # Token footprint comparison
        audit = engine.compare_token_footprint()
        self.assertLess(audit["lean_tokens"], audit["full_tpl_tokens"])
        self.assertGreater(audit["token_savings_vs_desktop_pct"], 80.0)

    def test_03_skill_router_hybrid_bm25_cosine_and_validator(self):
        router = SkillRouter()
        matches_gov = router.match("起草一份符合 GB/T 9704 标准的红头公文通知", top_k=3)
        self.assertTrue(len(matches_gov) > 0)
        self.assertEqual(matches_gov[0]["id"], "doc-typeset-government-doc")

        matches_excel = router.match("Excel xlsx 公式重算防止微信预览空白", top_k=3)
        self.assertEqual(matches_excel[0]["id"], "sheet-recalc")

        # Test hybrid 0.8 * Cosine + 0.2 * BM25 scoring with explicit vectors
        idx = RecallIndex(embedding_weight=0.8)
        idx.rebuild(
            [
                SkillItem(id="s1", name="s1", description="alpha beta", file_path=Path("a"), vector=[1.0, 0.0]),
                SkillItem(id="s2", name="s2", description="alpha gamma", file_path=Path("b"), vector=[0.0, 1.0]),
            ]
        )
        res = idx.search("alpha", query_vector=[1.0, 0.0], top_k=2)
        self.assertEqual(res[0]["id"], "s1")
        self.assertAlmostEqual(res[0]["score"], 1.0, places=3)

        # Test enhanced quick_validate.py (detects broken file references)
        import importlib.util

        val_path = Path(__file__).resolve().parent.parent / "workbuddy_cli/assets/skills/skill-creator/scripts/quick_validate.py"
        spec = importlib.util.spec_from_file_location("quick_validate", str(val_path))
        val_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(val_mod)

        bad_skill_dir = self.root / "bad-skill"
        bad_skill_dir.mkdir()
        (bad_skill_dir / "SKILL.md").write_text(
            "---\nname: bad-skill\ndescription: A valid description\nagent_created: true\n---\nSee `scripts/non_existent.py`.\n",
            encoding="utf-8",
        )
        ok, msg = val_mod.validate_skill(bad_skill_dir)
        self.assertFalse(ok)
        self.assertIn("scripts/non_existent.py", msg)

    def test_04_compactor_and_fixed_hypnosis_bug(self):
        messages = [
            {"role": "user", "content": "<user_query>\nImplement feature X and run tests\n</user_query>"},
            {
                "role": "assistant",
                "content": "Writing feature X first.",
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "x.py", "content": "print('hello')\n" * 100}),
                        },
                    }
                ],
            },
            {"type": "function_call_result", "role": "tool", "content": "Huge tool output " * 200},
            {"type": "reasoning", "content": "Internal reasoning chain..."},
        ]
        eng = HistoryEngineeringCompactor.compact(messages)
        self.assertIn("<cb_summary>", eng["compactContent"])
        self.assertIn('"content": "<omitted>"', eng["compactContent"])
        self.assertIn("<result><omitted /></result>", eng["compactContent"])
        self.assertNotIn("Huge tool output", eng["compactContent"])

        # Verify our fixed LLM summary prompt removes Tencent's premature task-completion hypnosis bug
        self.assertNotIn(BUGGY_TENCENT_HEADER, FIXED_CONTEXT_SUMMARY_PROMPT)
        self.assertIn("Pending Tasks & Current Work", FIXED_CONTEXT_SUMMARY_PROMPT)

        compactor = ThreeStageCompactor(max_context_tokens=300000, sufficiency_pct=0.15)
        res = compactor.run_compact(messages)
        self.assertFalse(res["used_llm"])
        self.assertTrue(res["fixed_hypnosis_bug"])

    def test_05_safe_delete_trash_interceptor_and_shim(self):
        trash_root = self.root / "trash_sandbox"
        interceptor = SafeTrashInterceptor(trash_dir=trash_root)

        # Create a victim file and directory in workspace, then run python script calling os.remove & shutil.rmtree
        victim_file = self.ws_dir / "important_report.txt"
        victim_file.write_text("Do not lose this data!", encoding="utf-8")
        victim_dir = self.ws_dir / "project_folder"
        victim_dir.mkdir()
        (victim_dir / "main.py").write_text("print(42)", encoding="utf-8")

        py_code = f"""
import os, shutil
os.remove({repr(str(victim_file))})
shutil.rmtree({repr(str(victim_dir))})
"""
        run_res = interceptor.run_sandboxed_python(py_code, cwd=self.ws_dir)
        self.assertEqual(run_res["returncode"], 0)
        self.assertFalse(victim_file.exists())
        self.assertFalse(victim_dir.exists())
        # Both must be safely inside Trash/files!
        trashed_names = [Path(p).name for p in run_res["trash_files"]]
        self.assertEqual(len(trashed_names), 2)

        # Verify No-Go Zone protection on Desktop
        desktop_res = interceptor.safe_delete(Path.home() / "Desktop", allow_personal_dir=False)
        self.assertEqual(desktop_res["status"], "blocked")
        self.assertEqual(desktop_res["warning"], HIGH_RISK_WARNING_BANNER)

        # Verify 3-phase DocumentBackupTransaction rollback
        doc_p = self.ws_dir / "contract.docx"
        doc_p.write_text("Version 1 Original", encoding="utf-8")
        tx = DocumentBackupTransaction(backup_root=self.root / "backups")
        ticket = tx.prepare(doc_p)
        doc_p.write_text("Version 2 Corrupted", encoding="utf-8")
        self.assertTrue(tx.rollback(ticket, doc_p))
        self.assertEqual(doc_p.read_text(encoding="utf-8"), "Version 1 Original")

    def test_06_visualizer_guidelines_and_svg_generator(self):
        dims = compute_box_dimensions("RecallIndex", "0.8*Cosine + 0.2*BM25")
        self.assertEqual(dims["height"], 56)
        self.assertGreaterEqual(dims["width"], 21 * 6 + 24)

        out_svg = self.ws_dir / "arch.svg"
        res = generate_architecture_svg_widget(
            title="WorkBuddy Core Pipeline",
            nodes=[
                {"title": "Stage 1: Soul & Memory", "subtitle": "SOUL.md + 3-Tier Memory"},
                {"title": "Stage 2: Hybrid Recall", "subtitle": "0.8*Cosine + 0.2*BM25"},
            ],
            output_path=out_svg,
        )
        self.assertTrue(res["audit"]["passed"], f"Violations: {res['audit']['violations']}")
        self.assertTrue(out_svg.exists())

        # Verify bad SVG with gradient/comment is caught by audit_widget_code
        bad_audit = audit_widget_code('<svg viewBox="0 0 500 200"><!-- comment --><defs><linearGradient/></defs></svg>')
        self.assertFalse(bad_audit["passed"])
        self.assertGreaterEqual(len(bad_audit["violations"]), 2)

    def test_07_office_suite_review_html_sims4_fix_gov_docx_and_xlsx_recalc(self):
        # 1. Test '模 拟 人 生 4' cover centering inheritance fix
        buggy_html = '<section role="cover"><h1>模拟人生4</h1><p class="subtitle">年度报告</p></section>'
        fixed_html, count = fix_sims4_cover_centering_bug(buggy_html)
        self.assertEqual(count, 2)
        self.assertIn('style="text-align: center;">模拟人生4</h1>', fixed_html)

        # 2. Test GB/T 9704 government doc HTML + 0-LLM review_html.py gatekeeper + .docx generation
        gov_html = render_government_doc_html(
            title="关于全面落实人工智能安全沙箱规范的通知",
            sections=[
                {"title": "总体要求", "paragraphs": ["各单位应高度重视安全沙箱建设。"]},
                {"title": "技术标准", "paragraphs": ["全面实行零 LLM AST 门禁检测。"]},
                {"title": "监督检查", "paragraphs": ["对违规使用裸色值的模板予以打回。"]},
            ],
        )
        report = review_html_ast(gov_html, genre="government-doc")
        self.assertTrue(report["passed"], f"review_html failed: {report}")
        self.assertGreaterEqual(report["score"], 85)

        docx_path = self.ws_dir / "gov_notice.docx"
        docx_info = convert_html_to_docx(gov_html, docx_path)
        self.assertTrue(docx_path.exists())
        self.assertGreater(docx_info["size_bytes"], 500)

        # 3. Test Excel formula recalculation (<f> -> <v> cache backfill) & GB 45438-2025 AIGC label
        xlsx_path = self.ws_dir / "finance.xlsx"
        create_sample_xlsx_without_cache(xlsx_path)

        # Before recalc: verify <c r="A4"> has <f> but NO <v>
        with zipfile.ZipFile(xlsx_path, "r") as zf:
            xml_before = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("<f>SUM(A1:A3)</f>", xml_before)
        self.assertNotIn("<v>750</v>", xml_before)

        recalc_res = recalc_xlsx_formulas(xlsx_path, apply_aigc_label=True)
        self.assertEqual(recalc_res["status"], "success")
        self.assertEqual(recalc_res["total_formulas"], 3)
        self.assertEqual(recalc_res["evaluated_cells"]["A4"]["cached_value"], 750)
        self.assertEqual(recalc_res["evaluated_cells"]["A5"]["cached_value"], 250)
        self.assertEqual(recalc_res["evaluated_cells"]["B1"]["cached_value"], 1550)
        self.assertTrue(recalc_res["aigc_label"]["ok"])

        # After recalc: verify <v>750</v> is physically written inside xl/worksheets/sheet1.xml
        with zipfile.ZipFile(xlsx_path, "r") as zf:
            root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
            ns = {"s": SML_NS}
            a4_v = root.find(".//s:c[@r='A4']/s:v", ns)
            self.assertIsNotNone(a4_v)
            self.assertEqual(a4_v.text, "750")

    def test_08_critic_generator_blind_review_mandatory_quotas(self):
        engine = CriticGeneratorEngine(min_issues=2, min_instructions=3, pass_score=85)
        res = engine.run_review("这是一份非常简短的草稿，没有任何数据支撑。")
        self.assertGreaterEqual(res["deducted_dimensions_count"], 2)
        self.assertGreaterEqual(res["instructions_count"], 3)
        self.assertIn(res["decision"], ("REVISE", "PASS", "DEGRADED"))
        self.assertIn("Step ① Isolate Active", res["markdown_report"])

    def test_09_deep_research_2_of_3_jury_and_abstain_quorum(self):
        wf = DeepResearchWorkflow()
        # 2/3 refutations -> killed
        c_killed = wf.adjudicate_claim(
            {"claim": "Fake claim"},
            [{"refuted": True}, {"refuted": True}, {"refuted": False}],
        )
        self.assertFalse(c_killed["survives"])

        # 1/3 refutation -> survives
        c_survived = wf.adjudicate_claim(
            {"claim": "Solid claim"},
            [{"refuted": False}, {"refuted": False}, {"refuted": True}],
        )
        self.assertTrue(c_survived["survives"])

        # All abstain (nulls) -> must NOT falsely survive!
        c_abstain = wf.adjudicate_claim({"claim": "Unverified claim"}, [None, None, None])
        self.assertFalse(c_abstain["survives"])

        # 3-tier malformed URL host extraction
        self.assertEqual(extract_host_three_tier("www.workbuddy.cn/docs/overview"), "workbuddy.cn")
        self.assertEqual(extract_host_three_tier("[Title](https://sub.example.org/path), extra"), "sub.example.org")

        full_run = wf.run("WorkBuddy Tool RAG architecture")
        self.assertGreaterEqual(len(full_run["confirmed"]), 1)
        self.assertGreaterEqual(len(full_run["killed"]), 1)
        self.assertIn("## Refuted Claims", full_run["markdown_report"])

    def test_10_expert_team_qi_huolin_spawn_vs_role_switch(self):
        team_engine = ExpertTeamEngine()
        teams = team_engine.list_expert_teams()
        self.assertEqual(len(teams), 10)
        team_ids = [t["id"] for t in teams]
        self.assertIn("SoftwareCompany", team_ids)
        self.assertIn("TradingAgentTeam", team_ids)

        # Mode 1: spawn (Boss Qi Huolin hub-and-spoke with <teammate-message> XML relay & double token tax)
        spawn_res = team_engine.run_team_workflow(
            team_id="SoftwareCompany",
            task_prompt="开发一个带回收站保护的 CLI 工具",
            mode="spawn",
        )
        self.assertEqual(spawn_res["lead"]["name_zh"], "齐活林")
        stage_names = [s["name_zh"] for s in spawn_res["stages"]]
        self.assertEqual(stage_names, ["许清楚", "高见远", "寇豆码", "严过关"])
        self.assertGreater(spawn_res["lead_copy_paste_tax_tokens"], 0)
        self.assertIn("<teammate-message", spawn_res["markdown_report"])

        # Mode 2: role-switch (In-place single-context hat swap with zero relay token tax)
        rs_res = team_engine.run_team_workflow(
            team_id="SoftwareCompany",
            task_prompt="开发一个带回收站保护的 CLI 工具",
            mode="role-switch",
        )
        self.assertEqual(rs_res["lead_copy_paste_tax_tokens"], 0)
        self.assertIn("[角色切换]", rs_res["final_summary"])

    def test_11_slash_autocompletion_context_and_prefix_resolution(self):
        from workbuddy_cli.agent_client import WorkBuddyAgentClient
        from workbuddy_cli.cli import (
            get_subcommand_completions,
            resolve_slash_command_name,
            show_context_dashboard,
        )

        client = WorkBuddyAgentClient(self.config)

        # Prefix resolution: /cont -> /context, /m -> ambiguous (/mode, /model)
        resolved_cont, _ = resolve_slash_command_name("/cont")
        self.assertEqual(resolved_cont, "/context")
        resolved_m, cands_m = resolve_slash_command_name("/m")
        self.assertIsNone(resolved_m)
        self.assertIn("/mode", cands_m)
        self.assertIn("/model", cands_m)

        # Level-2 completions for /mode, /style, /model, /profile, /compact, /team
        mode_cands = [c[0] for c in get_subcommand_completions("/mode", [], "", client)]
        self.assertEqual(set(mode_cands), {"craft", "ask", "expert", "plan"})

        style_cands = [c[0] for c in get_subcommand_completions("/style", ["sar"], "sar", client)]
        self.assertEqual(style_cands, ["sarcastic"])

        team_cands = [c[0] for c in get_subcommand_completions("/team", ["Soft"], "Soft", client)]
        self.assertIn("SoftwareCompany", team_cands)

        # Level-3 completions for `/team SoftwareCompany ` -> spawn / role-switch
        team_mode_cands = [c[0] for c in get_subcommand_completions("/team", ["SoftwareCompany"], "", client)]
        self.assertEqual(set(team_mode_cands), {"spawn", "role-switch"})

        # /context dashboard data verification
        ctx_info = show_context_dashboard(self.config, client, [])
        self.assertEqual(ctx_info["model"], "deepseek-chat")
        self.assertGreater(ctx_info["total_tokens"], 500)


if __name__ == "__main__":
    unittest.main()
