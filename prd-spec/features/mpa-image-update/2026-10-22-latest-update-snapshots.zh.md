# MPA 独立镜像更新解析 latest

[English](2026-10-22-latest-update-snapshots.md)

变更 ID：mpa-latest-image-update。创建/修订：2026-10-22。状态：implemented。
前序：[手填/公共来源二选一](2026-10-22-manual-image-source.zh.md)。
组件：[MPA 镜像管理](../../../specs/mpa-image-update/README.zh.md)，CON-IMAGE-LATEST。
上游归属：[只读 latest 解析](../../bugfixes/studio-latest-image-refresh/2026-10-21-readonly-tag-resolution.zh.md)。

## 背景和证据

AgentWorkspace 的 imagesAvailable 要求 agentCategory=mpa；_authorize_mpa_image 在进入管理作用域前拒绝普通智能体。目录已分别为 Volcengine、BytePlus 的 Runtime、Worker 选择对应仓库。ImageManager.update 当前仅校验字面标签后提交 repository:latest，尚未使用 managed/image_snapshot.py 的上游 snapshot_image。该解析器匿名比对 latest manifest 字节及 SHA-256，匹配同仓库已有非 latest 标签，或仅验证保存的选择而不重读 latest。其部署封装 pin_studio_images 更新创建用 image_snapshots 及两个资源，独立镜像更新不得调用该封装。

## 目标、非目标和场景

FR-1：保持仅 MPA 的界面和后端鉴权。普通智能体创建/更新路径、导航、请求及依赖不变，同时测试 API 拒绝和导航隐藏。
FR-2：国内与 BytePlus 的 Runtime、Worker 四种组合均支持，且使用各自固定公共仓库。不切换供应商或推断其他云身份。
FR-3：公共标签 latest 复用上游 snapshot_image。确认前解析出同仓库已有版本和摘要，展示真实目标；提交时重新验证所选版本及摘要，不跟随后续变化的 latest。不新增仓库写入、标签发布或镜像复制。
FR-4：无匹配版本、所选内容被覆盖/删除、仓库响应非法、超时和权限失败时不写云，显示安全且可操作的错误。允许只读预览重试，不自动重试写入。关闭或切换时取消浏览器读取，忽略迟到预览。
FR-5：保留 Runtime/Worker 独立确认、请求和持久化意图。在所选组件更新意图中保存请求的 latest、所选镜像及摘要；不覆盖创建 image_snapshots 或另一组件意图。现有归属、修订、不确定结果和沙箱会话语义不变。
FR-6：固定公共标签和手填镜像保持当前行为。手填地址（包括手填 latest 引用）不会让 Studio 请求任意仓库。兼容既有 {tag, revision} 更新 API；未提供预览选择的旧 latest 请求在服务端完成解析。

选择某公共组件的 latest 后，确认框显示匹配版本/摘要；用户确认后仅该组件使用校验过的版本更新。预览后 latest 移动不改变目标。所选版本被覆盖/删除时零写入。普通智能体不能访问详情、版本、latest 预览或更新接口。四种供应商/组件组合均指向正确仓库。

## 设计和契约影响

新增只读 GET /web/mpa-images/{runtime_id}/{component}/latest-preview?revision=...，使用同一管理/所有者/MPA 授权及新读取的修订/归属检查。在账号/区域部署锁之外解析，再次持锁重新核对资源，返回 {component, revision, requestedImage, image, digest}。不持久化预览选择；现有只读元数据核对仍可结束已经观察到完成的操作。

通过 asyncio.to_thread 和仅含 provider 的对象复用 snapshot_image，不传云凭据。保持其 HTTP 校验、匿名鉴权、分页、摘要验证和限制不变。不调用 pin_studio_images，后者维护创建状态和两个组件。GET 预览前后端有界等待 180 秒；取消后线程可能完成有界仓库读取，但不能写云或更新意图。

公共更新请求仅在 tag=latest 时允许可选 selection={image,digest}，严格校验来源联合类型，手填或固定标签携带 selection 时拒绝。已有更新锁内通过 snapshot_image(selection=...) 重新验证所选内容。旧 latest 请求无 selection 时先解析并验证再提交。两个来源均保留新读取的修订检查。解析后目标与当前相同时拒绝更新；当前字面引用为 repository:latest 时仍允许打开 latest 预览。提交前保存所选目标、摘要和 requestedImage 诊断信息。云结果不确定时保留意图，阻止重复写入。

只有 latest 确认路径引入预览状态。在既有 ModalButton 内显示加载、安全错误和只读重试；目标验证完成前禁用确认。目标与当前镜像配置相同时说明无需变更并禁用提交。关闭、切换来源、刷新或切换 Agent 均使预览失效，迟到结果不能覆盖当前目标。固定标签/手填界面及请求不变。API 客户端和解析器类型放在 src/adk，仅需要解析的 MPA 镜像操作延长截止时间。不改变 Python 公共 SDK 签名或依赖元数据。

