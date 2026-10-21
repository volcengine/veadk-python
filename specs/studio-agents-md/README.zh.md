# Studio MPA AGENTS.md

[English](README.md) · [设计](../../prd-spec/features/studio-agents-md-edit/2026-10-21-studio-agents-md-edit.zh.md)

## 职责和范围

MPA 信息侧栏编辑当前选中 Runtime 的文档。Studio 后端负责鉴权和注入凭据，
Runtime 负责修订存储及 Main/Worker 生效。不新增模型、Skill、MCP、Bot Profile
编辑器、缓存或部署能力。

## 接口与安全

按 Runtime ID 和地域代理 GET/POST `/api/v1/studio/agents-md`。需要 Studio
管理员身份，并通过现有 Runtime 可见性校验。剥离浏览器传入的
`X-MPA-Studio-Key`，仅注入服务端解析的当前 Runtime 密钥；拒绝非规范路径。
密钥不得存入浏览器状态。

GET 返回 `{content: string, revision: integer}`；POST 接受同样结构，仅更新文档，
返回已保存/当前修订。空内容清除自定义指令，最多 40000 字符。并发修改返回
409，凭据错误/缺失为 401/503，无权访问 403，非法输入 422。
旧 Runtime 可能返回 404/405/501；显示升级提示，保留元数据查看能力。

## 交互与状态

复用 ModalLayout、Button、Textarea、ScrollArea 和 Base UI Dialog。打开时读取
持久配置；加载、保存中、内容未变、超限或前次保存结果不明时禁用保存。
清空、放弃编辑需确认，错误保留草稿。冲突时刷新并核对当前修订；网络/5xx
保存异常后需先回读才能重写。防重复提交及中文输入组合过程中提交；卸载时
取消请求并忽略迟到响应。切换 Runtime/地域时侧栏重建。

## 生效配置

进行中的回合保持文档快照；下一轮 Main 使用保存的内容，包括已有会话。清空
移除 Main 自定义部分，保留平台规则。Worker 文件收到快照，但复用中的原生
Worker 线程可能继续使用旧指令。Worker 热更新仍为暂缓项，不属于 Studio 保存
成功能够保证的行为。历史记录保留。接口验证配置传递，而非模型回答的确定性。
直接更新选中 Runtime，不引入 ArkClaw 独立调试/发布双环境。

## 验证

包含 Python 代理鉴权/伪造头测试、Runtime 持久化/CAS/回合快照、前端加载、保存、
错误、清空、IME、取消测试、浏览器检查及生产构建。实际结果和限制见双语设计。
