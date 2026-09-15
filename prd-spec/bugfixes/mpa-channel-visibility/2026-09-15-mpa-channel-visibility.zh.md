# 消息渠道仅对 MPA 显示

[English](2026-09-15-mpa-channel-visibility.md)

日期：2026-09-15。状态：implemented。用户批准：选择 Runtime 后，只有 MPA 智能体大类显示消息渠道。契约：[MPA channels](../../../specs/mpa-channels/README.zh.md)。

## 证据与需求
CloudRuntime 已有 agentCategory，但 MyAgents Runtime 卡片与 App 详情 AgentEntry 丢失该字段；AgentWorkspace 当前对所有类型显示渠道。FR-1：沿 Runtime 列表 → 卡片 → 详情传递 general/mpa 分类。优先使用 Runtime 明确分类，旧响应缺失时使用请求时筛选的类目。FR-2：仅 selectedAgent 具有 Runtime ID 且分类为 mpa 时显示入口/内容；通用/未知/本地智能体隐藏。FR-3：分类变化或不支持的定位请求使 channels 不再适用时回到 basic，不挂载渠道请求。

## 设计与范围
MyAgentCardData.runtime 和 AgentEntry 增加可选分类元数据，MyAgents 和 App 传递，AgentWorkspace 过滤栏目并保护内容渲染。保留用量权限、其他栏目、各渠道行为和二维码生命周期。未知分类默认隐藏。不改变后端/API 鉴权，不执行真实云操作。

## 评审、任务与验收
直接评审（review-spec 不可用）：新增可选元数据保持兼容，列表回退分类绑定请求类目，显式渲染保护避免旧面板挂载。无阻塞；用户请求授权此范围。
T-1/AC-1（FR-1）：元数据传递源码契约测试，覆盖缓存列表映射。
T-2/AC-2（FR-2/3）：执行谓词测试覆盖 MPA/通用/未知/无 Runtime，检查栏目过滤/内容保护/回退；修改上述四个源文件。
T-3/AC-3：定向/前端回归、构建/资源、真实浏览器配模拟 Runtime API 验证分类切换与不支持的栏目定位；同步双语文档和产物。

## 验证与风险
执行日期：2026-09-15；范围：当前未提交的分类传递及栏目可见性差异、对应测试/文档和重建的 WebUI 产物。
- pass：测试先行，实施前回归失败；实施后 `node --test frontend/tests/agentWorkspace.test.mjs` 34 项通过。
- pass：为现有 Runtime 映射断言增加分类参数后，`npm --prefix frontend test` 1208 项通过。
- pass：`npm --prefix frontend run build`；`npm --prefix frontend run test:webui-assets` 校验 104 个文件和 248 个内部引用。仍有既有构建包体积警告。
- pass：真实浏览器运行 AgentWorkspace 并模拟 API，验证 MPA 显示渠道、通用/未知分类隐藏、切换后回到基本信息、切回 MPA 恢复入口。480×850 下 MPA/通用切换也通过。隔离模拟返回的基本信息错误界面符合预期。
- pass：直接实施评审无阻塞；已检查双语文档和范围内差异空白。T-1 至 T-3、AC-1 至 AC-3 完成。
- not_applicable：未修改 Python、IME/输入及渠道绑定/错误/重试行为。不涉及提交，因此未运行提交前同步。
- not_run：真实云端/渠道验证和部署；用户未要求真实操作。
非列表入口缺失分类时有意隐藏渠道，不根据名称/镜像猜测。
