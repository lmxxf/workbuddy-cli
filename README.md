# WorkBuddy-CLI (`wb`) — 腾讯 WorkBuddyAI 核心管线纯开源跨平台 CLI（DeepSeek 一等公民）

> **“扒掉 181MB 的 Electron 臃肿外壳与 32,739 Token 的开局僵尸底仓，把 WorkBuddyAI 最值钱的十大工程补丁、2.6 万字交互画图规范、GB/T 9704 红头公文排版门禁、Excel 公式重算与『齐活林/许清楚/寇豆码』专家团双模式，浓缩进一个零配置、纯开源的跨平台命令行工具。”**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](pyproject.toml)
[![DeepSeek First-Class](https://img.shields.io/badge/DeepSeek-First--Class%20Citizen-blueviolet.svg)](https://api.deepseek.com)
[![Tests: 12/12 Passed](https://img.shields.io/badge/Tests-12%2F12%20Passed-brightgreen.svg)](tests/test_all.py)

---

## 一、 为什么要做 `workbuddy-cli`？

在对腾讯 **WorkBuddyAI (`5.9.4-wb.42593613`)** 的 `app.asar` 与 `codebuddy-lite-wb.mjs` 进行完整逆向解剖后，我们发现了一个极其有趣的工程真相：

1. **为什么普通白领觉得它“画交互图惊艳、排红头公文像样、发微信预览 Excel 不空白、还不会乱删桌面”？**
   不是因为底层模型有什么神秘魔法，而是因为工程师在 `.tpl` 模板与内置 Skill 里塞了**十套极其务实（甚至有点鸡贼）的确定性工程门禁与预制脚本**：
   - `sitecustomize.py` 运行时猴子补丁劫持 `os.remove / shutil.rmtree` 强行改发系统回收站；
   - 859 行零 LLM 往返的 `review_html.py` AST 门禁（裸色值、跳级标题、缺 `<thead>` 直接打回）+ 修复封面 **`"模  拟  人  生  4"`** 两端对齐继承惨案的 CSS 硬补丁；
   - 955 行 `sheet_recalc.py` 强行把公式计算结果回填进 `.xlsx` 压缩包的 `<v>` 缓存节点（解决 `openpyxl` 公式在手机微信预览一片空白的痛点）+ `GB 45438-2025` AIGC 隐式水印；
   - 2.6 万字流式防闪烁 `VisualizerGuidelines`（锁死 `viewBox="0 0 680 H"`、禁渐变/阴影/注释、算框宽公式 `rect_width = max(title*7, sub*6) + 24`）+ **腾讯程序员亲手写的“模型智商鄙视链”**（把自家混元 `Hunyuan` 放最底端 `Minimal`，把 Claude/GPT/DeepSeek 放 `No ceiling`😂）。
2. **为什么程序员用它写中大型工程代码时却觉得“记不住上下文、像玩具”？**
   - **开局“你好”底仓高达 `32,739` Tokens**：一句话还没干活，3.3 万 Token 的全量提示词、工具 Schema 和四个灵魂模板已经垫进去了；
   - **`/compact` 二压模板里的“假完工催眠乌龙”**：在原版 `context-summary-prompt.txt` 第 8–9 行，竟然硬编码了 `All tasks described below are already completed. **DO NOT re-run, re-do or re-execute any of the tasks mentioned!**`——哪怕活儿干到一半触发压缩，也会把接班窗口的 AI 当场催眠；
   - **对外撑场面的“包工头多角色专家团”双倍 Token 爆炸**：拿同一个底座模型套上 **“交付总监齐活林、产品经理许清楚、架构师高见远、项目经理毕达成、程序员寇豆码、测试严过关”** 六顶谐音梗帽子，禁止团员直连，全靠包工头“齐活林”用 `<teammate-message>` 在中间复制粘贴当二传手（而腾讯程序员自己写核心 `tdoc-orchestrator.md` 第 150 行时却诚实地写着：`“⚠️ subagent 模式上下文隔离，效果不稳定，非必要不使用，推荐在单上下文喊 [角色切换]”`😂）。

**`workbuddy-cli` (`wb`) 的设计目标**：
- **DeepSeek-V4.1-Flash 一等公民（First-Class Citizen）**：默认直连 DeepSeek V4.1-Flash（`deepseek-flash` / `deepseek-v4.1-flash`，1M 上下文原生多模态；无缝支持切换 `deepseek-v4-pro` / `deepseek-reasoner` / `deepseek-chat`），支持完整 10 大 Agentic Tools 自动循环与 `/think <off|low|medium|high|max>` 思维链控长；
- **去芜存菁（Lean Profile 节省 94%+ 开局 Token）**：默认启用按需挂载的 `lean` 模式（开局核心提示词仅 `~1,800` Tokens，通过本地 `0.8 * Cosine + 0.2 * BM25` `RecallIndex` 动态按需注入 Skill），同时保留 `--prompt-profile full` 1:1 复刻原版 `.tpl`；
- **原生支持 `AGENTS.md` / `CLAUDE.md` 自动发现**：像 Codex / Antigravity CLI 一样自动识别项目根下的 `AGENTS.md`；
- **修复原版三大工程 Bug**：
  1. **Fixed `/compact` premature task-completion hypnosis bug**（修复二压模板假完工催眠乌龙，保留 `Pending & In-Progress Tasks`）；
  2. **Upgraded `skill-creator/quick_validate.py`**（补齐原版 65 行脚本缺失的 Markdown 资源引用真实性审计与 `agent_created: true` 校验）；
  3. **Exposed Dual-Mode Expert Team (`--team-mode spawn` vs `--team-mode role-switch`)**（把“包工头齐活林 `<teammate-message>` 二传手模式”与“腾讯内部偷偷用的单上下文 `[角色切换]` 模式”做成公开开关，并内置实时 **二传手复读损耗账本 `Relay Copy-Paste Tax Meter`**！）。

---

## 二、 十大核心特性还原与改进对照表

| 序号 | 核心模块 | 原版 WorkBuddyAI (`5.9.4`) 逆向内幕 | `workbuddy-cli` (`wb`) 实现与增强 |
| :---: | :--- | :--- | :--- |
| **1** | **灵魂孵化器与三层记忆** | 照抄 OpenClaw 的 `SOUL.md` + `IDENTITY.md` + `USER.md` + `BOOTSTRAP.md`（认主后自删）+ 3 层 `MEMORY.md` 与按日日志 | `workbuddy_cli/memory.py` 完整复刻 `/soul onboard` 认主自删 `BOOTSTRAP.md`、4000/3000 字双层记忆与 `YYYY-MM-DD.md` 自动追加日志，外加 48-bit 零宽隐形水印编解码 |
| **2** | **2.6 万字 Visualizer 画图引擎** | 锁死 `viewBox="0 0 680 H"`、禁渐变/阴影/注释防流式闪烁、算框宽公式 + 模型智商分级门禁 | `workbuddy_cli/tools/visualizer.py` 内置 9 色板 63 色阶、算框宽公式、流式防闪烁审计器 `audit_widget_code` 与 `--widget-svg` / `show_widget` 工具 |
| **3** | **三阶段 Word & GB/T 9704 红头公文** | 严禁直调 `python-docx`，走 `md -> HTML -> docx`，含 `review_html.py` 零 LLM AST 门禁与封面 `"模 拟 人 生 4"` 居中继承补丁 | `workbuddy_cli/tools/office_suite.py` 集成原版 859 行 `review_html.py`、`fix_sims4_cover_centering_bug` 与纯标准库 `GB/T 9704-2012` 红头 `.docx` 编译器（`--generate-gov-docx`） |
| **4** | **Excel 公式三层重算与国标打标** | `openpyxl` 公式无 `<v>` 缓存导致微信预览空白；`sheet_recalc.py` 强行回填 `<v>` + `xlsx_aigc_label.py` 写 `GB 45438-2025` 标签 | `workbuddy_cli/tools/office_suite.py` 内置零依赖 OOXML 公式求值回填引擎 + 原版 `xlsx_aigc_label.py` 隐式打标（`--recalc-xlsx`） |
| **5** | **五阶段 Deep Research (2/3 杠精陪审团)** | 迁就 `deepseek-chat` 砍掉 JSON Schema 参数改手写正则，对每条断言派 3 个怀疑论 Agent 投票，`>=2/3` 驳回即枪毙 | `workbuddy_cli/tools/deep_research.py` 完整复刻五阶段流水线、三层畸形 URL 域名提取、防全弃权假存活机制与 `Refuted Claims` 透明公示（`--research`） |
| **6** | **对抗式盲审引擎 (`Critic-Generator`)** | 六步状态机：物理剥离作者思维链（`Isolate`）+ 延迟加载尺规 + 强制扣分配额（`min_issues=2, min_instructions=3`，严禁全部通过） | `workbuddy_cli/tools/critic_engine.py` 实现盲审包构造、强制扣分配额兜底与 `PASS / REVISE / DEGRADED` 报告生成（`--critic`） |
| **7** | **混合技能检索 (`RecallIndex`)** | 本地 `0.8 * Cosine + 0.2 * BM25 (k1=1.5, b=0.75)` 动态路由 Skill，离线自动降级纯 BM25 | `workbuddy_cli/skill_router.py` 完整移植 `Bm25Index` 与 `RecallIndex`，内置 10 大逆向核心 Skill 并支持 `--match-skill` 与 `skill-creator` |
| **8** | **物理级防删库沙箱 (`Safe-Delete`)** | `sitecustomize.py` 猴子补丁劫持 `os.remove / shutil.rmtree` 强行改发回收站 + 个人目录防删 8 铁律 + 3 段式文档备份事务 | `workbuddy_cli/tools/safe_shell.py` 实现 `PYTHONPATH` 自动注入回收站劫持垫片、禁区拦截与 `DocumentBackupTransaction` 快照回滚 |
| **9** | **7 种说话风格 & 闪光增强 Prompt** | 含 `sarcastic`（毒舌死党：先嘲讽烂点子再给正确答案）等 7 种风格 + 右下角小闪光图标 `llm:enhancePrompt` | 支持 `--style sarcastic` 一键切换毒舌模式，以及 `--enhance` / `/enhance` 800 字以内同语种提示词增强 |
| **10** | **谐音梗“专家团”双模式公开处刑** | 对外吹嘘 **齐活林/许清楚/高见远/毕达成/寇豆码/严过关** 子会话传话，对内自己写核心功能却用 `[角色切换]` 单上下文独角戏 | `workbuddy_cli/tools/expert_team.py` 同时支持 `--team-mode spawn`（带 `<teammate-message>` 二传手损耗账本）与 `--team-mode role-switch`！ |

---

## 三、 快速安装与零配置上手

### 1. 安装

```bash
git clone https://github.com/lmxxf/workbuddy-cli.git
cd workbuddy-cli
pip install -e .
# 若系统 setuptools 版本较老，也可使用：
# python3 setup.py develop --user
```

安装后即可在终端直接使用 `workbuddy` 或短命令 **`wb`**。

### 2. 配置 DeepSeek / OpenAI 兼容 API

默认将 **DeepSeek** 作为一等公民。支持通过环境变量 `WORKBUDDY_API_KEY` / `DEEPSEEK_API_KEY` 或配置文件 `~/.workbuddy-cli/config.json` 配置：

```json
{
  "api_key": "sk-your-deepseek-api-key",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-v4.1-flash",
  "mode": "craft",
  "style": "efficient",
  "thinking_effort": "off",
  "prompt_profile": "lean",
  "language": "中文",
  "ide_theme": "dark"
}
```

---

## 四、 核心命令与真机实测演示

### 1. 日常作为 DeepSeek 主力 CLI Agent 使用（自带 10 大工具 + 自动加载 `AGENTS.md`）

```bash
# 单次指令执行（自动触发 RecallIndex 技能检索 + Tool Calling 循环）
wb "用毒舌吐槽风格点评一下把同一个模型拆成齐活林、许清楚、寇豆码五个子会话互相复制粘贴传话的架构设计，并调用 show_widget 画一张简洁的流程图保存在 /tmp/wb_roast.svg" --style sarcastic

# 切换思维链 (CoT) 开关与长短档位: off (默认关闭黑盒CoT) | low (50) | medium (65) | high (75) | max (100)
wb -t low "算一下 17 * 23 等于多少？"
wb -t high "简述 MLA 相比 MQA 的几何优势"

# 查看当前精细上下文账本 (Base System Prompt / AGENTS.md / 历史对话占比与 15% 压缩水位线)
wb --context

# 查看历史会话列表或一键恢复上一次会话继续聊 (-r / --resume)
wb --sessions
wb -r latest "继续刚才的话题"

# 启动交互式 REPL（内置 prompt_toolkit 实时 `/` 下拉菜单 + 多级 `Tab` 自动补全：
# 支持 /resume, /rewind, /undo, /sessions, /new, /rename, /think, /effort, /context, /status, /mode, /style, /model, /profile, /team, /compact, /research, /critic, /docx, /recalc, /soul, /enhance, /clear）
wb
```

### 2. 招牌功能：体验“齐活林”专家团的两种真相（`spawn` 二传手模式 vs `role-switch` 独角戏模式）

查看内置的 10 个官方专家团与让人脚趾抠地的谐音梗花名阵容：

```bash
wb --list-teams
```

**模式 A：对外撑场面的包工头星型传话模式（`--team-mode spawn`）**
主理人交付总监 **齐活林** 建队，依次唤醒独立空上下文团员 **许清楚(PM) $\rightarrow$ 高见远(Arch) $\rightarrow$ 寇豆码(Dev) $\rightarrow$ 严过关(QA)**，用 `<teammate-message>` XML 标签当二传手复制粘贴前序全文：

```bash
wb --team SoftwareCompany --team-mode spawn --task "实现一个支持A股红涨绿跌的终端行情小组件" --llm
```

> **真机实测账本输出**：
> - `有效产出 385 tokens | 包工头二传手复读损耗 (Relay Copy-Paste Tax): +985 tokens`（包工头复制粘贴传话白烧的 Token 是有效产出的 **2.5 倍**！）

**模式 B：腾讯核心研发内部偷偷用的单上下文模式（`--team-mode role-switch`）**
直接在单上下文内高喊 `"[角色切换] 现在以 许清楚(pm) 身份执行 Stage 1"` 原地换帽子干活：

```bash
wb --team SoftwareCompany --team-mode role-switch --task "实现一个支持A股红涨绿跌的终端行情小组件" --llm
```

> **真机实测账本输出**：
> - `有效产出 363 tokens | 包工头二传手复读损耗 (Relay Copy-Paste Tax): +0 tokens`（零上下文失真，零二传手税！）

### 3. 三阶段 `GB/T 9704-2012` 红头公文生成 + 零 LLM `review_html.py` AST 门禁

```bash
# 一键生成符合 GB/T 9704 国标的红头公文 .docx，并自动过 859 行 review_html.py 门禁检测（100 分通过！）
wb --generate-gov-docx ./outputs/gov_red_header.docx

# 单独对任意 HTML 运行零 LLM 门禁审查
wb --check-html ./outputs/gov_red_header.html --genre government-doc
```

### 4. Excel (`.xlsx`) 公式重算回填 `<v>` 缓存（防微信预览空白）+ `GB 45438-2025` AIGC 隐式水印

```bash
# 自动解析 .xlsx 内的 <f> 公式（SUM/AVERAGE/四则运算等），计算并写回 OOXML <v> 缓存节点，同时写入 docProps/custom.xml AIGC 隐式标识
wb --recalc-xlsx ./outputs/finance_demo.xlsx
```

### 5. 修复了“假完工催眠乌龙”的三级上下文压缩（`/compact`）

```bash
# 运行 HistoryEngineeringCompactor 工程剪刀（剪除工具大输出与 content/widget_code/new_string）+ 修复版 LLM 二压
wb --compact-demo
wb --compact-demo --llm
```

### 6. 对抗式盲审引擎（`Critic-Generator`）与五阶段 `Deep Research`（2/3 怀疑论陪审团）

```bash
# 运行六步盲审状态机（物理剥离作者思维链 + 强制扣分配额 min_issues=2, min_instructions=3）
wb --critic "这是一份待审查的技术架构方案草稿..." --llm

# 运行五阶段深度研究（Scope -> Search -> Fetch -> 3票杠精陪审团 Verify -> Synthesize）
wb --research "Hybrid BM25 and Cosine Tool RAG in LLM Agents" --llm

# 运行右下角小闪光图标提示词增强器 (llm:enhancePrompt)
wb --enhance "帮我写个能防删库的python脚本"
```

---

## 五、 项目结构

```text
workbuddy-cli/
├── pyproject.toml
├── setup.py
├── README.md
├── LICENSE
├── workbuddy_cli/
│   ├── __init__.py
│   ├── cli.py                 # 主交互式 REPL + 单次 CLI 入口 (workbuddy / wb)
│   ├── config.py              # DeepSeek/OpenAI 配置管理与 AGENTS.md 自动向上发现
│   ├── agent_client.py        # DeepSeek 一等公民客户端 + 10 大 Agentic Tools 执行循环
│   ├── prompt_engine.py       # .tpl 模板渲染器 (lean vs full)、7 种说话风格、模型复杂度门禁
│   ├── memory.py              # SOUL.md + BOOTSTRAP.md 孵化器、三层记忆、48-bit 零宽字符隐形水印
│   ├── compactor.py           # HistoryEngineeringCompactor + 修复“假完工催眠乌龙”的 LLM 二压器
│   ├── skill_router.py        # 0.8 * Cosine + 0.2 * BM25 本地动态 Skill 路由器 (RecallIndex)
│   ├── tools/
│   │   ├── safe_shell.py      # sitecustomize.py 回收站劫持沙箱 + 个人目录防删 8 铁律 + 3段式回滚
│   │   ├── visualizer.py      # 2.6 万字规范 SVG 生成器与流式防闪烁审计器 (viewBox="0 0 680 H")
│   │   ├── office_suite.py    # review_html.py 零 LLM 门禁 + GB/T 9704 红头 Docx + Excel 公式重算
│   │   ├── critic_engine.py   # Critic-Generator 六步盲审隔离与强制扣分配额引擎
│   │   ├── deep_research.py   # 五阶段 2/3 怀疑论陪审团深度研究工作流
│   │   └── expert_team.py     # 10 大官方专家团（齐活林/许清楚/寇豆码/严过关）spawn vs role-switch 双模式
│   └── assets/                # 完整内置逆向提取的原始 .tpl、7 种 style-*.md、skills/ 与沙箱脚本
└── tests/
    └── test_all.py            # 覆盖全部 10 大核心子系统的自动化测试套件
```

---

## 六、 运行自动化测试

```bash
pytest -v
# 或使用标准库 unittest：
python3 -m unittest discover -s tests -v
```

---

## 七、 致谢与关联研究

本项目源自我对 `WorkBuddyAI.exe` 的深度逆向工程解剖研究（详见姊妹仓库 [`workbuddy-study`](https://github.com/lmxxf/workbuddy-study)）。通过将闭源桌面壳内的优秀工程防御经验（回收站物理锁、零 LLM HTML AST 门禁、Excel OOXML `<v>` 缓存回填、盲审强制扣分配额）提取为纯开源 CLI，并修复其开局 Token 臃肿、`/compact` 催眠乌龙与多角色二传手损耗，希望能为国内 AI Agent 开发者提供一份扎实、透明的工程参考。

## License

[MIT License](LICENSE) © 2026 Jin Yanyan (`lmxxf`)