## 任务和影响文件

T-1 / FR-1,2：扩展现有导航/路由集成回归，覆盖普通智能体拒绝及四种供应商/组件组合。
T-2 / FR-3..6：在 frontend/server/mpa_images.py 增加解析适配器、只读预览、来源联合扩展、所选标签校验和更新意图证据；复用 managed/image_snapshot.py，不修改创建封装及其契约。
T-3 / FR-3,4,6：扩展 frontend/src/adk/mpaImages.ts、client.ts 中的 requestMpaImage；MpaImageUpdates.tsx 接入预览加载/错误/重试/取消及实际目标展示，更新双语文案。
T-4：先写回归覆盖原样提交 latest、摘要变化、latest 移动、解析失败、不确定结果及创建状态/另一组件保留；同步双语组件/用户文档、构建资源及验证记录。

## 验证和验收

AC-1：普通智能体没有镜像入口，全部镜像接口拒绝访问且不解析、不写入。
AC-2：国内/BP Runtime/Worker latest 目标均匹配对应公共仓库并复用现有解析器。
AC-3：确认框展示匹配的已有版本；校验所选内容时忽略 latest 移动；解析失败、内容改变/删除或元数据过期时零写入。
AC-4：不修改创建 image_snapshots 或另一组件；固定标签/手填行为和旧 tag 请求兼容。不确定写入在核对前继续禁止重复。
AC-5：记录包含 tests/cli/test_mpa_images.py、tests/cli/test_frontend_runtime_proxy.py、tests/integrations/mpa_managed/test_image_snapshot.py 的目标 Python 测试、修改文件 Ruff/Pyright、npm --prefix frontend test、npm --prefix frontend run build -- --emptyOutDir false、i18n/资源检查、模拟浏览器加载/错误/重试/取消/键盘/窄窗口、双语链接/空白及范围密钥检查。不授权真实云写入。

## 风险和评审

仓库读取可能耗时，预览发现阶段不能占用部署锁。保留现有解析器限制；取消后正在进行的读取可能继续，但不能产生写入副作用。仍依赖发布方保留且不覆盖标签；摘要验证可检测变化，但不能使可变标签不可变。延长等待仅限 MPA 镜像操作。已有云启动环境/启用问题不属于本轮，不自动重启 Studio 或改选账号。

2026-10-22：用户要求仅 MPA、两个供应商及复用创建 latest 优化。未安装 review-spec，已直接检查归属边界、匿名读取、禁止任意手填主机请求、旧 API 兼容、准确目标确认、取消、保存意图及双语等价。用户明确批准确认前预览、两个供应商、仅 MPA 范围及独立更新。评审阻塞已解决。已按此批准实现；未授权提交、推送或云写入。


## 交付审查和验证证据

2026-10-22，HEAD 33671a15 加本地 MPA 镜像差异，已 rebase 至 upstream/main cb9975df。T-1–T-4、AC-1–AC-5 均由本地实现及模拟验证满足。直接代码审查覆盖来源校验、供应商/组件仓库隔离、发现前后归属和修订、发现期间不占部署锁、不写创建状态、已选版本复验、取消/迟到读取及未知写入阻塞。无阻塞审查项。手填和固定标签维持原路径。本扩展未修改上游解析器及普通智能体生产代码。

