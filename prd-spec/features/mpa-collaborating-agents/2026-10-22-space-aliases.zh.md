# 空间共享别名与显式 A2A 提及

Change ID: agentkit-a2a-collaborators | 日期：2026-10-22 | 状态：approved
[English](2026-10-22-space-aliases.md)

## 证据、目标和边界

A2ACenter.tsx 通过选中 Runtime 列出 AgentKit 注册记录；a2aSpace.ts 校验响应。用户明确批准同一空间内全部 MPA 共享别名，以及 @别名/@AgentCardName 派发，不修改 AgentKit。别名存现有共享管理 PostgreSQL，不存浏览器或各 Runtime 业务库。Runtime 负责持久化、解析与授权，Studio 负责编辑反馈。不做自动补全、多目标编排、缓存或云端写入。

## 需求与设计

FR-1：中心每个成员展示可选别名，通过现有管理员 Runtime 代理编辑和清空。复用 Input、FormLabel、Button 与现有表单样式。留空即清空；保留中心原名。说明别名在空间内共享。规范化和唯一性以服务器为准。
FR-2：PUT /api/v1/studio/collaborators/registry/aliases/{agent_id} 输入 {space_id, alias:string|null, revision:int}，返回 {alias,revision}。列表增加 Alias、AliasRevision、AliasAvailable。旧 Runtime 无新字段时编辑不可用。共享 DB/账号配置缺失明确提示，不降级存本地。并发冲突与重名分别提示。写入结果不确定时刷新，不自动重试写入。
FR-3：当前消息前缀 @名称 空白 任务，含空格名称使用 @"name with spaces"，指定唯一目标。Runtime 在绑定空间中对别名和真实 Card.name 取并集，NFKC/casefold 比较，再核对派发 ID。歧义、未找到、目录不完整、多个开头目标或缺任务都不派发。引用/代码、邮箱和普通正文提及不路由。由 Runtime 实现，不由浏览器改写正文。

## 场景、测试与验收

AC-1 / FR-1：给定成员，编辑/清空后展示服务器确认的数据；原名及空间选择保留。测试 frontend/tests/a2aAlias.test.tsx。
AC-2 / FR-2：冲突保留输入，刷新得到最新 revision。取消/卸载后忽略迟到响应；IME 不提前提交；重复点击只发送一次。缺能力禁用并说明。同一测试文件和真实浏览器检查。
AC-3 / FR-3：两个 Runtime 业务库共享一份别名，精确解析及错误目标拒绝由 agentkit-mpa-agent/tests/test_a2a_aliases.py 覆盖。模拟测试不宣称真实远端调用成功。

## 任务、风险和评审

T1 先补失败 UI 测试；T2 类型校验、编辑器和翻译；T3 npm test/build 与浏览器正常/错误/键盘/窄窗检查；T4 同步双语合同及验证。现有 Runtime 代理承载路由，无需修改 Studio Python 服务，无 Agent 生成代码变更、无新增依赖。

Runtime 必须具备共享库配置与权限，旧实例需升级 Runtime。写入不确定先刷新。回滚 UI/Runtime 时保留可选新数据。设计已核对账号空间隔离、CAS 与规范化职责。用户授权是本轮两仓实现请求；@详细语法为本文实现默认值。验证待执行，未获发布部署授权。


## 本地验证

Studio 和 Runtime 已实现。Studio Node tests1389通过、Vitest192通过、生产构建通过。本地浏览器使用真实编辑器/主题、模拟传输，验证保存、清空、重名提示、Escape/焦点恢复及320px窄列。未发布、未调用云端或完成真实模型端到端验收。Runtime证据见 agentkit-mpa-agent/docs/verification/agentkit-a2a-collaborators/alias-verification.md。
