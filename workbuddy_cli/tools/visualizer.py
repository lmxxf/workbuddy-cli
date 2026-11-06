"""
Visualizer Guidelines (`widget_guidelines`) & Interactive Widget Renderer (`show_widget`)
ported from WorkBuddyAI's `visualizer_guidelines_full.js` (26,803 bytes).

Enforces WorkBuddy's strict streaming-safe visual rules:
1. No HTML/CSS comments (`<!-- -->`, `/* */`), no gradients (`linear-gradient`, `radial-gradient`),
   no drop-shadows (`box-shadow`, `drop-shadow`), no `blur()` (anti-flicker during token streaming).
2. SVG viewBox locked to `"0 0 680 H"`, font-weight restricted to `400` or `500`, font-size >= 11px.
3. Box width formula: `rect_width = max(title_chars * 7, subtitle_chars * 6) + 24`,
   single-line height = `44px`, two-line height = `56px`.
4. 9 Color Palettes (`c-purple`, `c-teal`, `c-coral`, `c-pink`, `c-gray`, `c-blue`, `c-green`, `c-amber`, `c-red`)
    across 7 stops (`50, 100, 200, 400, 600, 800, 900`).
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..config import ASSETS_DIR


COLOR_RAMPS: Dict[str, Dict[int, str]] = {
    "c-purple": {50: "#EEEDFE", 100: "#CECBF6", 200: "#AFA9EC", 400: "#7F77DD", 600: "#534AB7", 800: "#3C3489", 900: "#26215C"},
    "c-teal":   {50: "#E1F5EE", 100: "#9FE1CB", 200: "#5DCAA5", 400: "#1D9E75", 600: "#0F6E56", 800: "#085041", 900: "#04342C"},
    "c-coral":  {50: "#FAECE7", 100: "#F5C4B3", 200: "#F0997B", 400: "#D85A30", 600: "#993C1D", 800: "#712B13", 900: "#4A1B0C"},
    "c-pink":   {50: "#FBEAF0", 100: "#F4C0D1", 200: "#ED93B1", 400: "#D4537E", 600: "#993556", 800: "#72243E", 900: "#4B1528"},
    "c-gray":   {50: "#F1EFE8", 100: "#D3D1C7", 200: "#B4B2A9", 400: "#888780", 600: "#5F5E5A", 800: "#444441", 900: "#2C2C2A"},
    "c-blue":   {50: "#E6F1FB", 100: "#B5D4F4", 200: "#85B7EB", 400: "#378ADD", 600: "#185FA5", 800: "#0C447C", 900: "#042C53"},
    "c-green":  {50: "#EAF3DE", 100: "#C0DD97", 200: "#97C459", 400: "#639922", 600: "#3B6D11", 800: "#27500A", 900: "#173404"},
    "c-amber":  {50: "#FAEEDA", 100: "#FAC775", 200: "#EF9F27", 400: "#BA7517", 600: "#854F0B", 800: "#633806", 900: "#412402"},
    "c-red":    {50: "#FCEBEB", 100: "#F7C1C1", 200: "#F09595", 400: "#E24B4A", 600: "#A32D2D", 800: "#791F1F", 900: "#501313"},
}

VALID_MODULES = ("diagram", "mockup", "interactive", "chart", "art")


def compute_box_dimensions(title: str, subtitle: str = "") -> Dict[str, int]:
    """
    Implements WorkBuddy's exact SVG node sizing formula:
      `rect_width = max(title_chars * 7, subtitle_chars * 6) + 24`
      `height = 56 if subtitle else 44`
    """
    t_len = sum(2 if ord(ch) > 127 else 1 for ch in title)
    s_len = sum(2 if ord(ch) > 127 else 1 for ch in subtitle)
    width = max(t_len * 7, s_len * 6, 80) + 24
    height = 56 if subtitle else 44
    return {"width": width, "height": height}


def load_widget_guidelines(modules: List[str]) -> str:
    """Loads requested design modules from `visualizer_guidelines_full.js`."""
    js_path = ASSETS_DIR / "visualizer_guidelines_full.js"
    raw = js_path.read_text(encoding="utf-8") if js_path.exists() else ""
    selected = [m for m in modules if m in VALID_MODULES] or ["diagram"]
    header = (
        f"# WorkBuddy Visualizer Guidelines (Loaded modules: {', '.join(selected)})\n"
        "- ViewBox MUST be `0 0 680 H` (safe canvas x=40..640).\n"
        "- NO gradients, NO drop-shadows, NO blur, NO HTML/CSS comments.\n"
        "- Box sizing formula: `rect_width = max(title_chars * 7, subtitle_chars * 6) + 24`, height = 44px (1-line) or 56px (2-line).\n"
        "- Font weights ONLY 400 or 500 (never 600/700). Minimum font-size: 11px.\n"
    )
    return header + "\n" + raw[:12000]


def audit_widget_code(widget_code: str) -> Dict[str, Any]:
    """Audits SVG/HTML widget code against WorkBuddy's streaming anti-flicker & layout rules."""
    violations = []
    if "<!--" in widget_code or "/*" in widget_code:
        violations.append("Contains HTML/CSS comments (forbidden by streaming token rules)")
    if re.search(r"linear-gradient|radial-gradient", widget_code, re.IGNORECASE):
        violations.append("Contains CSS/SVG gradients (causes DOM streaming flicker)")
    if re.search(r"box-shadow|drop-shadow", widget_code, re.IGNORECASE):
        violations.append("Contains drop shadows (forbidden by VisualizerGuidelines)")
    if "<svg" in widget_code.lower() and 'viewBox="0 0 680' not in widget_code:
        violations.append('SVG viewBox width is not locked to "0 0 680 H"')
    if re.search(r'font-weight\s*[:=]\s*["\']?(?:600|700|800|bold)', widget_code, re.IGNORECASE):
        violations.append("Uses font-weight >= 600 (only 400 and 500 allowed)")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
    }


