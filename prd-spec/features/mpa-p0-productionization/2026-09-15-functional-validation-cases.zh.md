# MPA AgentKit P0 功能验证 Case

- Change ID：`mpa-p0-productionization`
- 状态：`designed`；已执行至 S5-10 兼容性预检，其余 Case 继续推进
- 日期：2026-09-15
- English：[2026-09-15-functional-validation-cases.md](2026-09-15-functional-validation-cases.md)
- PRD：[MPA AgentKit P0 功能迁移](2026-09-15-mpa-p0-productionization-design.zh.md)
- 浏览器 Runbook：[browser-cases.zh.md](browser-cases.zh.md)

## 1. 统一执行与证据约定

证据根目录为 `evidence/{automated,postgres,browser,contract,live}/<run-id>/`。执行前运行 `mkdir -p` 创建对应目录。每项记录 `caseId/timestamp/repositorySHA/runtimeImageDigest/agentkitOpenAPIVersion/workerProtocol/environment/command/status/expected/actual/artifactPaths/cleanupResult`；状态仅允许 `pass|fail|blocked|not_run|not_applicable`。日志、JSON、截图和 manifest 必须脱敏。

下列标记“需新增”的命令/文件是对应切片交付物，执行前必须先验证路径存在；它们不是当前已具备能力。Mock、内存、PostgreSQL、浏览器和 live cloud 证据不能相互替代。

## 2. 覆盖矩阵

| AC | Case | 切片 |
| --- | --- | --- |
| `AC-1` | `VC-06`, `VC-20A`, `VC-20B` | S1/live |
| `AC-2` | `VC-04`, `VC-05`, `VC-07`, `VC-20B` | M0/S1/live |
| `AC-3` | `VC-08`, `VC-09`, `VC-17`, `VC-18B` | S2/browser/PG |
| `AC-4` | `VC-10`, `VC-11`, `VC-18C` | S3/PG |
| `AC-5` | `VC-12`, `VC-13`, `VC-18D` | S4/PG |
| `AC-6` | `VC-02`, `VC-15`, `VC-18E`, `VC-20B` | M0/持续/live/PG |
| `AC-7` | `VC-14`, `VC-17`, `VC-18C` | S3/browser/PG |
| `AC-8` | `VC-16`, `VC-17` | S1-S5/browser |
| `AC-9` | `VC-19`, `VC-21` | S5/live |
| `AC-10` | `VC-16`, `VC-19`, `VC-22` | S5 |
| `AC-11` | `VC-02` 本地子集、`VC-03`、`VC-01`、`VC-20B` | M0 本地 / S5 live |
| `AC-12` | `VC-18A`, `VC-18B`, `VC-18C`, `VC-18D`, `VC-18E`, `VC-19` | M0-S5/PG |

## 3. Case 明细

### VC-01：Studio 到 Runtime 的 Profile 写链路

- 前置：隔离部署的 mpa-agent 接受已校验 Studio principal；资源前缀 `mpa-p0-e2e-*`；live manifest 已脱敏。
- 命令：`scripts/verify-mpa-p0-e2e.sh --manifest <redacted-json> --case VC-01`（runner 已存在；`VC-01` live driver stage 随 S1 增加）。
- 输入：两次 Studio Agent draft/Profile apply 请求，携带 `sourceProfileId + digest`，不携带调用方分配的 revision。
- 预期：Runtime prepare -> Profile apply/status -> update/replay -> delete 成功；Runtime 分别返回 revision 1 和 2；不调用 Managed Agent API，清理后无残留。
- 证据：`evidence/live/<run-id>/VC-01.json`、request IDs、版本序列、cleanup report。
- 失败处理：部署态失败阻止发布并回到对应 S1/S5 task，不回溯否定已完成的本地 M0 门禁；不得改用 arkcli 子进程。

### VC-02：统一 RuntimePrincipal

- 前置：真实 Studio OAuth/gateway、custom-JWT Runtime、A2A TIP、可撤权测试主体。
- 命令：live runner `--case VC-02`；Runtime `uv run pytest -q tests/test_runtime_principal.py`（需新增）。
- 输入：有效 bearer/TIP，错误 issuer/audience/kid，过期/缺 claim token，跨 scope 与已撤权主体。
- 预期：bearer/TIP 映射相同 principal；所有非法请求在副作用前 401/403；JWKS 轮换收敛。
- 证据：`evidence/live/<run-id>/VC-02.json` 与 JUnit；仅记录 issuer/audience/TTL/kid hash。
- 失败处理：本地 contract 失败阻止 S1；部署态 issuer/JWKS/撤权失败阻止发布。禁止关闭 JWT、使用 Runtime key 或用户 Header 绕过。

