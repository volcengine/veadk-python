# MPA 创建失败详情

## 证据与批准
用户已批准覆盖国内火山和 BytePlus 所有 MPA 创建资源的失败诊断，明确不要建议部分，不改变成功展示、创建、重试或普通智能体行为。当前 RuntimeCloud 仅记录 Runtime 写操作，网络/APIG 包装丢弃标识，runner 最终记录泛化诊断，弹窗只使用 configuration_changed。批准来源：2026-10-20 用户请求。

## 要求
R1：失败任务显示具体操作、本地化安全原因、平台返回的错误码及 Request ID。无建议部分。账号/配置、IAM、PG/数据库、VPC/子网、APIG/IM、沙箱、OV、技能空间、Runtime/就绪等阶段都有安全兜底。
R2：在已有调用边界补诊断，不新增调用、重试、等待，不改变异常、顺序、云端参数、归属检查或恢复决策。异常包装后保留源头诊断。
R3：只有现有启动/恢复流程接受新一轮执行时，才在当前结果中隐藏上一轮诊断。成功及取消不展示诊断；失败页面忽略阶段不匹配和 retrying 事件。
R4：不暴露任意异常正文、SDK 响应体、URL、SQL、模型/PG 密钥或请求体。根据结构化标识显示白名单本地化解释；未知失败明确说明没有可展示的详细安全原因。错误码/Request ID 沿用有界校验。不展示完整原始响应。
R5：支持展开/复制错误详情，提供可访问文本和复制失败反馈，保留成功 DOM 及现有操作/重试行为。普通智能体不使用该组件。

## 设计与影响文件
通过异常上的终态诊断标记无损传递安全信息；已有 report 及重试分类不变。在 managed/runtime.py、network_cloud.py、gateway_cloud.py 补操作记录，保留 PG/IAM/OV/worker/model/APM 已采集的元数据。SQL 错误只做安全分类，不展示 SQL。runner 输出源头诊断或安全兜底；tasks.py 在已有的接受启动事务中推进诊断轮次游标，保留原有最多 100 条的历史记录。MPA 弹窗渲染独立失败组件及双语文案，不修改共用部署 UI。扩展诊断/任务/资源及 MPA 前端测试，重新构建 WebUI。

## 契约评估与设计审查
更新 [Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，补充失败展示/传递及轮次隔离。已有 HTTP 字段继续可选且兼容。SQLite tasks 新增 diagnostic_start_id 列（默认 0），兼容旧记录，不改云端创建契约。直接审查将 R3 从删除诊断记录细化为轮次游标，以保留已有历史记录契约。直接设计审查（review-spec 不可用）：已核对安全、过期轮次、兜底、异常保留、取消、双语一致性及可测试性，无阻塞。特别注意：展示时的配额分类不改变重试分类。

## 非目标与风险
不新增云端排查请求、自动清理或修改重试策略。历史泛化错误无法恢复。未知平台正文不直接展示，避免依赖不可靠的自由文本脱敏。保留所有无关本地改动。

## 任务与验收
1. 先写资源诊断、安全传递、旧轮次隔离、成功态不显示及两种云平台的失败测试。
2. 实现诊断采集及仅失败时渲染。
3. 定向 Python 测试、managed 回归、修改文件 Ruff/Pyright；前端测试/构建/国际化/资源；隔离浏览器错误/成功/复制/窄屏检查。
4. 同步双语文档并记录实测结果。验收：配额/权限/超时及可用标识可见，现有流程测试通过。

## 验证与最终审查
范围：2026-10-20 `feat/from-upstream-main-20261020` 工作区本次失败详情修改；保留无关的协作智能体改动。

- pass：先执行失败的资源/传递和前端测试，再实现并回归。最终定向 Python：`uv run --no-sync --extra dev pytest tests/integrations/mpa_managed/test_creation_failure_details.py tests/integrations/mpa_managed/test_worker_recovery.py tests/integrations/mpa_managed/test_runtime_diagnostics.py -q`（74 项通过）。
- pass：最终加固前串行 managed 回归（1,161 项通过）；最终 `uv run --no-sync --extra dev pytest -n 2 tests/integrations/mpa_managed -q`：1,168 项通过，两个上游 OpenTelemetry 弃用警告；使用两个 worker 控制资源占用。
- pass：`npm --prefix frontend test`（1,389 项 Node 测试、145 项 Vitest 测试），包含通用/MPA 隔离及现有创建/重试测试。
- pass：修改的 Python 文件使用 `uvx --from ruff==0.11.12 ruff check ...` 和 `uvx pyright --pythonpath .venv/bin/python ...`（零错误/警告）。临时工具读取仓库 Python 环境，未修改全局配置；初次工具版本/解释器路径问题已纠正并重跑。
- pass：真实浏览器使用实际失败组件、双语文案和主题的隔离页面，验证配额详情、复制、键盘展开/收起、360px 容器换行、缺少详情、成功/创建中/取消不显示。复制失败及重试恢复另有自动测试。截图 `/tmp/mpa-creation-failure-preview.png` 为模拟数据。临时页面与服务已移除。IME 为 not_applicable：未改输入控件。
- not_run：真实云端创建/重试/部署，无需且未授权云端写操作；平台测试均模拟火山及 BytePlus。全仓无关测试与 pre-commit 为 not_run：未要求提交；定向 managed 回归及前端检查覆盖所改边界。

直接最终审查：未新增云端调用/重试循环或改变参数/顺序，现有异常和重试分类器保持不变；新增元数据只影响诊断。已有 IAM/OV 错误键仍提供具体解释。密钥不进入页面/任务记录。旧轮次诊断保留在有界历史中，仅接受重启后隐藏。成功输出及通用智能体代码未改动。PRD/spec 双语与引用一起核对。


- pass：`npm --prefix frontend run build`、`npm --prefix frontend run check:i18n`（2 种语言 / 22 个命名空间）、`npm --prefix frontend run test:webui-assets`（114 个文件 / 351 处引用）；已重新生成发布 WebUI。
- pass：双语配对/标识/相对链接检查和 `git diff --check`。未提交、推送或部署。
