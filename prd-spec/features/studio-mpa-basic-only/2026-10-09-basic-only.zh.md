# MPA 详情仅保留基本信息

- 日期：2026-10-09；状态：已实现并通过本地验证，未部署。
- 批准依据：用户明确要求隐藏 MPA 详情页其他 Tab，并停止该页面的 Profile 请求。
- [English](2026-10-09-basic-only.md)；契约：[Studio MPA 控制面](../../../specs/studio-mpa-control-plane/README.zh.md)。

## 范围与证据
`AgentWorkspace.tsx` 在选择 MPA 时调用 `getMpaAgentView`，间接请求 Runtime `/profile-status`。仅隐藏导航不能阻止请求。基本信息页底部也有 Profile 配置入口。

## 需求与设计
- FR-1：MPA 详情只显示基本信息，沿用既有布局和样式。普通 Agent 保留原有页面。
- FR-2：MPA 的任意目标页面（包括恢复或外部焦点）在副作用运行前同步解析为 `basic`。
- FR-3：基本信息不读取 MPA Agent View、Profile 状态或发起 Profile 修改。控制面加载限定在所属的 Profile/会话页面，并隐藏底部 Profile 入口。
- FR-4：保留 Runtime 信息、执行流程、聊天/删除操作及其授权。后端 API、原生聊天会话创建和 Profile 存储不在本次范围。

## 审查与验证计划
直接审查：只改变展示和请求调度，不迁移数据或改变鉴权。隐藏的既有实现保留，后续需明确重新启用。本地没有 `ui-ux-pro-max`，采用现有组件规范及直接审查。核对双语一致性和既有样式。

回归：渲染真实工作台并模拟网络边界，覆盖全部隐藏页面焦点、MPA 切换、普通 Agent 导航、基本信息展示以及 Profile/控制面零请求。执行前端测试、构建、资源检查和 pre-commit，检查新增可执行行覆盖率超过 95%，在可用时验证浏览器夹具。本地检查不代表已部署云端。

## 交付
在 `frontend/src/ui/AgentWorkspace.tsx` 实现 FR-1 至 FR-4，更新既有源码契约测试，新增 `frontend/tests/mpaBasicDetails.test.tsx`，重新构建 `veadk/webui`。未改变后端或 API 契约。

针对 `42b50624` 之上的差异验证（2026-10-09）：
- **pass**：`npm --prefix frontend test`：1,377 个 Node 测试和 64 个 Vitest 测试通过，包含 10 个新增组件用例。
- **pass**：`vitest run --root frontend tests/mpaBasicDetails.test.tsx --coverage --coverage.include=src/ui/AgentWorkspace.tsx --coverage.reporter=json`：变更的可执行语句起始行覆盖 7/7（100%）。这是增量行覆盖率，不是整个组件覆盖率。
- **pass**：`npm --prefix frontend run build`；`npm --prefix frontend run test:webui-assets`：验证 113 个打包文件及 350 个引用。
- **pass**：真实 Chrome 加载临时本地夹具，使用真实组件与模拟 fetch：MPA 仅基本信息、普通 Agent 导航及集成页面交互、普通 Agent 切回 MPA、Profile 零请求、窄窗口布局。提交前移除临时夹具。
- **pass**：`uv run --extra dev pre-commit run --all-files`；`git diff --check`；已获取最新 `origin/main`，当前分支已包含该基线。
- **not_applicable**：新增输入/IME、写入取消/重试流程及后端测试；本次未修改这些路径。隐藏页面焦点由组件测试覆盖。
- **not_run**：云端部署及真实云端 E2E；浏览器夹具与本地检查不代表发布。原生聊天会话创建保留原有 Profile 行为。

最终直接审查：类别限制保留普通 Agent 的导航与更新行为，同步解析页面避免旧焦点启动隐藏页面请求，既有副作用保留清理逻辑。已核对中英文需求与组件文档一致性。
