 getAgentMailAccessToken(e)}catch(e){return errorResult(`Failed to obtain access token: ${e instanceof Error?e.message:String(e)}`)}let a=(0,W.dirname)(r),o=`./${(0,W.basename)(r)}`;try{let t=await execAgentlyCli([`attachment`,`+upload`,`--file`,o],{cwd:a,timeoutMs:_O,token:i,resolveBundledAsset:e.resolveBundledAsset});return t.ok?successResult(t.data??{message:`Upload succeeded but no data returned.`}):errorResult(t.error||`Upload failed (CLI returned ok=false).`)}catch(e){return errorResult(`Upload failed: ${e instanceof Error?e.message:String(e)}`)}}}}var vO=new Set([`diagram`,`mockup`,`interactive`,`art`,`chart`]),VisualizerGuidelines=class{static build(e=[]){let t=this.normalizeModules(e),n=[this.getCoreDesignSystem(),this.getColorPalette()];t.some(e=>e===`diagram`||e===`art`)&&n.push(this.getSvgSetup()),t.some(e=>e===`mockup`||e===`interactive`||e===`chart`)&&n.push(this.getUIComponents());for(let e of t)switch(e){case`diagram`:n.push(this.getDiagramTypes());break;case`mockup`:case`interactive`:n.push(this.getInteractiveGuidance());break;case`chart`:n.push(this.getChartJsRules()),n.push(this.getD3ChoroplethRules());break;case`art`:n.push(this.getArtGuidance())}return n.join(`

`)}static normalizeModules(e){let t=[],n=new Set;for(let r of e??[]){if(!r||typeof r!=`string`)continue;let e=r.trim();vO.has(e)&&!n.has(e)&&(n.add(e),t.push(e))}return t}static getCoreDesignSystem(){return'# Visualizer Core Design System\n\n## Philosophy\n- **Seamless**: Users shouldn\'t notice where the host UI ends and your widget begins.\n- **Flat**: No gradients, mesh backgrounds, noise textures, or decorative effects. Clean flat surfaces.\n- **Compact**: Show the essential inline. Explain the rest in text.\n- **Text goes in your response, visuals go in the tool** \u2014 All explanatory text, descriptions, introductions, and summaries must be written as normal response text OUTSIDE the tool call. The tool output should contain ONLY the visual element.\n\n## Streaming\nOutput streams token-by-token. Structure code so useful content appears early.\n- **HTML**: `<style>` (short) \u2192 content HTML \u2192 `<script>` last.\n- **SVG**: `<defs>` (markers) \u2192 visual elements immediately.\n- Prefer inline `style="..."` over `<style>` blocks \u2014 inputs/controls must look correct mid-stream.\n- Keep `<style>` under ~15 lines.\n- Gradients, shadows, and blur flash during streaming DOM diffs. Use solid flat fills instead.\n\n## Rules\n- No `<!-- comments -->` or `/* comments */` (waste tokens, break streaming)\n- No font-size below 11px\n- No emoji \u2014 use CSS shapes or SVG paths\n- No gradients, drop shadows, blur, glow, or neon effects\n- No dark/colored backgrounds on outer containers (transparent only \u2014 host provides the bg)\n- **Typography**: h1 = 15px, h2 = 14px, h3 = 13px \u2014 all `font-weight: 500`. Body text = 13px, weight 400, `line-height: 1.6`. **Two weights only: 400 regular, 500 bold.** Never use 600 or 700.\n- **Sentence case** always. Never Title Case, never ALL CAPS.\n- Never use `position: fixed`\n- No DOCTYPE, `<html>`, `<head>`, or `<body>` \u2014 just content fragments.\n- **Local images**: to show an image from the session workspace inside the widget, reference it by absolute path (`<img src="/abs/path.png">`; for SVG use `<image href="/abs/path.png">`). The host rewrites local paths to a loadable form automatically \u2014 do NOT hand-write `data:` base64 or custom protocols.\n- **CDN allowlist (CSP-enforced)**: scripts, fonts and other external resources may ONLY load from `cdnjs.cloudflare.com`, `esm.sh`, `cdn.jsdelivr.net`, `unpkg.com`.\n\n## CSS Variables\n\n| Category | Variables |\n|----------|-----------|\n| Backgrounds | `--color-background-primary` (white), `-secondary` (surfaces), `-tertiary` (page bg), `-info`, `-danger`, `-success`, `-warning` |\n| Text | `--color-text-primary` (black), `-secondary` (muted), `-tertiary` (hints), `-info`, `-danger`, `-success`, `-warning` |\n| Borders | `--color-border-tertiary` (0.15\u03B1, default), `-secondary` (0.3\u03B1, hover), `-primary` (0.4\u03B1), semantic `-info/-danger/-success/-warning` |\n| Typography | `--font-sans`, `--font-serif`, `--font-mono` |\n| Layout | `--border-radius-md` (8px), `--border-radius-lg` (12px \u2014 preferred for most components), `--border-radius-xl` (16px) |\n\n## Complexity budget (hard limits)\n- Box subtitles: \u22645 words\n- Colors: \u22642 ramps per diagram\n- Horizontal tier: \u22644 boxes at full width (~140px each)\n\n## Accessibility\n- For HTML widgets, begin with a visually-hidden `<h2 class="sr-only">` containing a one-sentence summary.\n- SVG widgets use `role="img"` with `<title>` and `<desc>` as first children.'}static getColorPalette(){return`# Color Palette (9 ramps \u00D7 7 levels)

Level meaning: 50=lightest fill, 100-200=light fills, 400=midtone, 600=accent/stroke, 800-900=text on light bg.

| Class | 50 | 100 | 200 | 400 | 600 | 800 | 900 |
|-------|----|-----|-----|-----|-----|-----|-----|
| c-purple | #EEEDFE | #CECBF6 | #AFA9EC | #7F77DD | #534AB7 | #3C3489 | #26215C |
| c-teal | #E1F5EE | #9FE1CB | #5DCAA5 | #1D9E75 | #0F6E56 | #085041 | #04342C |
| c-coral | #FAECE7 | #F5C4B3 | #F0997B | #D85A30 | #993C1D | #712B13 | #4A1B0C |
| c-pink | #FBEAF0 | #F4C0D1 | #ED93B1 | #D4537E | #993556 | #72243E | #4B1528 |
| c-gray | #F1EFE8 | #D3D1C7 | #B4B2A9 | #888780 | #5F5E5A | #444441 | #2C2C2A |
| c-blue | #E6F1FB | #B5D4F4 | #85B7EB | #378ADD | #185FA5 | #0C447C | #042C53 |
| c-green | #EAF3DE | #C0DD97 | #97C459 | #639922 | #3B6D11 | #27500A | #173404 |
| c-amber | #FAEEDA | #FAC775 | #EF9F27 | #BA7517 | #854F0B | #633806 | #412402 |
| c-red | #FCEBEB | #F7C1C1 | #F09595 | #E24B4A | #A32D2D | #791F1F | #501313 |

**Light/dark mode quick pick:**
- **Light mode**: 50 fill + 600 stroke + **800 title / 600 subtitle**
- **Dark mode**: 800 fill + 200 stroke + **100 title / 200 subtitle**`}static getSvgSetup(){return`# SVG Setup Rules

- viewBox fixed to \`"0 0 680 H"\`, **680 must not change**, it is the basis for all coordinate calculations. \`width="100%"\` on root \`<svg>\`.
- H = bottommost element + 20px, do not guess.
- Safe area: x=40 to x=640, y=40 to y=(H-40). Background transparent.
- One SVG per tool call.
- No rotated text.
- Use 0.5px strokes for diagram borders and edges.
- Every \`<path>\` or \`<polyline>\` used as a connector MUST have \`fill="none"\`.

## Pre-built classes

| Class | Description |
|-------|-------------|
| \`class="t"\` | sans 14px primary |
| \`class="ts"\` | sans 12px secondary |
| \`class="th"\` | sans 14px medium (500) |
| \`class="box"\` | neutral rect (bg-secondary fill, border stroke) |
| \`class="node"\` | clickable group with hover effect |
| \`class="arr"\` | arrow line (1.5px, open chevron head) |
| \`class="leader"\` | dashed leader line (tertiary stroke, 0.5px) |
| \`class="c-{ramp}"\` | colored node \u2014 apply to \`<g>\` or rect/circle/ellipse (not paths) |

## Arrow marker (must include in every SVG \`<defs>\`)

\`\`\`svg
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
    markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke"
      stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </marker>
</defs>
\`\`\`

## Font size calibration

| Text | Chars | Weight | Size | Rendered width |
|------|-------|--------|------|----------------|
| Title | 12 | 500 | 14px | ~88px |
| Subtitle | 16 | 400 | 13px | ~104px |
| Body | 24 | 400 | 13px | ~156px |
| Caption | 20 | 400 | 12px | ~120px |

Box width formula: \`rect_width = max(title_chars \u00D7 7, subtitle_chars \u00D7 6) + 24\``}static getDiagramTypes(){return`# Diagram Guidance

## Flowchart
For sequential processes, cause-and-effect, decision trees.

- **Spacing**: 60px minimum between boxes, 24px padding inside boxes, 12px between text and edges.
- **Layout**: Prefer single-direction flows. Keep diagrams simple \u2014 max 4-5 nodes per diagram.
- **Cycles don't get drawn as rings.** Build a stepper in HTML instead. Only fall back to a linear SVG with curved return arrow when there's one input and one output total.
- Keep all nodes the same height when they have the same content type (single-line = 44px, two-line = 56px).
- Every \`<text>\` inside a box needs \`dominant-baseline="central"\`.

Single-line node example (44px):
\`\`\`svg
<g class="node c-blue" onclick="sendPrompt('...')">
  <rect x="100" y="20" width="180" height="44" rx="8" stroke-width="0.5"/>
  <text class="th" x="190" y="42" text-anchor="middle" dominant-baseline="central">T-cells</text>
</g>
\`\`\`

Two-line node example (56px):
\`\`\`svg
<g class="node c-blue" onclick="sendPrompt('...')">
  <rect x="100" y="20" width="200" height="56" rx="8" stroke-width="0.5"/>
  <text class="th" x="200" y="38" text-anchor="middle" dominant-baseline="central">Dendritic cells</text>
  <text class="ts" x="200" y="56" text-anchor="middle" dominant-baseline="central">Detect foreign antigens</text>
</g>
\`\`\`

## Structural diagram
For concepts where physical or logical containment matters \u2014 things inside other things.

- Outermost container: large rounded rect, rx=20-24, lightest fill (50 stop), 0.5px stroke.
- Inner regions: medium rounded rects, rx=8-12, next shade fill (100-200 stop).
- 20px minimum padding inside every container. Max 2-3 nesting levels.
- **Database schemas / ERDs \u2014 use mermaid.js \`erDiagram\`, not SVG.**

## Illustrative diagram
For building *intuition* \u2014 physical cross-sections or abstract spatial metaphors.

- **Physical subjects**: draw simplified versions (cross-sections, cutaways). A water heater is a tank with a burner underneath.
- **Abstract subjects**: invent spatial metaphors. A transformer is a stack of horizontal slabs. A hash function is a funnel scattering items into buckets.
- **Color encodes intensity**, not category. Warm ramps = heat/energy/active. Cool ramps = cold/calm/dormant.
- **Prefer interactive over static.** If the real-world system has a control, give the diagram that control.
- One \`<linearGradient>\` per diagram permitted (continuous physical properties only).
- CSS \`@keyframes\` animation permitted (\`transform\` and \`opacity\` only, loops under ~2s). Wrap in \`@media (prefers-reduced-motion: no-preference)\`.
- Place labels *outside* the drawn object with thin leader lines.

## Diagram type routing

| User says | Type | What to draw |
|-----------|------|-------------|
| "how do LLMs work" | Illustrative | Token row, stacked layer slabs, attention threads |
| "transformer architecture" | Structural | Labelled boxes: embedding, attention heads, FFN, layer norm |
| "what are the training steps" | Flowchart | Forward \u2192 loss \u2192 backward \u2192 update |
| "TCP handshake sequence" | Flowchart | SYN \u2192 SYN-ACK \u2192 ACK |
| "how does TCP work" | Illustrative | Two endpoints, numbered packets in flight, an ACK returning |
| "explain the Krebs cycle / event loop" | HTML stepper | Click through stages. Never a ring. |
| "draw the database schema" | mermaid.js | \`erDiagram\` syntax. Not SVG. |`}static getUIComponents(){return`# UI Components

## Aesthetic
Flat, clean, white surfaces. Minimal 0.5px borders. Generous whitespace. No gradients, no shadows (except functional focus rings). Everything should feel native to the host UI.

## Tokens
- Borders: always \`0.5px solid var(--color-border-tertiary)\` (or \`-secondary\` for emphasis)
- Corner radius: \`var(--border-radius-md)\` for most elements, \`var(--border-radius-lg)\` for cards
- Cards: white bg (\`var(--color-background-primary)\`), 0.5px border, radius-lg, padding 1rem 1.25rem
- Form elements (input, select, textarea, button, range slider) are pre-styled \u2014 write bare tags.
- Buttons: pre-styled with transparent bg, 0.5px border-secondary. If it triggers sendPrompt, append a \u2197 arrow.
- **Round every displayed number.** Use \`Math.round()\`, \`.toFixed(n)\`, or \`Intl.NumberFormat\`.
- Spacing: use rem for vertical rhythm (1rem, 1.5rem, 2rem), px for component-internal gaps (8px, 12px, 16px)

## Metric cards
\`background: var(--color-background-secondary)\`, no border, \`border-radius: var(--border-radius-md)\`, padding 1rem. Muted 13px label above, 24px/500 number below. Use in grids of 2-4 with \`gap: 12px\`.

## Layout
- Editorial (explanatory content): no card wrapper, prose flows naturally
- Card (bounded objects like a contact record, receipt): single raised card wraps the whole thing
- Don't put tables here \u2014 output them as markdown in your response text instead
- Grid: use \`minmax(0, 1fr)\` to clamp overflow
- Table overflow: use \`table-layout: fixed\` in constrained layouts (\u2264700px)

## Mockup presentation
Contained mockups (mobile screens, chat threads, modals) should sit on a background surface. Full-width mockups (dashboards, settings pages) do not need an extra wrapper.

## Pattern 1: Interactive explainer
Use HTML for the interactive controls \u2014 sliders, buttons, live state displays, charts. No card wrapper. Whitespace is the container. Use \`sendPrompt()\` to let users ask follow-ups.

## Pattern 2: Compare options
Use \`repeat(auto-fit, minmax(160px, 1fr))\`. Featured card: \`border: 2px solid var(--color-border-info)\` (the only scenario where 2px border is allowed). Badge: \`background: var(--color-background-info); color: var(--color-text-info); font-size: 12px\`.

## Pattern 3: Data record
Wrap in a single raised card. Avatar/initials circle: 44px, \`background: var(--color-background-info)\`, \`color: var(--color-text-info)\`, \`font-weight: 500\`.

\`\`\`html
<div style="background: var(--color-background-primary); border-radius: var(--border-radius-lg); border: 0.5px solid var(--color-border-tertiary); padding: 1rem 1.25rem;">
  <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
    <div style="width: 44px; height: 44px; border-radius: 50%; background: var(--color-background-info); display: flex; align-items: center; justify-content: center; font-weight: 500; font-size: 14px; color: var(--color-text-info);">MR</div>
    <div>
      <p style="font-weight: 500; font-size: 15px; margin: 0;">Maya Rodriguez</p>
      <p style="font-size: 13px; color: var(--color-text-secondary); margin: 0;">VP of Engineering</p>
    </div>
  </div>
</div>
\`\`\``}static getInteractiveGuidance(){return`# Interactive Guidance
- Use HTML for the interactive controls \u2014 sliders, buttons, live state displays, charts.
- Keep prose explanations in your normal response text, not embedded in the HTML.
- Handle filtering, sorting, toggling, and calculations in JS instead. Use \`sendPrompt()\` only when the user's next step benefits from Claude thinking.
- For steppers: show all content stacked vertically during streaming. Post-streaming JS-driven steppers are fine.
- For cycles: HTML stepper with \`\u25CF \u25CB \u25CB\` position indicator. Next wraps from the last stage back to the first.`}static getChartJsRules(){return`# Charts (Chart.js)

## Setup
\`\`\`html
<div style="position: relative; width: 100%; height: 300px;">
  <canvas id="myChart" role="img" aria-label="Bar chart of quarterly revenue">Fallback text.</canvas>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"><\/script>
<script>
  new Chart(document.getElementById('myChart'), {
    type: 'bar',
    data: { labels: ['Q1','Q2','Q3','Q4'], datasets: [{ label: 'Revenue', data: [12,19,8,15] }] },
    options: { responsive: true, maintainAspectRatio: false }
  });
<\/script>
\`\`\`

## Rules
- Every \`<canvas>\` MUST have \`role="img"\`, a descriptive \`aria-label\`, and fallback text between the tags.
- Never rely on color alone to distinguish data series \u2014 pair each color with a secondary visual cue.
- Canvas cannot resolve CSS variables. Use hardcoded hex.
- Set height ONLY on the wrapper div, never on the canvas element itself.
- For horizontal bar charts: wrapper div height = \`(number_of_bars \u00D7 40) + 80\` pixels minimum.
- Load UMD build via \`cdnjs.cloudflare.com\`. Follow with plain \`<script>\` (no \`type="module"\`).
- Multiple charts: use unique IDs (\`myChart1\`, \`myChart2\`).
- Bubble/scatter charts: pad the scale range ~10% beyond your data range to avoid clipping.
- \u226412 categories: set \`scales.x.ticks: { autoSkip: false, maxRotation: 45 }\`.
- Negative values: \`-$5M\` not \`$-5M\`.

## Legends
Always disable default legend and use custom HTML:

\`\`\`js
plugins: { legend: { display: false } }
\`\`\`

\`\`\`html
<div style="display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 8px; font-size: 12px; color: var(--color-text-secondary);">
  <span style="display: flex; align-items: center; gap: 4px;">
    <span style="width: 10px; height: 10px; border-radius: 2px; background: #3266ad;"></span>Chrome 65%
  </span>
</div>
\`\`\``}static getD3ChoroplethRules(){return`# Geographic maps (D3 choropleth)

**Never invent coordinates** \u2014 no hand-drawn SVG paths, no inline GeoJSON. Fetch real topology or don't draw a map.

## Topology sources

| Coverage | URL | Projection | Object key |
|----------|-----|------------|------------|
| US states | \`https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json\` | \`d3.geoAlbersUsa()\` | \`.states\` |
| World countries | \`https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json\` | \`d3.geoNaturalEarth1()\` | \`.countries\` |
| Per-country subdivisions | \`https://cdn.jsdelivr.net/npm/datamaps@0.5.10/src/js/data/{iso3}.topo.json\` | varies | \`.{iso3}\` |

Fetch the topology URL first and check the real \`id\` and \`properties.name\` fields before building the component. CSP blocks \`raw.githubusercontent.com\` and other unlisted domains.

\`\`\`html
<div id="map" style="width: 100%;"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"><\/script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/topojson/3.0.2/topojson.min.js"><\/script>
<script>
const values = { 'California': 39, 'Texas': 30, 'New York': 19 };
const isDark = matchMedia('(prefers-color-scheme: dark)').matches;
const color = d3.scaleQuantize([0, 40], isDark ? d3.schemeBlues[5].slice().reverse() : d3.schemeBlues[5]);
const svg = d3.select('#map').append('svg').attr('viewBox', '0 0 900 560').attr('width', '100%');
const path = d3.geoPath(d3.geoAlbersUsa().scale(1100).translate([450, 280]));
d3.json('https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json').then(us => {
  svg.selectAll('path').data(topojson.feature(us, us.objects.states).features).join('path')
    .attr('d', path)
    .attr('stroke', isDark ? 'rgba(255,255,255,.15)' : '#fff')
    .attr('fill', d => color(values[d.properties.name] ?? 0));
});
<\/script>
\`\`\``}static getArtGuidance(){return'# Art and illustration\n\nUse SVG. Same technical rules (viewBox, safe area) but the aesthetic is different:\n\n- Fill the canvas \u2014 art should feel rich, not sparse.\n- Bold colors: mix `--color-text-*` categories for variety (info blue, success green, warning amber).\n- Art is the one place custom `<style>` color blocks are fine \u2014 freestyle colors, `prefers-color-scheme` for dark mode variants if you want them.\n- Layer overlapping opaque shapes for depth.\n- Organic forms with `<path>` curves, `<ellipse>`, `<circle>`.\n- Texture via repetition (parallel lines, dots, hatching) not raster effects.\n- Geometric patterns with `<g transform="rotate()">` for radial symmetry.'}},yO=[`diagram`,`mockup`,`interactive`,`art`,`chart`];function parseModules(e){if(Array.isArray(e))return e.map(e=>typeof e==`string`?e:String(e)).map(e=>e.trim()).filter(Boolean);if(typeof e!=`string`)return[];let t=e.trim();if(!t)return[];if(t.startsWith(`[`))try{let e=JSON.parse(t);if(Array.isArray(e))return e.map(e=>typeof e==`string`?e:String(e)).map(e=>e.trim()).filter(Boolean)}catch{}return t.split(/[\s,]+/).map(e=>e.trim()).filter(Boolean)}function createVisualizerReadMeTool(){return{name:`widget_guidelines`,promptCacheStability:`stable`,description:`Returns required context for show_widget (CSS variables, colors, typography, layout rules, examples). Call before your first show_widget call. Call again later if you need a different module. Do NOT mention or narrate this call to the user \u2014 it is an internal setup step.`,inputSchema:{type:`object`,properties:{modules:{anyOf:[{type:`array`,items:{type:`string`}},{type:`string`}],description:`Which module(s) to load. Pick all that fit. Options: ${yO.join(`, `)}. Pass as an array (e.g. ["diagram","chart"]), a JSON-encoded string array, or a comma-separated list like "diagram,chart".`}},required:[`modules`]},handler:async e=>{try{let t=parseModules(e.modules),n={type:`visualizer_read_me_result`,content:VisualizerGuidelines.build(t)};return{content:[{type:`text`,text:JSON.stringify(n)}]}}catch(e){let t=e instanceof Error?e.message:String(e);return{content:[{type:`text`,text:JSON.stringify({type:`visualizer_read_me_result`,content:``,success:!1,message:`Failed to load visualizer guidance: ${t}`})}],isError:!0}}}}}function parseLoadingMessages(e){if(Array.isArray(e))return e.map(String).map(e=>e.trim()).filter(Boolean);if(typeof e!=`string`)return[];let t=e.trim();if(!t)return[];if(t.startsWith(`[`))try{let e=JSON.parse(t);if(Array.isArray(e))return e.map(String).map(e=>e.trim()).filter(Boolean)}catch{}return t.split(`,`).map(e=>e.trim()).filter(Boolean)}function sanitizeTitle(e){return e.replace(/[\s-]+/g,`_`).replace(/[^\p{L}\p{N}_]/gu,``).replace(/^_+|_+$/g,``).replace(/_{2,}/g,`_`)||`widget`}function validateInputs(e,t,n){if(!e||!e.trim())return`title is required.`;if(!t||!t.trim())return`widget_code is required.`;if(n.length===0)return`loading_messages must contain at least one message.`;if(n.length>4)return`loading_messages can contain at most four messages.`;let r=t.trim();if(/<(!DOCTYPE|html|head|body)\b/i.test(r))return`widget_code must be a raw SVG or HTML fragment without document wrapper tags.`;if(/\b(localStorage|sessionStorage)\b/.test(r))return`widget_code cannot use localStorage or sessionStorage in the widget sandbox.`;if(/position\s*:\s*fixed/i.test(r))return`widget_code cannot use position: fixed because the widget height is auto-sized from in-flow content.`;if(/<form[\s>]/i.test(r))return`widget_code cannot use <form> tags. Use normal controls and event handlers instead.`;if(r.startsWith(`<svg`)){if((r.match(/<svg[\s>]/gi)||[]).length!==1)return`widget_code must contain exactly one <svg> element.`;if(!/viewBox\s*=\s*["']0\s+0\s+680\s+\d+["']/i.test(r))return`SVG widget_code must use a 680px-wide viewBox.`}return null}function buildErrorPayload(e){return{type:`visualizer_show_widget_result`,success:!1,title:``,loading_messages:[],render_mode:`html`,message:e}}function createVisualizerShowWidgetTool(){return{name:`show_widget`,promptCacheStability:`stable`,description:`Show visual content \u2014 SVG graphics, diagrams, charts, or interactive HTML widgets \u2014 that renders inline alongside your text response. Call widget_guidelines (modules: diagram|mockup|interactive|chart|art) before your first show_widget call to load required design guidance. widget_code MUST be a raw SVG/HTML fragment (no <html>/<head>/<body>/<!DOCTYPE>); for SVG use a viewBox starting with "0 0 680 ".`,inputSchema:{type:`object`,properties:{title:{type:`string`,description:`Short identifier for this visual, written in the same language the user is using (follow <response_language>). Must be specific and disambiguating \u2014 if the conversation has multiple visuals, this title alone should tell you which one is being referenced. Spaces and hyphens are converted to underscores automatically. Also used as the download filename.`},widget_code:{type:`string`,description:`SVG or HTML code to render. For SVG: raw code starting with <svg> tag. For HTML: raw HTML fragment, do NOT include DOCTYPE, <html>, <head>, or <body> tags.`},loading_messages:{type:`string`,description:`A JSON-encoded string array of 1\u20134 loading messages shown while the visual renders, each roughly 5 words long. Write in the same language the user is using. Example: '["Preparing chart data","Rendering visualization","Applying styles","Almost ready"]'`}},required:[`title`,`widget_code`,`loading_messages`]},handler:async e=>{try{let t=typeof e.title==`string`?e.title:void 0,n=typeof e.widget_code==`string`?e.widget_code:void 0,r=parseLoadingMessages(e.loading_messages),i=validateInputs(t,n,r);if(i)return{content:[{type:`text`,text:JSON.stringify(buildErrorPayload(i))}],isError:!0};let a={type:`visualizer_show_widget_result`,success:!0,title:sanitizeTitle(t),widget_code:n,loading_messages:r,render_mode:n.trim().startsWith(`<svg`)?`svg`:`html`,message:`Widget payload prepared for inline rendering.`};return{content:[{type:`text`,text:JSON.stringify(a)}]}}catch(e){let t=e instanceof Error?e.message:String(e);return{content:[{type:`text`,text:JSON.stringify(buildErrorPayload(t))}],isError:!0}}}}}p.t();function createConversationSearchBuiltinTool(e){return createConversationSearchTool(e)}function syncConversationSearchBuiltinTool(e,t){return t?(e.workbuddyConnector.registerBuiltinTool({...createConversationSearchBuiltinTool({authService:e.authService,productManager:e.productManager,isCloudMemoryEnabled:e.isCloudMemoryEnabled,isMemoryPlatformSession:e.isMemoryPlatformSession}),defer_loading:cd.has(GE)}),`registered`):e.workbuddyConnector.unregisterBuiltinTool(`conversation_search`)?`unregistered`:`already_unregistered`}function shouldRegisterConversationSearchTool(e){return e.isCloudMemoryEnabled?.()!==!1}function syncPickLocationBuiltinTool(e,t){return t?(e.workbuddyConnector.registerBuiltinTool({...createPickLocationTool({poiQuestionRegistry:e.poiQuestionRegistry,setSessionPoi:e.setSessionPoi??(()=>{}),isPoiMapEnabled:e.isPoiMapEnabled,pushPoiPickQuestion:e.pushPoiPickQuestion,logger:e.logger}),defer_loading:!0}),`registered`):e.workbuddyConnector.unregisterBuiltinTool(`pick_location`)?`unregistered`:`already_unregistered`}function syncKnowledgeSearchBuiltinTool(e,t,n){return t?(e.workbuddyConnector.registerBuiltinTool({...createKnowledgeSearchTool(e.knowledgeSearch,n),defer_loading:cd.has(iD)}),`registered`):e.workbuddyConnector.unregisterBuiltinTool(`knowledge_search`)?`unregistered`:`already_unregistered`}function syncAgentMailAttachmentBuiltinTools(e,t){let n={productManager:e.productManager,authenticationManager:e.authenticationManager,fetch:e.connectorOauthFetch,resolveBundledAsset:e.resolveBundledAsset},r=createUploadAttachmentTool(n),i=createDownloadAttachmentTool(n);if(!t){let t=e.workbuddyConnector.unregisterBuiltinTool(r.name),n=e.workbuddyConnector.unregisterBuiltinTool(i.name);return t||n?`unregistered`:`already_unregistered`}return e.