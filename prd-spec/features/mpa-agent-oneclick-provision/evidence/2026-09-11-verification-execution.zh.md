# 功能验证 Case 执行报告（dev-loop 步骤 7 与步骤 10）

> 执行日期：2026-09-11
> 分支：`feat/mpa-agent-oneclick-provision`
> 被测范围：`veadk mpa create`、`veadk/integrations/mpa/*`、真实 AgentKit Tool/Runtime、Studio A2A。

## 1. 执行汇总

| Case | 结果 | 证据 / 说明 |
| --- | --- | --- |
| VC-1..17 | pass | CLI 注册、参数/secret、VeFaaS 兼容、两阶段 `mpa_meta`、env、key-auth probes、dry-run、回归均由单测/CLI 测试覆盖 |
| VC-18 Studio A2A 聊天 | blocked | Runtime/worker 可执行，但两个 A2A 请求最终均返回 `failed`：`The session has been modified in storage since it was loaded` |
| VC-19 不同 session 不同沙箱 | pass（资源隔离层） | 两个不同 A2A context 映射到 `cw_sess_872f64f2f00b` 与 `cw_sess_bdf3758b4ddd` |
| VC-20 飞书拉群 | blocked/not_run | 未提供飞书凭据/机器人安装；Runtime 共享网关没有客户 `apig_instance_id` |
| VC-21 自动身份与独立资源 | pass | Agent `mi-tyfybtw8nnzc`，Tool `t-yeuugdts00zn6n5iqhin`，Runtime `r-yeuugf44qob21078l38i` |
| VC-22 缺 Tool 输入无副作用 | pass | 参数前置校验测试确认 SkillSpace/DB/Tool/Runtime 零调用 |
| VC-23 worker 模型选择 | pass | `MPA_CODEX_WORKER_DEFAULT_MODEL=doubao-seed-2-0-pro-260215`；两个 worker turn 模型 HTTP 200、命令 exit code 0、binding completed |
| VC-24 重试幂等 | pass | 同名 Tool/Runtime 复用；非 Ready Tool 等待；重名歧义失败；Runtime 更新等待新版 Ready |
| VC-25 APIG 完整性 | pass（fail-closed） | 真实 Runtime：`GatewayMode=Shared`、`GatewayInstanceId=""`；endpoint 不匹配账户 gateway；CLI 拒绝 finalize，支持显式 `--apig-instance-id` |

## 2. 真机资源与状态

- Account：`2112682748`。
- Agent：`mi-tyfybtw8nnzc`。
- Tool：`t-yeuugdts00zn6n5iqhin`。
- Runtime：`r-yeuugf44qob21078l38i`，version 4，Ready。
- Public endpoint：`https://s6rrc31qdjfa7m90q4opi.apigateway-cn-beijing.volceapi.com`。
- Runtime 外层 APIG key auth 可用；`A2A_TIP_VERIFY_ENABLED=false` 解决镜像内部无 TIP issuer 时的 401，同时不取消外层 key auth。
- 数据库现有行仍为 `apig_instance_id=pending`；由于无法获得真实客户 APIG id，不能把它视为 finalize 成功。

## 3. Studio A2A 与沙箱证据

指定模型后，两个独立 context 都成功进入不同 worker session：

| Turn | Worker session | Worker 结果 | A2A 最终结果 |
| --- | --- | --- | --- |
| `turn_f896d856f1c1` | `cw_sess_872f64f2f00b` | completed，命令 exit code 0 | failed：ADK session revision 冲突 |
| `turn_fe422c33aa56` | `cw_sess_bdf3758b4ddd` | completed，命令 exit code 0 | failed：ADK session revision 冲突 |

结论：VC-19 的 session→sandbox 隔离得到真实证明，VC-23 的模型路由/worker 执行通过；但 VC-18 要求的是 Studio 收到成功聊天结果，因此必须保持 blocked。根因位于指定 mpa-agent image 的 PostgreSQL ADK session revision 协调：持久事件推进了 session revision，而 A2A runner 仍持有旧快照。veadk 不应吞掉或伪装该失败。

## 4. APIG 与飞书阻断

控制面原始字段为 `GatewayMode=Shared`、`GatewayInstanceId=""`。public endpoint 前缀 `s6rrc31qdjfa7m90q4opi` 也不匹配账户中的 APIG gateway id。因此：

- CLI 不再回退选择任意 serverless gateway；
- 可用 `--apig-instance-id` 显式传入 IM routing 对应的专属客户 gateway；
- 未取得真实 id 时，phase-2 `mpa_meta` finalize 失败并保留占位；
- 飞书验证同时缺少 Feishu App 凭据/机器人安装，VC-20 不可执行。

此外，`arkclaw:ListResources` 对 `clawspace/csi-2112682748` 返回 403，MCP discovery 会 fallback；这是飞书/集成能力的权限风险，不影响已证明的 Tool/worker 执行。

## 5. OpenViking 说明

提供的 OpenViking endpoint 与当前 bearer OpenViking Server API 契约不兼容，因此本次真实 Runtime 未注入该配置。PostgreSQL/OpenViking 均按设计作为外部既有资源，不由 CLI 创建。

## 6. 回归与门禁

- 第二轮 review 后定向 Tool/Runtime：13 passed。
- gateway/CLI + Runtime：22 passed。
- targeted ruff：All checks passed。
- 完整 MPA suite：57 passed。
- 完整 `tests/cli`：1282 passed，4 skipped（36 条依赖弃用 warning，无失败）。
- `uv run pre-commit run --files <本功能文件>`：ruff check、ruff format、Detect hardcoded secrets 全部通过。系统 PATH 无独立 `pre-commit`，因此使用仓库虚拟环境入口；门禁内容相同。

## 7. 验收结论

- 创建编排、动态 Tool/Agent ID、Runtime Ready、模型路由、不同 session 不同 sandbox：通过。
- APIG 绑定：实现通过 fail-closed 验证；真实共享网关缺少客户 APIG id，需显式适配或控制面能力。
- Studio 交互聊天：blocked（指定镜像 ADK session revision 冲突）。
- 飞书拉群：blocked/not_run（凭据/机器人安装 + 专属客户 APIG 缺失）。

因此本次交付可提交 veadk 编排实现与风险证据，但不得宣称 mpa-agent 全链路 E2E 已通过。