| 需求 / 验收 | 命令或流程 | 结果 |
| --- | --- | --- |
| FR-1..6 / AC-1..4 | 测试先行：tests/cli/test_mpa_images.py 和 frontend/tests/mpaImages.test.tsx | pass：预期红灯基线为 Python 9 失败/64 通过、UI 5 失败/30 通过；实现后均通过。 |
| FR-1..6 / AC-1..4 | uv run --extra dev pytest -n 2 tests/integrations/mpa_managed tests/cli/test_mpa_images.py tests/cli/test_frontend_runtime_proxy.py tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py tests/test_mpa_collaborator_proxy_policy.py tests/skills/test_skill_telemetry.py tests/test_harness_sidecar_release_gate.py tests/test_studio_release_workflow.py -q | pass：1613 项，选择两个 worker 限制本机资源消耗。首次扩大运行因新增供应商用例未模拟 TAGApi 而有一个读取超时；补齐隔离后重跑通过，未发生真实云写入。 |
| FR-3,4,6 / AC-3..5 | npm --prefix frontend test | pass：1389 项 Node、234 项 Vitest，包括手填 IME/Enter、过期响应、独立写入及 latest 预览状态。 |
| FR-3,4 / AC-5 | npm --prefix frontend run build -- --emptyOutDir false; npm --prefix frontend run check:i18n; npm --prefix frontend run test:webui-assets | pass：TypeScript、主应用和嵌入组件构建；2 语言/23 命名空间；239 文件/1031 引用。保留既有包体积建议。保留旧资源，兼容运行中服务缓存的引用。 |
| AC-5 | uv run --extra dev pre-commit run ruff-check --files frontend/server/mpa_images.py tests/cli/test_mpa_images.py tests/cli/test_frontend_runtime_proxy.py；通过相同 hook 命令对 mpa_images.py、test_mpa_images.py 运行 ruff-format | pass。 |
| AC-5 | Pyright 使用仓库 .venv/bin/python 检查 frontend/server/mpa_images.py 和 tests/cli/test_mpa_images.py | pass：0 错误。 |
| AC-5 | Pyright 检查 tests/cli/test_frontend_runtime_proxy.py，并与保留的修改前文件对比 | fail：两个副本均为相同的 20 条既有诊断；新增诊断 0，修改的镜像路由用例无诊断。未清理无关类型问题。 |
| FR-3,4 / AC-3,5 | 真实 IAB 浏览器访问临时 Vite 页面，仅模拟镜像 API | pass：国内 Runtime 加载/实际版本/摘要、BP Worker 失败/只读重试/独立已选标签请求、慢读取中取消、重开、Tab/Escape/焦点返回，以及 390px 地址换行/对话框内容滚动/固定操作栏。仅模拟提交。临时页面、标签和 Vite 进程已清理。截图 /tmp/veadk-mpa-latest-confirmation.png；窄窗口 /tmp/veadk-mpa-latest-narrow.png。 |
| AC-5 | 双语契约/标识符/相对链接审查、git diff --check、使用 .gitleaks.toml 的范围 gitleaks detect --no-git | pass。密钥扫描遵循仓库排除规则；未加入真实凭据或原始生产日志。 |
| AC-5 | 真实云更新、部署及实际账号冒烟 | not_run：未获授权。Studio 重启/启用为 not_run：保留原启动环境，现有服务继续运行。全量 pre-commit --all-files 和全仓库回归为 not_run：未请求提交，采用受影响范围回归和检查。Codex 进程冒烟及 sidecar 覆盖为 not_applicable：未改其契约。 |

启用方式：使用原云凭据/环境重启 Studio，并刷新浏览器加载新后端和构建资源。本实现任务未提交、推送、发布或更新云资源。可变的已选标签仍依赖发布方保留；提交会在派发前复验所选内容，但不能令标签不可变。


## 已授权 Git 交付检查

2026-10-22：用户随后授权提交并推送本地修改。本节覆盖此前 Git 检查为 not_run 的记录，范围是 feat/from-upstream-main-20261020 分支、HEAD 33671a15 上暂存的 MPA 协作及镜像更新改动。已 fetch origin/upstream 并运行 git rebase upstream/main：当前已基于 cb9975df，无需新增同步。暂存前备份并完整恢复原有 193 个变更路径。将意外遗漏的 27 个可选平台 lockfile 条目恢复为现有 HEAD 内容，依赖版本不变。Ruff 格式化了两个已修改的测试文件。

- pass：uv run --extra dev pre-commit run --all-files（Ruff 检查/格式、硬编码密钥扫描、依赖策略和 YAML 密钥扫描）。
- fail（既有问题）：uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"：7855 通过、53 跳过、4 xfailed、1 失败，耗时 457.53 秒。失败为 tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes：当前环境将 .md 识别为 application/octet-stream，而非 text/markdown。单独运行未修改的 writer 测试文件同样复现（48 通过、1 失败）；使用相同 Python 环境在 HEAD 的干净 git archive 上也复现相同断言（1 失败）。此问题并非 MPA 回归，已记录，未改动无关产物行为或放宽断言。
- pass：npm --prefix frontend test：1389 项 Node、234 项 Vitest；npm --prefix frontend run build -- --emptyOutDir false；npm --prefix frontend run check:i18n（2 语言、23 命名空间）；npm --prefix frontend run test:webui-assets（114 文件、351 内部引用）。构建输出与暂存资源一致。资源数量与此前保留缓存时的验证不同，是因为当前目录仅保留当前打包集合。
- pass：全部 26 个暂存 PRD/spec 文件的双语配对及相对链接完整性，以及 git diff --cached --check。

已如实披露已知基线失败，未通过跳过测试掩盖问题，未绕过安全 hook，本次 Git 交付不包含真实云更新或 Studio 重启。推送目标为 superops-team/veadk-python 的 feat/from-upstream-main-20261020；此前授权的 rebase 需要针对已获取远端 HEAD 使用 force-with-lease，不使用无约束强制推送。
