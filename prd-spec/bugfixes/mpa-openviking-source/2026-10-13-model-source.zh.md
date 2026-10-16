# OpenViking 模型来源及已拒绝意图恢复

[English](2026-10-13-model-source.md)

日期：2026-10-13。状态：已实现；待真实验收。基础：`71175c68636dc5b951e9804eb292d85402511e68` 加未提交的自动 OV 功能。

## 背景与范围
用户创建的北京 MPA 完成 Worker 准备后，CreateOpenVikingCollection 返回 InvalidParameter：模型来源为空。云审计确认明确拒绝，不是未知创建结果。因此不能省略 Credentials。参考库即便控制台显示自配凭证为空，接口仍返回 Source volcengine 与带版本模型标识。官方建库文档要求 volcengine 的 Source、EndpointID，并要求条件性的 ApiKey。
目标：保留北京自动 OV，显式传入模型来源/标识及已经解析的部署账号方舟 Key。不新增页面输入、不创建模型接入点、不改 BytePlus/通用智能体、不更新现有 OV 凭证，也不在没有单独用户操作/授权时执行付费云重试。

## 要求与设计
- FR-1：VLM Credentials 使用 Source `volcengine`、EndpointID `doubao-seed-2-0-lite-260428`；Embedding 使用 Source `volcengine`、EndpointID `doubao-embedding-vision-251215`。保留原模型名/版本。标识来自参考库，新 API 创建是否接受仍需真实验证。
- FR-2：适配器单独接收已解析方舟模型 Key，本地校验后仅将 ApiKey 加入复制的网络请求。非秘密意图含 Source/EndpointID，但没有模型 Key。注册库、任务结果、诊断及 repr 不得出现方舟或 OV Key。新 Studio 使用账号自动发现的 Key；显式启用的 CLI 可使用配置模型 Key，包括模板 MODEL_AGENT_API_KEY。缺失/掩码/非法 Key 在发送前以现有配置错误拒绝。注册库重试仅重新取 OV Key，不重发模型凭证。
- FR-3：仅当没有 OV ID、没有待完成 Runtime 操作、openviking_create_requested 明确为 false，才升级完全匹配的旧无 Credentials 意图。这是明确拒绝后的持久状态。未知/进行中创建、项目/名称/模型/描述改变及已注册 ID 继续安全拒绝，不删除绑定或重置标志来绕过失败。恢复保留智能体/库名，发送前登记修正的非秘密意图。
- FR-4：复用前核验 Get 的 Source/EndpointID，不持久化返回的 Key。保留锁、超时、取消、单次创建与就绪语义。每次创建最多发送一次，不增加付费回退。

## 影响文件与任务
OpenViking 适配器/资源准备、MPA 服务透传、目标 OV/service 测试、双语创建契约及使用/设计说明。没有前端或 Runtime 协议变化，仍使用已支持的四个 OV 环境变量。T-1 请求凭证/不持久化秘密回归；T-2 来源核验与明确拒绝意图恢复；T-3 透传现有模型 Key；T-4 受影响创建回归、Ruff/Pyright、秘密扫描及双语文档检查。

## 验收、风险与评审
AC-1 网络凭证明确，非秘密意图稳定；AC-2 同一失败智能体仅在明确拒绝后可恢复；AC-3 改变/未知/已登记请求不重复建库；AC-4 BytePlus/手动/通用流程保持行为并记录检查。接入点别名、模型/Key 权限仍需真实验收，默认模型可能需要账号开通。确认前不声称云建库成功。
review-spec 不可用，直接设计评审核验兼容、秘密生命周期、请求复制、归属、拒绝与未知结果、取消/期限及双语等价。用户于 2026-10-13 要求修复缺失来源，具体方案复用已有方舟 Key 并保留失败任务身份。未授权提交、推送或云重试。

## 验证
测试先行回归：实现前 27 失败 / 2 通过（缺少新增关键字及显式 Credentials）。实现后 OV/service 192 项通过。最终广泛创建/RBAC 回归以两个 worker 执行，1,087 项通过。参考库只读 Get 核实了 Source 和两个 EndpointID 的准确值，这不等于新库创建验收。

| 检查（2026-10-13，未提交修正） | 结果 |
| --- | --- |
| `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed/test_openviking.py tests/integrations/mpa_managed/test_service.py` | pass：192 |
| `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/frontend/server/mpa/test_runtime_profile_routes.py tests/cli/test_studio_rbac.py` | pass：1,087 |
| `uvx ruff==0.11.12 check <four-correction-python-files>` 及 `format --check` | pass |
| `uvx pyright --pythonpath .venv/bin/python <four-correction-python-files>` | pass：0 错误/警告 |
| `uv run --extra dev pre-commit run gitleaks --files <changed-files>` | pass：源码/测试/文档/构建产物 |
| 双语文档、链接/标识及 `git diff --check` | pass |
| 前端重建/浏览器 | not_applicable：本修正未修改前端，初版 auto-OV 前端检查保留在功能 PRD 中 |
| 修正后真实创建 / 取 Key / Runtime 就绪 | not_run：用户可重试原失败任务，未自动执行云写操作 |
| 全仓库 pre-commit / commit / push | not_run：未要求提交 |

评审：网络请求使用副本；凭证不进入注册意图；来源/接入点回读排除秘密字段；已登记/未知/改变请求不能升级。AC-1–AC-4 实现/离线检查完成，修正后真实云验收待完成。每次重试启动新的 runner 进程，所以该子进程修正在重试时加载，无需改变已有浏览器请求。
