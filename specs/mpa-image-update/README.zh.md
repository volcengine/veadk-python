# MPA 镜像管理

[English](README.md)

组件 ID：mpa-image-update。修订：2026-10-22。状态：active。

## 职责和接口

Studio 提供 GET /web/mpa-images/{runtime_id}/{component}、GET .../versions、GET .../latest-preview?revision=... 和 POST ...；component 仅为 runtime 或 worker。全部接口要求 Agent 管理权限、重新读取的所有者/管理员 Runtime 授权（不使用共享连接回退）、有效供应商区域和 MPA 类型。Runtime 只指向授权 RuntimeId。Worker 只指向 Runtime.ToolId / AGENTKIT_TOOL_ID / 部署记录 worker_id 一致的绑定，要求可证明的托管归属标签、项目匹配，且无其他 Runtime/注册记录引用。

GET 详情只返回 component、resourceId、currentImage、status、repository、revision、canUpdate、reason、operation，不返回凭据/环境变量。revision 对新读取的身份、绑定、镜像、状态求哈希。POST 仅接受 {tag, revision}、{image, revision} 或 {tag:latest, revision, selection:{image,digest}}；同时提供/均未提供来源或其他来源附带 selection 时拒绝；拒绝相同目标和过期修订。Runtime 只发送 RuntimeId、ArtifactType、ArtifactUrl、ReleaseEnable=true。对应固定公共仓库使用 public_image，自定义手填镜像使用 image。Worker 只发送 ToolId、ImageUrl。绝不自动更新另一组件。

## 目录和限制

volcengine 使用 agentkit-platform-2112682748-cn-beijing.cr.volces.com/mpa；byteplus 使用 agentkit-platform-3001037806-ap-southeast-1.cr.bytepluses.com/mpa。runtime 后缀为 mpa_agent；worker 后缀为 mpa_codex_worker。公共目录不接受任意仓库输入。OCI 每页最多 100 标签，游标为校验后的末标签。界面提供版本选择和加载更多，不再显示搜索框。不虚构发布时间或时间排序。HTTP 超时 12 秒，整个目录操作 25 秒，响应上限 1 MiB，禁止重定向。匿名令牌请求只指向固定仓库的 /service/token 和预期 service/scope；忽略不可信 challenge realm 和 Link 主机。校验 JSON 结构、标签、分页前进。公共标签写入前验证目标 manifest 存在；手填地址写入不会由 Studio 请求镜像仓库。

## 状态和并发

复用托管部署注册表账号/区域锁，串行化镜像写入与部署/删除。pending/deleting 部署拒绝写入。image_updates.runtime 和 image_updates.worker 分别在云写入前持久化目标及阶段。Update 应答只表示已提交，不表示健康。读取到目标及可用状态后将活动意图核对为 configured。明确云拒绝时清除活动意图；超时/传输/5xx/提交中断保留 uncertain。绝不自动重试云写入。浏览器读取取消/迟到响应不能改变其他 Agent/组件。提交后即使客户端断连，服务端操作仍持锁继续；进程中断后意图仍在注册表。部署/删除拒绝活动镜像意图。创建哈希不变，因为此流程不重新创建镜像资源。

## 失败和兼容

返回安全原因码 forbidden、invalid_request、invalid_image、stale、busy、ownership、missing_worker、read_failed、catalog_failed、latest_resolution_failed、rejected、unchanged、not_found、outcome_unknown，不返回原始云响应。云权限错误保持权限错误。共享或归属不可证明 Worker 只读并解释原因。已有沙箱会话可能保留旧 Worker 镜像；新建会话使用更新模板。Runtime 请求立即发布，不承诺应用健康。不改变 SDK/配置/代码生成/公共会话契约。自动测试不包含真实云写入。

相关设计：[独立更新](../../prd-spec/features/mpa-image-update/2026-10-22-independent-images.zh.md)。

## 契约验证