### VC-03：Studio Profile 映射与 Runtime client contract

- 前置：固定 Studio AgentDraft、Runtime Profile DTO/error fixture。
- 命令：`uv run --extra dev pytest tests/frontend/server/mpa/test_runtime_profile_client.py tests/frontend/server/mpa/test_profile_mapping.py -q`（`test_runtime_profile_client.py` 已存在；`test_profile_mapping.py` 随 S1 增加）。
- 输入：确定性的 AgentDraft 规范化、支持/未知字段、create/update precondition、Runtime timeout、HTTP 错误和非 JSON。
- 预期：Profile DTO/digest 稳定；转发 bearer、幂等键以及 `If-None-Match`/`If-Match` 二选一；冲突映射 `409 profile_version_conflict`；保留 request ID；Managed Agent/OpenTOP 调用次数为零。
- 证据：`evidence/contract/<run-id>/VC-03.xml` 与 fixture diff。
- 失败处理：回 Step 1 修契约或修 adapter；不得放宽 schema/吞错。

### VC-04：Profile precondition 与版本

- 前置：Runtime local backend、空/已有 Profile 两种 fixture。
- 命令：`PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_profile_apply.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-04.xml`（需新增）。
- 输入：`If-None-Match`、`If-Match`、双 header、无 header、stale ETag、相同 operation key 的同/异 digest。
- 预期：分别为成功、成功、400、428、412、幂等 replay/`409 idempotency_mismatch`；Runtime 只在 CAS 成功时分配一个新 revision 并返回强 ETag。
- 证据：JUnit、revision count/current row 断言。
- 失败处理：修 precondition/service/store 后重跑；不得弱化冲突断言。

### VC-05：Runtime operation ledger

- 前置：可注入 clock 的内存 store；24 小时 TTL fixture。
- 命令：`PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_runtime_operations.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-05.xml`（需新增）。
- 输入：Profile/run/upgrade/continue 的同 key 同/异 hash、跨 principal、TTL 边界。
- 预期：唯一 ledger、同请求 replay、异请求 409、越权不可见、状态可查询、pending Profile 不切 current。
- 证据：JUnit、operation 状态序列和无 Secret 快照。
- 失败处理：修 ledger 唯一键/授权/过期逻辑；PostgreSQL 竞态由 VC-18B/C 复验。

### VC-06：持久 MPA lifecycle operation

- 前置：TOS fake 支持 forbid-overwrite/ETag；Runtime/Profile/smoke adapter 可注入 failpoint。
- 命令：`uv run --extra dev pytest tests/frontend/server/mpa/test_agent_operations_repository.py tests/frontend/server/mpa/test_agent_operations_service.py tests/frontend/server/mpa/test_agent_routes.py -q`（需新增）。
- 输入：create/update 幂等键；首次响应丢失；Runtime/Profile/smoke 前后 crash；cleanup 失败。
- 预期：均返回 `202 + operationId`；同 key 恢复原 operation；active list 找回；retry 从安全阶段继续；副作用 effect 至多一次。
- 证据：`evidence/automated/<run-id>/VC-06.xml`、TOS ETag、attempt/effect count、阶段序列。
- 失败处理：任何重复 Runtime/Profile effect 或刷新丢失均阻断 S1。

### VC-07：Profile 参数映射

- 前置：固定 Studio AgentDraft/Profile fixture 和 runtime Profile DTO。
- 命令：VeADK `uv run --extra dev pytest tests/frontend/server/mpa/test_profile_mapping.py -q --junitxml=prd-spec/features/mpa-p0-productionization/evidence/contract/<run-id>/VC-07-veadk.xml`；Runtime `uv run pytest -q tests/test_profile_apply.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/contract/<run-id>/VC-07-runtime.xml`（需新增目标文件）。
- 输入：全部已支持字段、无版本 Skill、不支持 Tool/Multiagent、Secret/signed URL。
- 预期：映射 `sourceProfileId`、name、description、System、Model、Tools、Skills、MCP、Multiagent、allowlisted Metadata；`profileRevision` 由 Runtime 分配；资源版本先解析；不支持字段 422；只传 Secret ref。
- 证据：`evidence/contract/<run-id>/VC-07.json` 与两仓 JUnit。
- 失败处理：修映射/allowlist；不得将未知字段静默丢弃后声称 applied。

