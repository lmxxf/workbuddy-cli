#!/usr/bin/env python3
"""
Example 04: 0-LLM HTML AST Quality Gate (`review_html.py`), "模 拟 人 生 4" Bugfix & Excel `<v>` Recalc
======================================================================================================
Demonstrates Tencent WorkBuddyAI's genuine engineering gems (extracted & enhanced in `workbuddy-cli`):
1. `review_html_ast`: 859-line deterministic 0-LLM HTML/CSS AST gatekeeper (`review_html.py`) that catches:
   - Bare CSS color literals (`#ff0000`) & bare font sizes (`14px`) outside `:root` variables
   - Skipped heading levels (`<h1>` -> `<h3>`)
   - Missing GB/T 9704-2012 red-header elements (`--genre government-doc`)
2. `fix_sims4_cover_centering_bug`: Fixes the notorious `"模  拟  人  生  4"` full-width justification
   inheritance bug when converting HTML `<section role="cover">` to Word `.docx`.
3. `recalc_xlsx_formulas`: Evaluates `<f>` formulas and backfills `<v>` cached values inside `.xlsx`
   OOXML (`xl/worksheets/sheet1.xml`) + stamps `GB 45438-2025` AIGC implicit metadata so WeChat/mobile
   previews never show blank `None`!
"""

import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workbuddy_cli.tools.office_suite import (
    SML_NS,
    convert_html_to_docx,
    create_sample_xlsx_without_cache,
    fix_sims4_cover_centering_bug,
    recalc_xlsx_formulas,
    render_government_doc_html,
    review_html_ast,
)