def generate_architecture_svg_widget(
    title: str,
    nodes: List[Dict[str, str]],
    theme: str = "dark",
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Generates a 100% guidelines-compliant interactive SVG architecture diagram (`viewBox="0 0 680 H"`),
    using exact 63-stop color ramps and `onclick="sendPrompt(...)"` hooks.
    """
    is_dark = theme.lower() == "dark"
    bg_color = "#181816" if is_dark else "#FAF9F5"
    text_primary = "#EDEDEB" if is_dark else "#1F1E1D"
    arrow_stroke = "#888780"

    n_count = max(len(nodes), 1)
    canvas_h = max(140, 80 + n_count * 84)

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 {canvas_h}" width="100%">',
        '<defs>',
        f'<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
        f'<path d="M2 1L8 5L2 9" fill="none" stroke="{arrow_stroke}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
        '</marker>',
        '</defs>',
        f'<rect x="0" y="0" width="680" height="{canvas_h}" rx="12" fill="{bg_color}"/>',
        f'<text x="340" y="36" text-anchor="middle" font-family="system-ui, -apple-system, sans-serif" font-size="14" font-weight="500" fill="{text_primary}">{title}</text>',
    ]

    palette_cycle = ["c-purple", "c-teal", "c-blue", "c-amber", "c-coral", "c-green"]
    y_cursor = 60

    for idx, node in enumerate(nodes):
        n_title = node.get("title", f"Stage {idx + 1}")
        n_sub = node.get("subtitle", "")
        ramp_key = node.get("color", palette_cycle[idx % len(palette_cycle)])
        ramp = COLOR_RAMPS.get(ramp_key, COLOR_RAMPS["c-purple"])

        fill_hex = ramp[800] if is_dark else ramp[50]
        stroke_hex = ramp[200] if is_dark else ramp[600]
        title_hex = ramp[100] if is_dark else ramp[800]
        sub_hex = ramp[200] if is_dark else ramp[600]

        dims = compute_box_dimensions(n_title, n_sub)
        w = max(dims["width"], 280)
        h = dims["height"]
        x = (680 - w) // 2

        prompt_escaped = n_title.replace("'", "")
        svg_lines.append(
            f'<g style="cursor:pointer" onclick="sendPrompt(\'Tell me more about {prompt_escaped}\')">'
        )
        svg_lines.append(
            f'<rect x="{x}" y="{y_cursor}" width="{w}" height="{h}" rx="8" fill="{fill_hex}" stroke="{stroke_hex}" stroke-width="1"/>'
        )
        if n_sub:
            svg_lines.append(
                f'<text x="340" y="{y_cursor + 22}" text-anchor="middle" dominant-baseline="central" font-family="system-ui, -apple-system, sans-serif" font-size="14" font-weight="500" fill="{title_hex}">{n_title}</text>'
            )
            svg_lines.append(
                f'<text x="340" y="{y_cursor + 40}" text-anchor="middle" dominant-baseline="central" font-family="system-ui, -apple-system, sans-serif" font-size="12" font-weight="400" fill="{sub_hex}">{n_sub}</text>'
            )
        else:
            svg_lines.append(
                f'<text x="340" y="{y_cursor + h // 2}" text-anchor="middle" dominant-baseline="central" font-family="system-ui, -apple-system, sans-serif" font-size="14" font-weight="500" fill="{title_hex}">{n_title}</text>'
            )
        svg_lines.append("</g>")

        if idx < n_count - 1:
            arrow_y1 = y_cursor + h + 2
            arrow_y2 = y_cursor + h + 24
            svg_lines.append(
                f'<line x1="340" y1="{arrow_y1}" x2="340" y2="{arrow_y2}" stroke="{arrow_stroke}" stroke-width="1.5" marker-end="url(#arrow)"/>'
            )
        y_cursor += h + 28

    svg_lines.append("</svg>")
    svg_code = "\n".join(svg_lines)
    audit = audit_widget_code(svg_code)

    saved_path = None
    if output_path:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(svg_code, encoding="utf-8")
        saved_path = str(out_p)

    return {
        "title": title,
        "svg": svg_code,
        "audit": audit,
        "saved_path": saved_path,
    }