| 契约 | 保证 | 验证 |
| --- | --- | --- |
| CON-IMAGE-ISOLATION | 独立请求和导航 | tests/cli/test_mpa_images.py; frontend/tests/mpaImages.test.tsx; frontend/tests/mpaBasicDetails.test.tsx |
| CON-IMAGE-CATALOG | 固定供应商、有界匿名 OCI 读取 | tests/cli/test_mpa_images.py; 公共只读验证 |
| CON-IMAGE-OWNERSHIP | 新读取的归属、修订和共享资源保护 | tests/cli/test_mpa_images.py; tests/cli/test_frontend_runtime_proxy.py |
| CON-IMAGE-OUTCOME | 持久化意图和禁止盲目重试 | tests/cli/test_mpa_images.py; tests/integrations/mpa_managed/test_deletion.py |
| CON-IMAGE-SOURCE | 手填/公共来源互斥、格式校验、禁止任意主机请求 | tests/cli/test_mpa_images.py; frontend/tests/mpaImages.test.tsx |
| CON-IMAGE-LATEST | 同仓库已有版本、保存摘要复验、隔离创建状态 | tests/cli/test_mpa_images.py; tests/integrations/mpa_managed/test_image_snapshot.py; frontend/tests/mpaImages.test.tsx |
| CON-IMAGE-UI | 加载/错误/取消/键盘/窄窗口 | frontend/tests/mpaImages.test.tsx; 模拟浏览器验证 |

## 手填来源：CON-IMAGE-SOURCE

[手填镜像来源设计](../../prd-spec/features/mpa-image-update/2026-10-22-manual-image-source.zh.md)。搜索框改为完整镜像引用，与公共标签选择二选一；最近一次显式输入仅清除当前组件的另一来源。POST 扩展为严格 {image, revision} 或兼容的 {tag, revision}。手填格式校验不得导致 Studio 请求任意仓库主机。目录加载失败时，有效手填目标仍可更新。Runtime 自定义镜像使用 ArtifactType=image，匹配固定公共仓库的镜像使用 public_image；Worker 仍只发送 ImageUrl。保留现有授权、归属、过期修订和持久化意图规则。手填引用可使用其他仓库。格式要求为显式仓库主机、至少一级仓库路径和必填标签，最长 2048 字符，DNS 主机及路径小写，可选端口为 1–65535；禁止协议、内嵌凭据、空白、查询、片段和摘要。显式主机包含点或端口，或为 localhost。界面在提交前去除首尾空白；API 仅接受规范引用。拉取权限和镜像兼容性由 AgentKit 使用现有权限验证。刷新公共版本保留手填内容，目录加载/报错不阻止手填提交。单纯输入不会触发更新。

## latest 版本解析：CON-IMAGE-LATEST

[latest 更新设计](../../prd-spec/features/mpa-image-update/2026-10-22-latest-update-snapshots.zh.md)。公共 latest 更新在国内/BytePlus Runtime/Worker 四种组合中复用 managed.image_snapshot.snapshot_image，继续强制仅 MPA 授权。只读 GET .../latest-preview?revision=... 在部署锁外解析，重查资源身份后返回 {component, revision, requestedImage, image, digest}。确认框显示该目标；tag=latest 请求可携带 selection={image,digest}，不重读 latest 地重新验证。旧 latest 请求由服务端解析。只在所选组件更新意图保存实际目标、requestedImage、digest；创建 image_snapshots 不变。固定标签及手填保持原行为。无匹配、内容变化、超时或元数据过期时不写入。预览查询失败使用 latest_resolution_failed，不表示云写入结果未知。关闭取消浏览器预览并丢弃迟到结果；加载/错误期间禁用确认。预览截止时间为 180 秒。

可选 selection 必须严格包含 image 和 digest：对应固定仓库的非 latest 标签，以及小写 sha256 和 64 位十六进制摘要。格式不合法时在请求仓库前返回 invalid_request。只读预览要求非空且最长 128 字符的 revision。MPA 镜像 POST 与 latest 预览的浏览器截止时间为 180 秒；其他镜像读取维持 30 秒。上游解析器保留 120 秒发现预算、有界响应及分页。后端预览截止时间为 180 秒；取消后仍在执行的线程可完成只读仓库请求，不产生云写入。
