# 功能验证 Case：MPA Runtime 集成加固

- **Change ID：** `mpa-runtime-integration-hardening`
- **状态：** 生效
- **日期：** 2026-09-13
- **English version:** [2026-09-13-functional-validation-cases.md](2026-09-13-functional-validation-cases.md)

## Case 清单

| Case | 需求 | 前置条件与执行 | 预期结果 | 证据 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `VC-1` | `FR-1`、`FR-3`、`FR-9` | 运行 mpa-agent 依赖/配置测试；发布后观察 VeADK Runtime 至少 240 秒并执行一次 sandbox 回合。 | 无 `ListResources` 调用、无缺失 `user_pool_id`，预期配置缺失不打印 traceback。 | 测试输出、脱敏 Runtime 日志。 | 自动测试 `pass`；真实验证因镜像未发布而 `blocked`。 |
| `VC-2` | `FR-2` | 运行部署环境、Runtime、CLI 测试。 | 第二阶段同时包含 URL 与 Runtime key；输出不泄露 Key。 | Pytest 输出及 Secret scan。 | `pass` |
| `VC-3` | `FR-4` | 执行 A2A relay 测试及真实 sandbox 命令。 | 首个 artifact 使用 `append=false`，后续事件 append 且可见。 | Pytest 输出、真实 A2A 流。 | 自动测试 `pass`；真实验证 `blocked`。 |
| `VC-4` | `FR-5` | 运行 Runtime 日志后端/前端测试；打开日志、等待刷新并下载。 | 最多 1,000 行脱敏日志；下载字节与当前显示快照一致。 | Pytest/前端测试输出、浏览器截图、下载文件 Hash。 | 自动测试 `pass`；浏览器因缺少 Playwright Chromium 而 `blocked`。 |
| `VC-5` | `FR-6` | 重放主 A2A 用量和重复 worker `usage.updated`；再执行真实主模型和 sandbox 回合。 | 现有 Token UI 一次性展示模型、当前值与累计值；重放不放大总量。 | Decoder/前端测试、截图及 SSE。 | 自动测试 `pass`；真实验证 `blocked`。 |
| `VC-6` | `FR-7` | 配置两个可选模型；发送默认/备选回合；提交非法模型 ID；执行一次委托。 | 选择器按能力显示且忙碌时禁用；合法覆盖到达两条路径；非法 ID 在执行前拒绝。 | mpa-agent/桥接/前端测试、Runtime 日志及截图。 | 自动测试 `pass`；真实验证 `blocked`。 |
| `VC-7` | `FR-8` | 检查 Runtime metadata；完成回合后查询 `/web/runtime-trace`。 | `apmplus_enable=true`；采集中返回 425，成功返回 200 Span，或明确返回 403 权限错误。 | Runtime metadata 及规范化 Trace JSON。 | 请求测试 `pass`；当前 v31 因链路关闭为 `fail`。 |
| `VC-8` | 回归 | 运行目标测试、前端全量测试/构建、pre-commit 及默认 Python 回归。 | 无相关回归；环境依赖失败单独分类。 | 命令日志。 | 除可选依赖回归失败外为 `pass`。 |

## 覆盖门禁

每个 P0/P1 需求至少由一个可执行 Case 覆盖。需要发布的真实 Case 不得记为通过；在获得明确部署授权前保持 blocked。