### VC-08：execution-config CAS

- 前置：Runtime local backend，Session revision 1，资源 resolver fixture。
- 命令：Runtime `uv run pytest -q tests/test_session_execution_config.py tests/test_session_execution_config_service.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-08.xml`。
- 输入：缺失/stale/correct ETag，replace/clear/inherit，失效/撤权资源，活动 Turn。
- 预期：缺 ETag 428、stale 412；配置语义准确；失败无 revision；活动 Turn 不变、下一 Turn 生效。
- 证据：JUnit、revision/effective refs/Turn record 快照。
- 失败处理：修 CAS/resolver/transaction；双连接由 VC-18B 复验。

### VC-09：显式 Profile revision 升级

- 前置：Session 固定 N，N+1 Profile 已 applied；可构造无效 target。
- 命令：Runtime `uv run pytest -q tests/test_session_execution_config_service.py -k profile_upgrade --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-09.xml`。
- 输入：合法/重复/旧 ETag/未 applied/不存在/降级版本，override/clear/inherit。
- 预期：目标 Profile 作新 base，保留 override/clear，inherit 跟新默认；无效目标原子拒绝；活动 Turn 用 N、下一 Turn 用 N+1。
- 证据：JUnit、升级前后 revision 与 Turn 对照。
- 失败处理：失败升级若改变旧 revision 立即阻断 S2。

### VC-10：Run 强幂等

- 前置：Session/config fixture、可计数 dispatcher。
- 命令：`PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_run_acceptance.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-10.xml`（需新增）。
- 输入：缺 key/version、stale config、同 key 同/异 payload、同 Session 并发。
- 预期：明确 4xx；stale 在副作用前失败；同请求同 invocation；异内容 409；仅一个 active Turn。
- 证据：JUnit、operation/Turn/inbox rows 与 effect count。
- 失败处理：任何重复 effect 阻断 S3。

### VC-11：Outbox crash recovery

- 前置：可注入 dispatcher 与 commit/dispatch/writeback/terminal failpoint。
- 命令：`PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_turn_dispatcher.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-11.xml`（需新增）。
- 输入：各 failpoint 和 Runtime restart。
- 预期：唯一 dispatch key；允许 dispatcher attempt 重试，但外部 A2A Task/Turn/副作用 effect count 恰好 1；operation/Turn/inbox 收敛。
- 证据：JUnit、attempt count、effect count、恢复状态日志。
- 失败处理：重复外部 effect 或丢失 intent 阻断 S3；不得靠事后删重复记录通过。

### VC-12：Pause barrier

- 前置：fake clock，primary + 两 worker participant fixture。
- 命令：`PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_turn_participants.py tests/test_turn_control_api.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-12.xml`（需新增首个文件）。
- 输入：全部/部分 ACK、旧 generation ACK、lease expiry、pause 与 spawn 竞态、重复/冲突 control key。
- 预期：同 generation 全 ACK 才 paused；其余保持 pausing/分类失败；旧 ACK 无效；幂等结果稳定。
- 证据：JUnit、participant generation/ACK/lease 时间线。
- 失败处理：误报 paused 或旧 ACK 改状态阻断 S4。

### VC-13：Resume 与 continuation

- 前置：fake clock、outbox dispatcher、可恢复/不可恢复 owner fixture。
- 命令：`PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_turn_continuation.py tests/test_turn_safe_point_spike.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-13.xml`（需新增首个文件）。
- 输入：暂停 299/300/301 秒、lease viable/lost、restart、重复/并发 continue。
- 预期：≤300 秒恢复原 Turn；其余只返回 new-turn-required；显式 continue 创建唯一 linked Turn；outbox 可恢复。
- 证据：JUnit、fake-clock timeline、old/new Turn 与 dispatch intent。
- 失败处理：真实 sleep、自动建新 Turn 或重复 effect 均阻断 S4。

### VC-14：持久 SSE replay

- 前置：持久 ADK events、inbox terminal fixture、可重建 StreamHub。
- 命令：`PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_session_sse_persistent_replay.py tests/test_session_sse_edges.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-14.xml`（需新增首个文件）。
- 输入：合法/未知 cursor、跨 Pod/重启、persistent/live 重叠、queued/running/error/aborted、不同 invocation。
- 预期：仅 replay cursor 后事件；未知 cursor 410；文本/usage/artifact/terminal 各一次；error/aborted 准确；无终态不成功；不串 invocation。
- 证据：JUnit 和 SSE `id/event/data` 序列 JSONL。
- 失败处理：禁止未知 cursor 全量重播；重复或错误终态阻断 S3。

