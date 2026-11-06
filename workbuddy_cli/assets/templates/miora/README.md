# Miora 内置资源

本目录有两个文件，都由 daemon 在运行时按路径读取：

| 文件 | 用途 |
|---|---|
| `ai.kiwi` | Miora 画布数据的 kiwi schema 定义（从 miora 仓拷贝） |
| `empty-canvas.miora` | 新建空画布的模板 |

---

## `ai.kiwi` — kiwi Schema

`ai.kiwi` 是 Miora 画布数据的 **kiwi schema 定义**，从 miora 仓原样拷贝而来。

## 来源与同步

```
miora 仓：packages/frontend/web-flow/src/kiwi/ai.kiwi
```

同步方式：**整文件覆盖**。刻意不做裁剪（只留 `MioraLocalFile` 相关 message），
因为裁剪版在 schema 变更时容易漏字段，而整文件覆盖是无脑安全的操作。
55KB 的体积代价可接受。

## 用途

`packages/workbuddy-server/src/miora/schema-runtime.ts` 在运行时读取本文件并
`compileSchema(parseSchema(text))`，得到 `.miora` 的 encode/decode 能力。

**不走 kiwic 代码生成**：genie-v2 只需要 encode/decode 两个函数，运行时编译
（约 10-30ms，已做单例缓存）比引入代码生成步骤更简单。TS 类型另在
`src/miora/schema.entity.ts` 手工维护所需子集。

## 为什么放在 templates 下

需要一个「打包后仍能按路径读到」的位置。本目录复用了 prompt-template 的定位机制
（`src/server/prompt-template-paths.ts`），它已处理 dev / packaged / asar 三种布局，
且 `bundled-assets-manifest.js` 已登记 `templates` 目录与 `dist/resources/templates/**/*`。

⚠️ 不要改成用 `__dirname` 相对定位：electron-vite 会把 daemon 代码内联进
`dist/main`，`__dirname` 会失真。

## 同步时的注意事项

`MioraLocalFile`（`.miora` 文件的信封）字段顺序与编号**不可变更**，否则已有
`.miora` 文件无法解析：

```kiwi
message MioraLocalFile {
  uint formatVersion = 1;
  Workflow workflow = 2;
  string assetsBaseDir = 3;
  string generator = 4;
}
```

改动 schema 后请跑 `packages/workbuddy-server/src/miora/` 下的单测确认往返仍保真。

---

## `empty-canvas.miora` — 空画布模板

`workbuddy_miora_canvas` 工具在 `action="create"` 且没有 items 时，用这份模板产出
空画布（见 `src/miora/empty-canvas-template.ts`）。

### 可以直接用 Miora 打开编辑

这就是放模板文件而非代码里现搭结构的原因：页面级默认配置（页面名、后续新增的画布
设置）可以可视化调整，不必改 TS 代码。

### ⚠️ 必须保留一个默认 PAGE 节点

Miora 的投影链路以 `activePageId` 为根、沿 `parentIndex` 递归收集本页节点。
**页面节点缺失时不会报错**，只是收集到空集合 —— 表现为画布一片空白、控制台干净，
极难排查。因此：

- 编辑模板时不要删掉那个页面；
- `buildEmptyCanvasFromTemplate` 已加校验，缺页面时直接抛错而不是产出白板文件；
- `empty-canvas-template.spec.ts` 有对应的回归测试。

### 下列字段不随模板复制，由代码每次改写

| 字段 | 原因 |
|---|---|
| `workflow.id` | 画布唯一标识。共用会让 Miora 的画布状态索引撞车（打开 A 显示 B） |
| `createAt` / `updateAt` | 否则用户看到的永远是模板打包那天的时间 |
| `workflow.title` + 页面节点的 `data.title` / `data.pageName` | 标题在这三处都出现，图层面板读的是页面节点那份 |

### 为什么不是「拷贝文件 + 字节替换 title」

`.miora` 是 kiwi 二进制、**变长编码**：标题长度一变，字符串的长度前缀就得跟着变，
字节级替换会直接损坏文件。所以走 decode → 改字段 → encode。

### 如何重新生成

模板本身就是工具产物，`buildWorkflow({ title: 'New Canvas', items: [] })` 编码后
写盘即可（当前 166 字节）。改动后跑 `src/miora/empty-canvas-template.spec.ts` 验证。
