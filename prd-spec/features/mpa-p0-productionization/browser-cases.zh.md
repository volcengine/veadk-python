# MPA AgentKit P0 浏览器验证 Runbook

- 状态：`designed`；对应 `VC-17`
- English：[browser-cases.md](browser-cases.md)
- 证据：`evidence/browser/<run-id>/<case-id>/`

## 1. 公共环境

- M0 新增 `scripts/run-mpa-p0-browser-fixture.sh`，仅在 `APP_ENV=test`、`VEADK_MPA_TEST_SCENARIOS=1`、loopback bind 时启动；任一条件不满足则拒绝。
- 测试 API：`GET /__test/mpa/scenarios`、`PUT /__test/mpa/scenarios/{name}`、`GET /__test/mpa/scenarios/{name}`、`POST /__test/mpa/scenarios/{name}/calls/{call}`、`POST /__test/mpa/scenarios/{name}/barriers/{barrier}/release`。生产路由表中不得存在这些接口。
- 固定 scenario：`create_success`、`profile_apply_failed`、`smoke_worker_not_ready`、`smoke_output_mismatch`、`cleanup_failed`、`runtime_missing`、`binding_ambiguous`、`orphan_runtime`、`old_runtime`、`session_revision_6`、`cursor_expired`、`slow_scope_switch`、`turn_lifecycle`。S4-07 已实现 `turn_lifecycle` 的 participant barrier、control/continue 路由、call count 和 BC-09 使用的状态证据。
- 启动：调用方先执行 `umask 077; VEADK_MPA_SCENARIO_TOKEN=$(openssl rand -hex 32); printf '%s' "$VEADK_MPA_SCENARIO_TOKEN" > .gstack/<run-id>-scenario.token`，确认 `scripts/run-mpa-p0-browser-fixture.sh` 已存在且 token 文件权限为 `0600`，再以 `APP_ENV=test VEADK_MPA_TEST_SCENARIOS=1 VEADK_MPA_SCENARIO_TOKEN_FILE=.gstack/<run-id>-scenario.token scripts/run-mpa-p0-browser-fixture.sh --host 127.0.0.1 --port 8000` 启动。结束后删除 token/state 文件；token 不进入日志或 evidence。
- 浏览器：`B=$HOME/.claude/skills/gstack/browse/dist/browse`；A 调用 `env BROWSE_STATE_FILE=.gstack/<run-id>-a.json $B ...`，B 调用 `env BROWSE_STATE_FILE=.gstack/<run-id>-b.json $B ...`。两者分别打开带 fixture 所需测试登录态的 Studio URL，断言 principal hash 相同，但 cookie/localStorage/sessionStorage 相互隔离。
- 测试 API 从 `VEADK_MPA_SCENARIO_TOKEN_FILE` 读取 token。调用模板：`curl -fsS -H "Authorization: Bearer $(<.gstack/<run-id>-scenario.token)" -X PUT http://127.0.0.1:8000/__test/mpa/scenarios/create_success -H "Content-Type: application/json" --data '{"barriers":[]}'`；用 `GET /__test/mpa/scenarios/{name}` 读取状态，`POST /__test/mpa/scenarios/{name}/calls/{call}` 记录 call count，`POST /__test/mpa/scenarios/{name}/barriers/{barrier}/release` 释放 barrier。seed 响应必须包含准确的 `barriers{}` 状态；所有测试 API 请求都使用同一 Header。
- 公共浏览器命令：两端分别以各自 `BROWSE_STATE_FILE` 调用 `goto http://127.0.0.1:8000`、`snapshot -i -a -o <path>`、`console --errors`、`network`、`viewport <WxH>`。每个 Case 前 reset/seed，之后保存 call-count 并 reset。

## BC-01：创建与刷新恢复（`AC-1`, `AC-8`）

- 前置：seed `create_success`；记录客户端幂等键。
- 操作：从 Tab/Header/空态分别创建；在 runtime/profile/smoke 阶段各执行 `$B reload`、`$B snapshot -D`。
- 输入：同一最小 Profile、region 和三种 `source`。
- 预期：intent 均含 `category=mpa`；POST 返回 202；刷新用 operation ID/active list 恢复；每种资源 effect count 为 1；清理后才 runnable/chat enabled。
- 证据：`BC-01/{tab,header,empty,refresh}.png`、`network.txt`、`call-counts.json`。
- 失败：重复资源、丢 operation 或提前 runnable 均为 `fail`。

## BC-02：创建失败与重试（`AC-8`）

- 前置：依次 seed `profile_apply_failed`、`smoke_worker_not_ready`、`smoke_output_mismatch`、`cleanup_failed`。
- 操作：创建、等待失败、截图、点击 retry；从各 seed 响应读取并逐个释放 `barriers[]`，等待终态。
- 输入：同一 Profile 与持久 idempotency key。
- 预期：安全错误/阶段/retry 明确；chat disabled；retry 从安全阶段继续；effect count 不增加。
- 证据：`BC-02/<scenario>-before.png`、`after.png`、network/call-counts。
- 失败：误报 runnable、泄密或重复副作用为 `fail`。

## BC-03：Agent 详情与版本（`AC-8`, `AC-10`）

