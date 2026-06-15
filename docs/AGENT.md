# AGENT.md — VeADK 文档写作与维护指南

本文件是编辑 `docs/` 时的约定汇总（面向 AI agent 与人类作者）。改动文档前先读本文件，并严格遵循。

## 0. 工程速览

- **框架**：Fumadocs（Next.js + fumadocs-mdx）。内容在 `docs/content/docs/**`。
- **双语**：中文为默认语言，文件 `x.mdx`（URL `/cn/...`）；英文 `x.en.mdx`（URL `/en/...`）。**每个页面都要中英两份，且结构一致。**
- **导航**：每个目录的 `meta.json`（中）/ `meta.en.json`（英）控制标题与顺序。
- **本地预览**（需 Node 22）：
  ```bash
  export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
  export NODE_OPTIONS="--max-old-space-size=8192"   # 长时间会话避免 OOM
  cd docs && corepack pnpm dev                        # http://localhost:3000
  ```
- 改了目录结构 / `source.config.ts` / `lib/source.ts` 后，先 `corepack pnpm exec fumadocs-mdx` 重新生成索引，必要时重启 dev server。

## 1. 写作风格（硬性要求）

1. **简洁、清晰、声明式，少用主语**（少用「你 / 我们」）。参考 https://adk.wiki/agents/llm-agents/ 与 Google 技术写作课程（主动语态、一句一义、强主题句、去冗余、列表平行、术语先解释）。
2. **禁止口语化铺垫**：不要「换句话说」「也就是说」「你常常希望」「跑起来」等。
3. **尽量不在正文（尤其概述）引入类名、变量名、文件路径**。重点讲**设计与用法**，不是实现细节。面向用户的配置文件名（`.env`、`config.yaml`）可提；内部类名（如 `DynamicConfigManager`）用功能性描述代替。
4. **页面不写 frontmatter `description`**（标题下不再有副标题句）。frontmatter 通常只有 `title`（必要时加 `status`）。
5. **介绍参数用表格，不要用 bullet 列表**。表格列：`参数 | 类型 | 默认值 | 说明`（或按场景精简）。
6. **内容必须基于源码**。写某模块前先读 `veadk/` 对应实现，确保参数名、默认值、行为准确；不要照搬旧文档或臆测。

## 2. 每个页面的标准结构

正文按以下三段式组织（这是当前最重要的约定）：

1. **概述**：一段话说清「这个模块/能力提供了什么」，避免具体技术细节（类名、变量名）。
2. **基本使用**：一段**可直接运行**的最小代码示例（`python title="agent.py"` 等）。
3. **更多参数 / 支持的能力**：参数表 + 进阶用法。**若涉及多种能力，每种用一个 `##` 标题分别说明**，并各配一段示例。

参考样板：`content/docs/framework/agent/runtime.mdx`。

## 3. 结构与导航约定

- **带基类的模块** → 「基类契约 + 每个内置扩展单独子页」。例：`memory/short-term/`（index 讲统一接口与后端契约）+ `local`/`sqlite`/`mysql`/`postgresql` 子页；长期记忆同理。
- **倾向拍平**：能力相关的页面直接挂在分组分隔符下，避免「分隔符 + 同名折叠文件夹」的冗余双层。
- **章节拆分**：单页过长且含多个独立主题时，拆成文件夹 + 子页（如 `agent/`：基本组件/模型管理/Responses API/运行时/进阶能力/技能）。文件夹用 `index.mdx` 作为落地页以保留 `/.../<folder>` URL。
- **移动 / 重命名页面时**：① 全仓改写指向它的内部链接；② 更新相关 `meta.json` 与 `meta.en.json`；③ 确认旧 URL 404、新 URL 200；④ 中英同步。
- **不要写「下一步 / Next steps」结尾卡片**，也不要冗余的「简介 / Methods」段落。
- 全站已**关闭页脚上一页/下一页导航**（`app/[lang]/docs/[[...slug]]/page.tsx` 的 `footer={{ enabled: false }}`）；标题与「复制 Markdown / 打开方式」按钮在同一行右侧。

## 4. 善用 Fumadocs 组件（避免死板）

这些组件已全局注册（`components/mdx.tsx`），直接用，无需 import：

- **目录结构**一律用 `<Files>` / `<Folder name=… defaultOpen>` / `<File name=… />`，**不要用 `├ └ │` 画的 ASCII 树**。（`<File>` 不支持行内注释，注释信息改用正文或表格表达。）
- **流程 / 架构图**用 ` ```mermaid `（`flowchart` 等），**不要用文字画图**。
- `<Callout type="info|warn|error|success|idea">`、`<Tabs>`、`<Steps>`、`<Accordions>`、`<Cards>`、`<TypeTable>` 按需使用。
- 代码块支持 `title="…"`、行高亮 `// [!code highlight]`、行号 `lineNumbers`、tab 组 ` ```ts tab="…" `。

## 5. 侧边栏 NEW 等标签

- frontmatter 加 `status: new`（或 `beta`/`deprecated`/`experimental`）即可在侧边栏显示标签。
- 机制：`source.config.ts` 用 `pageSchema.extend({ status: z.string().optional() })` 放行该字段；`lib/source.ts` 通过 `statusBadgesPlugin` 渲染样式化小标签。
- 中英两份都要加，保持一致。

## 6. 当前导航结构（框架 root）

- **入门**：installation, quickstart, troubleshooting, changelog
- **核心能力**：agent（文件夹：index/model/responses-api/runtime/advanced/skills）, multi-agent, prompt, runner, tools（含 guardrail）, memory, knowledgebase, tunnel
- **交互**：frontend（VeADK Web + VeADK Frontend）, a2ui
- **安全**：security, inbound, api-key, oauth2-m2m, oauth2-user-federation, trusted-mcp, permission-policy
- **可观测**：observability, tracing, ve-tracing, span-attributes
- **部署**：vefaas, agentkit
- **评测与优化**：evaluation, optimization
- **进阶与更多**：enterprise-design, community

另有 **参考（references root）**：index, api, api-server, configuration（环境变量/内置默认/运行时动态配置）, contributing, license；以及 **命令行（cli root）**。

## 7. 安全红线

- **绝不提交密钥或 `.env`**。示例里密钥一律用占位符或环境变量；生产配置强调用环境变量 / `config.yaml`，勿硬编码。
- 代码示例中的 IP/域名用文档示例段（如 RFC 5737 的 `192.0.2.x`），避免误用真实地址。