def main() -> None:
    print("=" * 88)
    print("📄 [04] WorkBuddy-CLI: 零 LLM HTML AST 门禁 + 『模 拟 人 生 4』居中修复 + Excel `<v>` 公式回填")
    print("=" * 88)

    # 1. Test 0-LLM HTML AST Gatekeeper on a flawed HTML sample
    bad_html = """<!DOCTYPE html>
<html>
<head>
<style>
p { text-align: justify; color: #333333; font-size: 14px; }
</style>
</head>
<body>
<section role="cover">
  <h1>模拟人生4</h1>
  <p>年度项目技术总结报告</p>
</section>
<h1>第一章 概述</h1>
<h3>1.1 跳过了 H2 直接写 H3</h3>
<p>这里不仅跳级了标题，还在 CSS 里写了裸色值 #333333 和裸字号 14px，且封面继承了 justify 导致『模  拟  人  生  4』！</p>
</body>
</html>"""

    bad_report = review_html_ast(bad_html, genre="general")
    print("\n🔍 [1] 零 LLM 确定性 AST 门禁 (`review_html.py`) 拦截违规 HTML 实测：")
    print(f"  - 违规 HTML 审查得分: {bad_report.get('score')} / 100 | 是否放行: passed={bad_report.get('passed')}")
    for dim_name, dim_info in (bad_report.get("dimensions") or {}).items():
        if dim_info.get("issues"):
            print(f"  - [{dim_name}] 抓出违规项: {dim_info['issues'][:2]}")

    # 2. Fix the "模  拟  人  生  4" cover centering inheritance bug
    patched_html, fix_count = fix_sims4_cover_centering_bug(bad_html)
    print(f"\n🛠️  [2] 修复封面『模  拟  人  生  4』两端对齐继承 Bug (`fix_sims4_cover_centering_bug`)：")
    print(f"  - 自动为 `<section role=\"cover\">` 内块级元素补齐显式居中声明: 共修复 {fix_count} 处")
    for line in patched_html.splitlines():
        if "模拟人生4" in line or "年度项目技术总结报告" in line:
            print(f"    {line.strip()}")
    assert 'style="text-align: center;"' in patched_html

    # 3. Run full 3-Stage GB/T 9704-2012 Red-Header Government Document Pipeline
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        docx_out = tmp_path / "gov_notice.docx"
        gov_html = render_government_doc_html(
            title="关于全面推广零LLM确定性AST门禁与端侧算子探针的通知",
            sections=[
                {
                    "title": "总体要求与工程纪律",
                    "paragraphs": [
                        "各直属研究院、工程中心须全面废除浮夸的多智能体群聊传话模式，改用单上下文角色切换与确定性脚本门禁。"
                    ],
                },
                {
                    "title": "HTML 转 Word 零裸字面量标准",
                    "paragraphs": [
                        "所有办公文档必须通过 859 行 review_html.py AST 门禁检验，严禁出现裸色值、裸字号及标题跳级。"
                    ],
                },
                {
                    "title": "附则与落地时间表",
                    "paragraphs": [
                        "本通知自发布之日起施行，所有产出文件自动嵌入 GB 45438-2025 隐式标识。"
                    ],
                },
            ],
            org_name="国家人工智能安全与标准化委员会文件",
            org_code="国智发",
            year="2026",
            serial_no="42",
            signer_name="齐活林",
        )
        gov_gate = review_html_ast(gov_html, genre="government-doc")
        gov_docx = convert_html_to_docx(gov_html, docx_out)
        print("\n🏛️  [3] GB/T 9704-2012 党政机关红头公文三阶段流水线 (`--genre government-doc`)：")
        print(f"  - Stage 2 红头公文 HTML 门禁得分: {gov_gate.get('score')} / 100 | passed={gov_gate.get('passed')}")
        print(f"  - Stage 3 生成标准 OOXML `.docx`: {gov_docx['docx_path']} ({gov_docx['size_bytes']:,} bytes, 段落数={gov_docx['paragraphs_count']})")
        assert gov_gate.get("score", 0) >= 90
        assert docx_out.exists()

        # 4. Excel Formula `<v>` Cache Backfill & GB 45438-2025 AIGC Implicit Watermark
        xlsx_file = tmp_path / "financial_model.xlsx"
        create_sample_xlsx_without_cache(
            xlsx_file,
            rows=[
                ("A1", 1500),
                ("A2", 2500),
                ("A3", 4000),
                ("A4", "=SUM(A1:A3)"),
                ("A5", "=AVERAGE(A1:A3)"),
                ("B1", "=A4*1.25+200"),
            ],
        )

        # Inspect XML BEFORE recalc: verify <v> is missing on formula cells
        with zipfile.ZipFile(xlsx_file, "r") as zf:
            xml_before = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        ns = {"s": SML_NS}
        a4_before = xml_before.find(".//s:c[@r='A4']/s:v", ns)
        print("\n📊 [4] Excel 公式 `<v>` 缓存回填（解决微信/手机预览 `openpyxl` 公式全空白痛点）：")
        print(f"  - 重算前 `A4 (=SUM(A1:A3))` 的 `<v>` 缓存节点: {a4_before} (微信/手机预览直接显示空白 None！)")

        recalc_res = recalc_xlsx_formulas(xlsx_file, apply_aigc_label=True)
        with zipfile.ZipFile(xlsx_file, "r") as zf:
            xml_after = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        a4_after = xml_after.find(".//s:c[@r='A4']/s:v", ns)
        b1_after = xml_after.find(".//s:c[@r='B1']/s:v", ns)

        print(f"  - 重算后状态: status=`{recalc_res['status']}`, 共计算公式 {recalc_res['total_formulas']} 个, 错误 {recalc_res['total_errors']} 个")
        print(f"  - 重算后 `A4 (=SUM(A1:A3))` -> `<v>{a4_after.text}</v>` | `B1 (=A4*1.25+200)` -> `<v>{b1_after.text}</v>`")
        print(f"  - GB 45438-2025 AIGC 隐式元数据打标验证: {recalc_res['aigc_label']}")

        assert a4_before is None
        assert a4_after is not None and a4_after.text == "8000"
        assert b1_after is not None and b1_after.text == "10200"

    print("\n🎉 Example 04 全部断言通过！")


if __name__ == "__main__":
    main()