- 前置：逐个 seed `runtime_missing`、`binding_ambiguous`、`orphan_runtime`、`old_runtime` 及正常单 binding。
- 操作：打开列表/详情/版本，执行 snapshot、检查按钮 enabled/disabled。
- 输入：同 ID 不同 scope fixture 和 target/applied mismatch。
- 预期：0/1/N/orphan/unsupported 状态符合 `MpaAgentView`；版本来自 AgentKit；无 GitHub delivery/generic draft/evaluation/optimization；无 Secret。
- 证据：`BC-03/<scenario>.png`、console/network、view JSON。
- 失败：绑定误判、错误写入口或跨 scope 数据为 `fail`。

## BC-04：双客户端 CAS（`AC-3`, `AC-8`）

- 前置：seed `session_revision_6`；A/B 用同一测试用户独立登录；记录相同 principal hash、Session ID、ETag 6。
- 操作：A/B 分别提交 model/Skill PATCH；fixture 使用 `config-patch-a`、`config-patch-b` 两个 barrier，在两者 call-count 均为 1 后依次调用认证的 barrier release API。
- 输入：两个请求均显式带 ETag 6。
- 预期：一方 200/revision 7，另一方 412；失败端显示权威状态并要求显式 retry；最终两端一致。
- 证据：`BC-04/context-{a,b}.png`、两个 network transcript、barrier/call-count。
- 失败：不同 principal、请求未同时基于 revision 6、静默覆盖均为 `fail`。

## BC-05：显式 Session 升级（`AC-3`, `AC-8`）

- 前置：Session 固定 N、N+1 已 applied、活动 Turn fixture。
- 操作：确认只显示“新版本可用”；点击升级；观察活动与下一 Turn。
- 输入：target N+1、当前 ETag、持久 idempotency key。
- 预期：活动 Turn 保持 N；下一 Turn N+1；override/clear 保留、inherit 更新；无效 target 原子失败。
- 证据：`BC-05/{before,active,next,error}.png`、revision transcript。
- 失败：自动升级或活动 Turn 热切换为 `fail`。

## BC-06：流式刷新与 cursor（`AC-7`, `AC-8`）

- 前置：受控流 fixture；另 seed `cursor_expired`。
- 操作：记录 cursor K、刷新、等待终态；再用未知 cursor。
- 输入：含 text/usage/artifact/terminal 与 persistent/live 重叠。
- 预期：只补发 K 后事件，各类计数一次；未知 cursor 显示恢复入口，不显示成功。
- 证据：`BC-06/{before,after,expired}.png`、SSE JSONL、计数 JSON。
- 失败：重复、丢失或错误成功态为 `fail`。

## BC-07：键盘、IME 与窄屏（`AC-8`）

- 前置：seed `create_success`；中文拼音输入法；viewport `1440x900`、`1024x768`。
- 操作：composition 中 Enter、compositionend 后 Enter、busy 时重复 Enter/点击；Tab/Shift+Tab；长名称/operation/error。
- 输入：中文文本和超长安全 fixture。
- 预期：composition 不提交，结束后一次；busy 只一 operation；焦点可见；无重叠/横向溢出，主操作可达。
- 证据：`BC-07/{desktop,narrow,ime-steps}.png`、call-count、OS/browser/IME 版本。
- 失败：重复提交、不可达操作或布局遮挡为 `fail`。

## BC-08：身份与缓存隔离（`AC-6`, `AC-8`）

- 前置：seed `slow_scope_switch`；两个用户/Agent/region fixture。
- 操作：延迟旧请求时切换 scope，释放 barrier，检查页面与缓存；执行 denied 请求。
- 输入：相同资源 ID、不同 principal/scope。
- 预期：旧响应不覆盖；缓存隔离；denied 不泄露存在性、ID 或 Secret。
- 证据：`BC-08/{before,after,denied}.png`、storage、network、call-count。
- 失败：跨 scope 数据或 Secret 泄漏为阻断。

## BC-09：暂停、恢复与显式续跑（`AC-5`, `AC-8`）

- 前置：seed `turn_lifecycle`，包含 primary + 两 worker、部分/完整 ACK、可恢复和 new-turn-required fixture。
- 操作：依次触发 pause、释放一个/全部 participant barrier、resume；再 seed 超时状态并点击 continue；刷新和轮询超时期间观察 call-count。
- 输入：同一 Session/Turn、稳定 control/continue idempotency key。
- 预期：`running -> pausing -> paused -> resuming -> running`；部分 ACK 不显示 paused；new-turn-required 只展示显式继续；刷新/轮询超时不自动创建 Turn；重复 continue 只产生一个 linked Turn。
- 证据：`BC-09/{running,partial,paused,resumed,continue}.png`、control/continue network、participant/call-count JSON。
- 失败：误报 paused、自动 continue 或重复 linked Turn 为阻断。

## 2. 准出

BC-01～BC-09 全部 pass，console 无未处理 error；每项执行 `snapshot -a`、`console --errors`、`network` 并保存到 `evidence/browser/<run-id>/<case-id>/`。切片可先执行自己的 BC 子集，但只有 S5 全量回归可标记 `VC-17=pass`。gstack/Chromium 或 scenario harness 不可用则 `VC-17/AC-8=blocked`，Node tests 不替代。结束后调用 reset，分别用 A/B 专属 state file执行 `stop`，停止 fixture 服务，删除两个 state file 和 token file，并确认测试资源为零。