### VC-15：Secret migration 与泄漏

- 前置：schema 0 含 canary secret，fake secret provider 可成功/失败。
- 命令：`PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_secret_reference_migration.py tests/test_session_redaction.py tests/test_runtime_console_api.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-15.xml`（需新增首个文件）。
- 输入：AgentKit mode 新明文写、旧值迁移中断/重试、legacy 只读、旧镜像回滚。
- 预期：新明文写拒绝；成功转 ref 后清空；失败不清空；重试不重复；API/log/trace 无 canary；不兼容回滚被 fence。
- 证据：JUnit、仅显示 empty/ref-type 的 DB 前后快照、secret scan。
- 失败处理：任何泄漏或数据丢失阻断发布。

### VC-16：MpaAgentView 与页面隔离

- 前置：BFF fixture 覆盖 0/1/N binding、orphan、applied/target、旧 Runtime。
- 命令：`uv run --extra dev pytest tests/frontend/server/mpa/test_agent_view.py -q && npm --prefix frontend test`（需新增首个文件与 `mpaAgents.test.mjs`/`mpaAgentDetail.test.mjs`）。
- 输入：所有 view 状态、不同 scope 的同 ID、慢响应切换。
- 预期：view-model 合并正确；写门禁正确；MPA 不进入 GitHub/generic draft/evaluation；缓存不串；无 Secret。
- 证据：`evidence/automated/<run-id>/VC-16.json`、pytest/npm 输出。
- 失败处理：状态误判或误入通用流阻断 S5。

### VC-17：真实浏览器

- 前置：test-only scenario harness 与 gstack/Chromium 可用。
- 命令：S1 执行 BC-01/02 与 BC-07 create-busy/IME 子集；S2 执行 BC-04/05；S3 执行 BC-06；S4 执行 BC-09；S5 严格执行 [browser-cases.zh.md](browser-cases.zh.md) 的 BC-01～BC-09 全量回归。
- 输入：创建/失败/刷新/双客户端/upgrade/cursor/IME/窄屏场景。
- 预期：各切片子集通过仅作为切片门禁；S5 全部 BC pass 且 console 无未处理错误后才将 `VC-17=pass`。
- 证据：`evidence/browser/<run-id>/<case-id>/`。
- 失败处理：环境不可用为 `blocked`；Node tests 不替代。

### VC-18A：PostgreSQL 基座

- 前置：Docker 可用；需新增 Runtime `docker-compose.test.yml`、schema-0 fixture、PG integration test 与 Make target。
- 命令：`make test-postgres TEST_SELECT='foundation or migration_harness'`。
- 输入：PostgreSQL 16、schema 0、两连接、restart/failpoint harness。
- 预期：容器、migration runner、双连接、重启与 failpoint 基础设施可用；基础 schema migration 可重入；finally 清理 container/volume。
- 证据：`evidence/postgres/<run-id>/VC-18A.xml`、image digest、schema dump、cleanup。
- 失败处理：阻断 S1；不可用内存替代。

### VC-18B：PostgreSQL Profile/Session CAS

- 前置：VC-18A 与 S2 实现完成。
- 命令：`make test-postgres TEST_SELECT='profile_cas or execution_config_cas or upgrade_cas'`。
- 输入：两连接同 ETag/profile revision 并发。
- 预期：一个成功、一个冲突；无 lost update；唯一 current Profile/config revision。
- 证据：`evidence/postgres/<run-id>/VC-18B.xml` 与 rows。
- 失败处理：阻断 S2。

### VC-18C：PostgreSQL Outbox/SSE

- 前置：VC-18A 与 S3 实现完成。
- 命令：`make test-postgres TEST_SELECT='active_turn or ledger or outbox or sse_restart'`。
- 输入：并发 run、三 failpoint、restart、persistent cursor。
- 预期：唯一 active Turn/effect；outbox 收敛；重启后 cursor replay 正确。
- 证据：`evidence/postgres/<run-id>/VC-18C.xml`。
- 失败处理：阻断 S3。

### VC-18D：PostgreSQL Participants/Continuation

