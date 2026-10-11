# MPA A2A 推理快照与空回复提示

[English](2026-09-22-mpa-a2a-reasoning.md)

## 元信息与证据
- ID：`mpa-a2a-reasoning`；日期：2026-09-22；状态：implemented。
- 契约：[Studio runtime diagnostics](../../../specs/studio-runtime-diagnostics/README.zh.md)，CON-10。

用户反馈最终答案一份，但外层推理重复，sandbox 工具之前出现空回复提示。只读任务检查确认成功完成且 sandbox final 非空。App.tsx 对每个已结束、只有推理的 turn 独立显示空提示。A2A 桥接用 `projectionSource=a2a-artifact` 标识外层完整推理，预览边界已提交后重复快照会再次追加整段推理。未捕获完整实时 SSE 顺序；测试使用观察到的事件契约，不保存生产原文。

## 目标、范围与需求
- FR-1：仅注册为 `a2a-default`、且含 MPA 类型/实例信息的 Runtime 应用启用。通用 ADK、通用 A2A、本地智能体、原生 MPA 沿用既有行为。
- FR-2：启用后的 projector 对非 partial、仅含推理的 `a2a-artifact` 快照，若匹配或扩展紧邻的前一个推理块，则替换该块。保留不同推理、token 增量、sandbox 推理、工具、附件和错误。不对任意模型文本去重。
- FR-3：仅 MPA A2A 按两条用户消息之间的所有助手片段判断空回复。本轮运行/展示期间，或任何片段含可见内容时不提示。真正空的已结束请求仍在最后一个非空片段保留一次提示。历史请求独立判断，通用智能体沿用原逐 turn 规则。
- FR-4：实时、历史回放、鉴权续接使用同一个显式 projector 选项，状态限定在本次请求。不改鉴权、接口路由、云部署或后端。

## 设计、任务与验收
T-1 / AC-1：先增加失败测试，覆盖重复/扩展快照、实时/历史、两次请求、工具、默认/通用行为。T-2 / AC-2：增加空提示测试，覆盖运行、成功、空、取消、多条用户消息、通用行为。T-3 / AC-3：连接 `frontend/src/adk/client.ts`、`blocks.ts`、`App.tsx` 和小型纯转录辅助模块，运行定向/完整前端测试、构建、产物和浏览器检查，更新 README 与双语契约。既有取消/错误保持不变，不伪装成空的成功输出。

## 评审、授权与风险
用户明确批准修复这些表现并保留通用智能体行为。review-spec 不可用，已直接评审：显式协议/类型门控、默认投影不变、无跨请求状态、不改凭据、双语等价，无阻塞项。风险：未捕获完整实时顺序；限定快照合并不得移除不同推理或 partial 增量。既有任务历史恢复可能只有最终文本，不重构缺失历史。不改变视觉设计。

## 验证
2026-09-22 在基于 `3bbd260a` 的工作区差异上验证，包含既有未提交修改。T-1 至 T-3 已完成。直接实现评审确认五个投影入口显式门控、用户请求边界独立、默认行为保留；双语需求与契约一致。

- `pass`：测试先行基线复现重复快照（实现前六项失败，其中五项由于空提示辅助函数尚不存在）；定向回归现已随完整套件通过。
- `pass`：`npm --prefix frontend test` — 1,287 项 Node 测试和 25 项 Vitest 测试。
- `pass`：`npm --prefix frontend run build` — TypeScript 与 app/widget 构建。首次发现的参数位置错误和不兼容 ES2020 的数组访问已修正后重跑通过；保留既有 chunk 大小警告。
- `pass`：`npm --prefix frontend run test:webui-assets` — 104 个打包文件、248 条引用。
- `pass`：隔离浏览器页面使用真实 projector、提示辅助函数和 Blocks 渲染器 — MPA 推理快照/最终答案各一份，中间片段和运行中无空提示，真正空回复保留一条，通用智能体对照行为不变；无控制台错误。临时页面与服务已清理。
- `pass`：浏览器访问 `http://127.0.0.1:8000/index.html` 加载新构建 `index-BoFYrKMR.js`；未重启后端。运行进程缓存 `/` 的 HTML，使用 `/index.html` 加载新资源。
- `pass`：限定文件的 `uv run --with pre-commit pre-commit run gitleaks --files ...` 与 `git diff --check`。
- `not_run`：新增真实云模型请求/完整捕获 SSE 回放；浏览器场景使用契约推导的模拟事件，用户下一条真实消息另行复核。
- `not_applicable`：Python 门禁、键盘/输入法和响应式布局变更；本次增量不改后端、控件或布局。取消/请求边界由回归测试覆盖。未请求或执行提交/推送。
