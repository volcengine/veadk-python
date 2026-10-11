# 两轮 Code Review 报告（dev-loop 步骤 8-9）

> 日期：2026-09-11
> 分支：`feat/mpa-agent-oneclick-provision`
> 范围：`veadk/cli/cli_mpa.py`、`veadk/integrations/mpa/*`、对应 tests 与双语设计/验证 Case。

## 1. 旧问题复核

| ID | 严重度 / 分类 | 位置 | 状态 | 依据 |
| --- | --- | --- | --- | --- |
| R1 Runtime 重试重复创建 | medium / Correctness | `mpa_runtime.py` | fixed | 精确同名 Runtime 复用；更新 image/Tool/env 后 `ReleaseEnable=True`，等待更新版本 Ready |
| R2 中英文 Spec 与证据漂移 | medium / Scope | `prd-spec/features/mpa-agent-oneclick-provision/` | fixed | 编排顺序、Case 结果、APIG/A2A/飞书阻断已同步 |
| R3 APIG 回退到任意 gateway | high / Correctness | `cli_mpa.py` | fixed | 仅允许显式 id、计算面 id 或 endpoint 唯一映射；共享网关无 id 时 fail-closed |

## 2. 第一轮 Findings 与修复

| ID | 严重度 / 分类 | 证据与影响 | 处置 |
| --- | --- | --- | --- |
| F1 | medium / Correctness | Runtime 重跑缺少按名复用，失败重试可能创建多个计费资源 | 已补精确同名查找与复用测试 |
| F2 | high / Correctness | APIG endpoint 不包含客户 gateway id 时，枚举 fallback 会把无关 gateway 写入 `mpa_meta`，误导 IM routing | 移除 fallback；增加 `--apig-instance-id`；真实绑定缺字段时禁止 finalize |
| F3 | medium / Scope | 双语编排 Spec 仍写单阶段播种、`not_run` 与“无阻断”，不符合实际实现/验证 | 已同步两阶段 seed、实际测试和残余阻断 |

## 3. 第二轮对抗式复盘 Findings 与修复

| ID | 严重度 / 分类 | 反例与影响 | 处置 |
| --- | --- | --- | --- |
| F4 | medium / Correctness | 精确同名 Tool 已存在但非 Ready 时继续 CreateTool，会产生重复资源 | 改为等待既有 Tool Ready；超时返回其 id/status |
| F5 | medium / Correctness | 多个精确同名 Tool/Runtime 时取首个会产生非确定绑定 | 改为歧义错误并增加测试 |
| F6 | medium / Correctness | Runtime 更新后若轮询先看到旧 Ready 版本，会误判新配置已发布 | `_wait_ready` 增加 `newer_than_version` 门槛，只有更新版本 Ready 才返回 |

## 4. 对抗式边界结论

- phase-1 `mpa_meta` 占位是首次启动绕过 `GetMpaInstanceConf` 403 的必要状态；若后续绑定不完整，行可留待同 Agent ID 重试，但不得作为成功结果输出。
- `GatewayMode=Shared` 且 `GatewayInstanceId=""` 不足以支持 IM routing；public endpoint 前缀也未匹配到账户下任何 APIG gateway。代码必须 fail-closed。
- Tool/Runtime 的名称是幂等边界。非 Ready 状态与多个精确同名是两种不同异常，分别等待与失败。
- 第一轮/第二轮修复后未发现新的 P0/P1 代码问题。

## 5. 验证

| 命令 / 验证 | 结果 |
| --- | --- |
| `uv run pytest tests/integrations/test_mpa_tool.py tests/integrations/test_mpa_runtime.py` | pass：13 passed（第二轮修复后） |
| `uv run pytest tests/cli/test_cli_mpa.py tests/integrations/test_mpa_runtime.py` | pass：22 passed（gateway/runtime 修复后） |
| targeted ruff | pass：All checks passed |
| 完整 MPA 专项测试 | pass：57 passed |
| `uv run pytest tests/cli` | pass：1282 passed, 4 skipped |
| `uv run pre-commit run --files <本功能文件>` | pass：ruff check、ruff format、Detect hardcoded secrets |

## 6. 剩余风险

- Studio A2A 最终响应仍被所选 mpa-agent image 的 ADK session revision 冲突阻断；worker 完成不等于聊天成功。
- Runtime 使用共享 APIG 且无客户 gateway id；需显式 `--apig-instance-id` 或控制面提供专属 gateway，才能 finalize IM routing 配置。
- 飞书凭据/机器人安装未提供，且专属 APIG 尚缺，因此群聊能力未验证。

## 7. 结论

两轮 review 的六项真实 finding 均已修复并有定向测试。代码层未遗留 P0/P1；上述三个外部/镜像能力风险继续保持 blocked，不作为交付成功项。
