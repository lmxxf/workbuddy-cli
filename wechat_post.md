给 DeepSeek 搓了个顺手的命令行 Agent：开源版 workbuddy-cli

平时偶尔想在终端里调 DeepSeek-V4.1-Flash 干点活，一直没找到顺手的壳子——既不想用讨厌的 Claude Code，DeepSeek 官方那个 DSH 又没有 CLI 且不好用。

前两天正好把腾讯的桌面端 WorkBuddyAI 拆开研究了一遍，发现它底层的提示词和工具链本来就是专门针对 DeepSeek 打磨的（比如免 Schema 兼容思考模式、0.8*Cosine + 0.2*BM25 本地技能路由、Python sitecustomize.py 劫持删除进回收站、HTML AST 零 LLM 门禁、Excel 公式缓存回填防微信预览空白），唯独缺点也很明显：只有臃肿的 Electron 桌面壳、开局硬塞 3.3 万 Token 僵尸提示词、/compact 二压模板甚至写死了“所有任务均已完成”的假完工乌龙。

干脆去粗取精，把它的提示词逻辑和工程补丁全数移植出来，顺手修掉了它的压缩 Bug，做成了一个纯开源的命令行工具 workbuddy-cli（命令简称 wb），现在成了我自己日常用 DeepSeek 的主力 CLI 环境：

1. 开局底仓从 33K 砍到 2.4K（直降 92%）：默认走 lean 按需加载，自动向上发现并挂载项目目录的 AGENTS.md；
2. 原生适配 DeepSeek-V4.1-Flash：支持 /think <off|low|medium|high|max> 五档思维链控长切换、实时 / 下拉提示与多级 Tab 补全、本地 Session 自动落盘、/resume 历史回放与 /rewind 轮次回退；
3. 保留全套趣味内幕：内置毒舌死党等 7 种说话风格（/style sarcastic），连原版那个由包工头“齐活林”带着“许清楚、高见远、寇豆码、严过关”传话的 10 大官方专家团（/team）也原汁原味保留了下来，还提供了 spawn（星型二传手）与 role-switch（单上下文原地换帽子）双模式对比开关。

开源地址：https://github.com/lmxxf/workbuddy-cli