- 前置：VC-18A 与 S4 实现完成。
- 命令：`make test-postgres TEST_SELECT='participant or continuation'`。
- 输入：并发 ACK/lease/generation/continue。
- 预期：row lock/CAS 正确；全 barrier；唯一 linked Turn/effect。
- 证据：`evidence/postgres/<run-id>/VC-18D.xml`。
- 失败处理：阻断 S4。

### VC-18E：PostgreSQL Secret migration

- 前置：VC-18A 与 S5 Secret reference 实现完成；schema 0 含 canary 明文值；fake secret provider 可成功或失败。
- 命令：`make test-postgres TEST_SELECT='secret_migration'`。
- 输入：reference 创建成功、provider 失败、清空前进程中断、重启重跑、旧镜像回滚。
- 预期：成功建 ref 后才清空；失败/中断保留旧值；重跑不重复 ref；最终 DB/log/evidence 无 canary；不兼容回滚被拒绝。
- 证据：`evidence/postgres/<run-id>/VC-18E.xml`、仅显示 empty/ref-type 的 DB 快照和 secret scan。
- 失败处理：阻断 S5 和发布；不得以 local/fake 结果替代。

### VC-19：兼容、回归与性能

- 前置：S1～S5 的实现和非 live Case 已完成，但 `VC-21` 尚未执行；M0 已写入双方 SHA/image digest/协议版本。先以兼容矩阵 runner 完成发布前 preflight，再执行 VC-21；VC-21 后重跑本 Case 的全量回归/性能部分作为最终门禁。
- 命令：`scripts/verify-mpa-p0-contract.sh --manifest <redacted-compatibility-json> --matrix contracts/mpa-p0/compatibility-matrix.json`，随后 Runtime `make test && make coverage && make test-postgres`，VeADK `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" && npm --prefix frontend test && npm --prefix frontend run build && uv run --extra dev pre-commit run --all-files`。性能 runner 为 `scripts/benchmark-mpa-p0.py --warmup 5 --requests 100 --concurrency 10 --list-size 20`。
- 输入：PRD 全部兼容组合和固定 fixtures。
- 预期：矩阵结果吻合；MPA update/release/rollback 写路由在副作用前拒绝不兼容 manifest；Runtime coverage ≥95%；无回归；性能报告含 p50/p95/max/error rate。
- 证据：`evidence/contract/<run-id>/VC-19.json`、测试/build/coverage/benchmark 输出。
- 失败处理：允许组合失败或指标超限阻断 S5；矩阵外需求先回 Step 1。
- 2026-09-18 执行记录：S5-10 使用固定 VeADK `486dc06e429573ce43d6462b6dc960be4bc34ab6`、Runtime `eecc6e3115685e5cb86dcfbff4fb7c6ac7a10dee` 和已部署 v62 镜像 digest `sha256:6ac6a2712ecd1c7950125dc9afc6467373a08142fbd6c3577aba12f126079bef` 完成预检。实时 Runtime 为 version 62、状态 `Ready`，registry 查询结果与固定 digest 一致。真实 manifest 命中 `p0-codex-rest-v1`；负向 fixture 按预期返回 `worker_protocol_incompatible` 和 `invalid_runtime_image_digest`。证据位于 `evidence/contract/s5-10-v62-20260918/`。这不代表 VC-21 后的最终全量回归/性能部分已完成；该部分仍属于 S5-13。

### VC-20A：S1 live 创建至首轮对话

- 前置：M0 全绿；S1 实现完成；隔离账号/region/project、写删权限、配额、成本上限、镜像 digest、DB 和 cleanup owner 已写入 manifest；ArkClaw endpoint 阻断。
- 命令：`scripts/verify-mpa-p0-e2e.sh --manifest <redacted-json> --case VC-20A`（需新增）。
- 输入：全新 Agent、最小 Profile、合法 model。
- 预期：创建 operation、Runtime、Profile、deterministic smoke、mpa-agent Session 和首轮 A2A/worker/result 成功；Session create/read、A2A acceptance、worker/tool dispatch 使用共享 authorizer，撤权后 effect count 为 0；不要求 S2～S4 的 upgrade/cursor/continue。
- 证据：`evidence/live/<run-id>/VC-20A/` 中 manifest、operation、HTTP/SSE、trace、cleanup。
- 失败处理：权限/配额不足记 blocked；功能失败记 fail；EXIT trap 清理，清理失败单独阻断 S1。

### VC-20B：完整 live 创建、身份与 Profile 回归

