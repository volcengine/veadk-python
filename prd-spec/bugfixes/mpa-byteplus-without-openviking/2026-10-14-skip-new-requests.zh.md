# BytePlus Studio 新请求暂时跳过 OpenViking

[English](2026-10-14-skip-new-requests.md)

变更 ID：mpa-byteplus-without-openviking。日期：2026-10-14。状态：superseded；未进行真实创建/聊天。
组件契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-17/CON-18。

## 证据、目标与范围

一次 BytePlus 任务通过 PG/网络/IM Gateway/Worker 后，在 OV 创建返回 ProductUnordered。用户明确要求跳过 OV，验证其余创建/聊天链路。不购买或开通服务，不修改结算。保留国内自动 OV 及已提交请求身份；不重置不确定建库保护，不修改已有资源绑定。

## 需求与场景

- FR-1：内置 BytePlus 配置不再为新请求声明自动 OV；国内默认仍声明。明确提交过的自动请求和手动配置保留现有支持行为。
- FR-2：服务端不再声明自动 OV 时，新的 BytePlus 表单及恢复的可编辑草稿清除自动选择和手动字段，显示本地化跳过记忆说明，隐藏 OV 输入，不提交自动模式或凭证。已提交自动/手动请求保留原字段和重试意图。
- FR-3：空请求字段使用现有手动禁用路径，清除继承的 OPENVIKING_* 变量，不调用 OV 准备。PG、IAM、网络、APIG/IM Gateway、Worker、Skill Space、Runtime 和通用智能体保持现有契约。
- FR-4：保留三步导航、控制台链接、可选 TOS、取消、新建另一个请求及重试行为。旧失败自动请求需使用现有“新建另一个智能体”，不静默转换。

## 设计、任务与评审

T-1：config.py 只关闭内置 BytePlus 自动能力声明；现有 with_creation_resources 空输入行为负责 Runtime 不注入，不新增 API 枚举或依赖。
T-2：MpaCreateDialog.tsx 仅为可编辑、服务端未声明自动能力的 BytePlus 请求清除 OV 选择，并清除内存中的 Key。跳过状态使用现有段落/布局，不扩展 CSS/图标/组件，增加双语文案。归档自动及非空手动请求保留现有 UI。
T-3：先测试配置默认、国内兼容、旧明确自动请求、恢复可编辑草稿、已提交重试及无 OV Runtime 载荷（含继承配置），再实现。运行 MPA/启动 Python、Ruff/Pyright、前端测试/构建/i18n/产物、隔离浏览器正常/重试/窄窗口/Escape 及密钥扫描。
T-4：同步双语设计、组件契约和模块/前端 README；保留其他任务的本地改动及生成产物。

批准记录：用户在 2026-10-14 明确要求暂时跳过 BytePlus OV，实现前已说明范围。review-spec 不可用，已直接评审边界、缺省字段兼容、已提交请求不可变、密钥排除及双语一致性，无阻塞项。仓库引用的 frontend-design/ui-ux-pro-max 文件在指定路径和已安装技能根中均不可用，使用现有弹窗及 Foundation/SPEC 规则，不引入视觉设计。

## 验收与风险

AC-1（FR-1）：BytePlus 新配置省略自动能力，国内仍声明，旧明确自动请求解析不变。
AC-2（FR-2/FR-4）：新建/恢复可编辑 BytePlus 请求不含 OV 凭证或自动选择，显示跳过说明；重试保留提交身份和值，已有手动恢复仍可用。
AC-3（FR-3）：模拟 BytePlus 准备流程到达 Runtime 时不含 OPENVIKING_*，包括继承模板/参考值，不调用 OV API。
AC-4（全部）：目标/回归/静态/前端/浏览器/密钥检查通过并记录真实证据；真实聊天验证独立，由用户执行。本次实现不重启服务、不修改云资源、不提交或推送。

新智能体没有 OV 长期记忆。本修改不会让旧自动任务以不同请求重试。其他云端/模型/启动错误仍可能影响全链路。

## 验证

2026-10-14，基于 2ffe6e14 的差异。not_run：等待实现检查。真实云端创建/聊天 not_run，未自动追加资源写入。Harness/Codex smoke not_applicable，因为执行协议未改。

2026-10-14 验证完成：pass，失败回归复现 BytePlus 声明自动能力及可编辑旧草稿仍保留自动模式；补充回归复现配置刷新清除已提交意图，均已修复。pass：`uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py`（1,045 项，4 条依赖警告，两个 worker）。pass：`npm --prefix frontend test`（Node 套件及 100 个 React 场景）、生产构建、i18n（2 语言/21 命名空间）、打包产物（113 文件/350 引用）。pass：三个修改 Python 文件通过 Ruff 0.11.12 和显式仓库解释器的 Pyright（零错误/警告）。pass：Chromium 加载真实弹窗，模拟云端 API，验证正常无 OV 提交、同请求重试、可编辑旧草稿、已提交自动恢复、国内自动、窄窗口和 Escape。pass：128 个范围内源码/文档/产物隔离副本通过仓库 Gitleaks hook。浏览器测试入口最初缺少应用主题 token，已导入真实主题并使用相同的浅色默认后完成最终视觉检查。临时浏览器文件/服务已清理。pass：双语标识/链接及差异空白。not_run：全仓/全文件 pre-commit，因为未要求提交，使用目标静态/密钥及受影响回归检查。未新增依赖、修改结算或写云资源，保留已有 package-lock 改动。

已由[恢复 OV 并补齐 Runtime 诊断](../mpa-runtime-diagnostics/2026-10-14-sdk-json-and-restore-ov.zh.md)替代：用户在 OV 开白后明确要求恢复。下方历史证据仅描述临时跳过行为。
