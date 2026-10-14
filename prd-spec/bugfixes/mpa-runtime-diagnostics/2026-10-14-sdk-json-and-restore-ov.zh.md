# 解码 Runtime SDK 拒绝元信息并恢复 BytePlus OV

[English](2026-10-14-sdk-json-and-restore-ov.md)

变更 ID：mpa-runtime-json-and-restore-ov。日期：2026-10-14。状态：implemented；真实云端重试待验证。
前置：[Runtime 诊断](2026-10-14-sdk-error-codes.zh.md)和[临时跳过 OV](../mpa-byteplus-without-openviking/2026-10-14-skip-new-requests.zh.md)。
契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-10/CON-17/CON-18。

## 证据、目标与非目标

实际 CreateRuntime 失败仍只留下 provider_error。已安装 SDK 的 Service.json 对非 200 响应抛出 Exception(bytes)，外层包装保留 cause，但没有结构化属性；现有 Runtime 诊断只读取属性。用户现在说明 BytePlus OV 已开白，要求恢复自动 OV。本次授权包含这两项修复，不包含实际云端创建、重启 Studio、提交或推送。通用智能体、国内载荷、IAM、计费、模型默认值、资源绑定和不确定建库保护不在修改范围。

## 需求与场景

- FR-1：直接或包装后的 SDK 拒绝，从属性、HTTP/SDK 结构化响应体，或单个包含 JSON／SDK 字节串表示的有界异常参数提取已验证 errorCode/requestId。最多遍历八个 cause 并防循环；参数／响应体解析上限 65,536 字节／字符。拒绝格式错误、超长、过深及非 JSON 文本；不执行代码，不记录云端 Message、响应体、凭证或 ClientToken。复用 OV 元信息校验／解码方法。
- FR-2：重新抛出同一异常，保留调用次数、取消、载荷、token、分类与重试行为，不增加云端重放。
- FR-3：内置 BytePlus ap-southeast-1 新请求重新声明自动 OV。移除临时跳过专用 UI／文案和清空逻辑。新请求／可编辑草稿选择 auto 且无需手填；已提交的无 OV／自动／手动任务在配置刷新及重试时保留原意图。国内自动流程和不支持自动模式的配置所用手动路径不变。
- FR-4：保留已有 BytePlus 个人版 developer 建库、端点／Key 注入及持久绑定复用。不改写已有任务或云资源。不确定建库继续受保护；账号开白不代表模型凭证及服务一定可用。

## 设计与任务

T-1（FR-1/FR-2）：先在 test_runtime_diagnostics.py 增加失败测试，覆盖包装的 bytes／JSON／字符串表示、HTTP/SDK 响应体、格式错误／危险值／超长／循环、异常身份和单次调用，仅扩展 Runtime 提取方法。
T-2（FR-3/FR-4）：配置回归改为要求 auto，增加已提交无 OV 恢复测试。恢复 config.py 支持提供方的自动默认，仅删除 MpaCreateDialog.tsx／文案中的临时跳过部分，保留 submittedIntent 竞态保护和无关 BytePlus 能力。
T-3：同步双语组件／模块文档，将历史跳过设计标记为被替代。执行目标及 managed/startup Python 回归、Ruff/Pyright、前端测试／构建／国际化／产物、隔离模拟接口的真实浏览器检查、范围内密钥扫描及双语链接／空白检查。保留包括 package-lock 在内的无关改动。

## 评审、风险与验收

用户批准：2026-10-14 明确要求补完整日志及恢复 OV。review-spec 不可用，直接设计评审在限制解析边界、保留原异常和已提交意图后无阻塞。复用现有弹窗／Foundation 样式，不新增视觉组件。引用的 frontend-design/ui-ux-pro-max 技能不可用，直接遵循仓库 SPEC。

AC-1：模拟真实 SDK 形状的异常保留安全 Runtime 标识；禁止的值／文本不进入诊断；原异常／token 和单次调用不变。
AC-2：BytePlus 新请求包含 auto；已提交无 OV 和自动请求在重试／配置刷新时保留身份和模式；国内行为不变。
AC-3：必需检查有实际通过证据，不执行云端变更或服务重启。真实重试由用户另行验证。

解析补充不能恢复历史错误，也不能解释无云端响应的传输错误。已提交无 OV 任务无法通过重试获得 OV，测试 OV 应新建请求。BytePlus 实际开白／模型可用性及 Runtime 拒绝原因仍未验证。

## 验证

2026-10-14，基于 2ffe6e14 的本地差异。not_run：实现检查待执行。not_run：真实云端创建／重试，本次实现不执行云端写操作。not_applicable：harness/Codex smoke，协议未变。全部文件 pre-commit 为 not_run：未要求提交，须执行范围内静态及密钥检查。

2026-10-14 结果（基于 2ffe6e14 的本地差异）：pass，修复前回归复现 11 项失败；Runtime／BytePlus／OV 诊断目标套件 73 项通过，最终 Runtime 单独套件 30 项通过。pass，两个 worker 的 managed/startup 回归 1,075 项（四条依赖警告）。pass，npm --prefix frontend test：Node 套件和 101 项 React 测试；生产构建、国际化（2 种语言／21 个 namespace）、产物（113 个文件／350 个引用）。pass，四个 Python 文件的 Ruff 0.11.12 检查／格式及使用仓库解释器的 Pyright，零错误／警告。pass，内置 Chromium 中用模拟接口验证海外新请求自动提交、原无 OV 重试身份／模式、国内自动展示、420x760 窄窗口及 Escape。浏览器夹具起初使用错误 i18n 导入，验证前已修正；夹具和隔离 Vite 服务已移除。最初一项前端回归误用不存在的刷新按钮，已修正为验证配置加载后的恢复。最初 Pyright 夹具属性错误已通过有类型的 SDK 异常类修正。范围内密钥及双语文档检查待下方补充。not_run：真实云端创建、重启、全部文件 pre-commit／提交／推送，未执行变更。本次修复不增加依赖，也未改动 package-lock。

最终评审：pass，双语需求／契约 ID、相对链接及 git diff 空白检查。pass，在隔离的 106 文件快照上按仓库配置执行 Gitleaks hook。最初扫描遗漏 .gitleaks.toml，将生成的 MarkdownPromptEditor 第三方 anchor.key 代码表达式误报为 generic-api-key；核实为代码后，使用未修改的仓库配置重新检查。现有仓库白名单排除 tests 和编译 WebUI，本次按既有策略扫描源码，未新增绕过规则。未发现源码凭证。浏览器夹具／服务已移除；package-lock 仍保留原有 512 行删除。范围内验收完成，不宣称真实服务商行为已验证。