- 前置：M0 全绿；隔离账号/region/project、写删权限、配额、成本上限、镜像 digest、DB、cleanup owner 已写入 manifest；ArkClaw endpoint 阻断。
- 命令：`scripts/verify-mpa-p0-e2e.sh --manifest <redacted-json> --case VC-20B --cases AC-11,AC-1,AC-2,AC-6`（需新增）。
- 输入：全新 Agent、最小 Profile、合法 model、有效/非法/撤权身份。
- 预期：创建到首轮 A2A/worker/result；Profile update/replay/conflict；安全拒绝；中断可续；最终清理零残留。
- 证据：`evidence/live/<run-id>/VC-20B/` 中 manifest、operation、HTTP/SSE、trace、cleanup。
- 失败处理：权限/配额不足记 blocked；功能失败记 fail；EXIT trap 清理，清理失败单独阻断。

### VC-21：Runtime 生命周期、回滚与删除

- 前置：VC-19 允许目标/回滚组合；live manifest 含 current/target/rollback image digest；有 active Session/shared resource fixture。
- 命令：`scripts/verify-mpa-p0-e2e.sh --manifest <redacted-json> --case VC-21`（需新增）。
- 输入：合法 update/release、受控失败、兼容 rollback、不兼容 downgrade、malformed compatibility manifest、存在 active MPA operation 的删除预览、存在 active Runtime Session 的删除预览、包含可见 idle Runtime Session 的删除执行、最终 delete。
- 预期：每步有 operation ID/request ID/version timeline；受控失败可恢复；不兼容 downgrade 或 manifest 在 mutation 前拒绝；兼容回滚后 smoke 通过；删除预览在 mutation 前返回阻断原因和清理阶段；active operation 或 active Session 以 `409` 阻止删除；idle 可见 Session 先通过 Runtime `DELETE /api/v1/sessions/{sessionId}` 删除，再删除 AgentKit Runtime；最终删除且零残留。
- 证据：`evidence/live/<run-id>/VC-21/` 中版本时间线、平台响应、smoke trace、cleanup report。
- 失败处理：任一 unsafe mutation、错误成功状态或残留资源均使 `AC-9=fail`。

### VC-22：CLI parity

- 前置：共享 `MpaControlPlaneClient` 和 CLI 命令已实现，受控 BFF fixture 可用。
- 命令：`uv run --extra dev pytest tests/integrations/test_mpa_control_plane_client.py tests/cli/test_cli_mpa_control.py -q`。
- 输入：`veadk mpa control` 的 view、create/update、operation list/get/retry、Profile status/apply、Session config get/patch/profile-upgrade、delete preview，以及 401/403/409/412/428、旧 Runtime、timeout/replay；不调用 Managed Agent endpoint，也不直连 Runtime URL。历史基础设施命令仍为 `veadk mpa create`。
- 预期：CLI 不 import FastAPI route；与 Studio 共用 schema 和 `MpaControlPlaneClient`；写操作携带由调用方持久复用的 key 并处理 202；CAS 命令要求当前 ETag 或 Runtime revision；JSON 可解析；不输出 bearer、Runtime credential 或含 Secret 的 Profile 字段。退出码固定为：`0` 成功、`2` 本地用法/输入错误、`3` 鉴权错误、`4` 冲突/前置条件错误、`5` 可重试 transport/server 失败、`1` 其他控制面失败。timeout 后重试复用同一 key，不重复写。Chat/Turn/Debug 因缺少共享 Studio BFF CLI 契约，不属于本 Case；CLI 不得通过绕过 Studio 补偿。
- 证据：`evidence/automated/<run-id>/VC-22.xml`、UI/CLI 响应对照与 secret scan。
- 失败处理：任何语义分叉、重复写或泄漏阻断 S5。

## 4. 准出规则

1. M0 只要求 `VC-02` 本地子集、`VC-03`、`VC-18A` 与 live runner dry-run。部署态 `VC-01/02` 在 `S5-14` 执行；`VC-04/05` 由 S1 实现后执行，不得形成前置环。
2. 每个切片自身 Case 与持续安全 Case 通过后才进入下一切片。
3. live Case 需要明确授权；缺权限为 `blocked`，不得用 mock 替代。
4. 任一 P0/P1 Case 失败，回对应 SDD/TDD Task 修复并重跑。
5. Step 7 所有 P0/P1 Case 通过后才进入两轮 Review；Step 10 E2E 通过后才进入提交。
