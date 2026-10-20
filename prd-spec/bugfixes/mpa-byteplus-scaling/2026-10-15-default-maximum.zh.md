# BytePlus MPA 最大实例数默认设为 10

[English](2026-10-15-default-maximum.md)

日期：2026-10-15。范围：仅 Studio MPA 创建。授权：用户要求将海外 BytePlus 最大实例数改为 10。状态：已实现并完成本地验证。

## 证据、需求与设计

创建弹窗在新输入、缺少该值的可编辑草稿、数字编辑缓冲、新请求重置及本地化帮助中写死 20。FR-1：使用已有可信 cloudProvider 属性，为 BytePlus 选择 10，为火山保留 20。FR-2：保留显式草稿修改和已提交请求的数值，包括旧已提交请求省略字段的情况；通过已有 maxInstance API 字段传递数字。FR-3：帮助文字插入对应提供商的默认值，重新生成 WebUI 产物。

复用现有数字输入和校验。此次改变默认扩容上限，不是强制上限或立即分配的实例数。不修改后端/YAML/CLI 配置默认值、最小实例数、并发、通用智能体创建或已部署 Runtime 设置。未授权云端操作、提交或推送。现有 CON-21 扩容契约仅需在双语文档中说明分提供商默认值。

## 审查、任务与验收

直接设计审查（review-spec 不可用）：已检查提供商选择、请求身份保留、旧字段省略、本地化及不变的部署映射，无阻塞项。用户已明确要求此范围的默认值修改。T-1：先写 BytePlus 新请求提交、草稿恢复、新请求重置和不可变重试的失败 React 测试。T-2：实现分提供商默认值和本地化帮助。T-3：执行前端测试、生产构建、国际化/产物检查、已有后端扩容定向测试及适度浏览器验证。验收：BytePlus 新请求提交 10；火山仍为 20；显式/旧重试输入保持原样；构建产物与源码一致。不改变组件归属或 API/数据结构。

## 验证

- pass：先执行失败回归，两个新增场景因预期 10、实际 20 而失败；三个显式值/旧请求场景原本已通过。
- pass：`npm --prefix frontend test`，1,389 项 Node 测试、116 项组件测试通过，包含全部五项新增场景。
- pass：`uv run --extra dev pytest -q tests/integrations/mpa_managed/test_creation_scaling.py`，20 项通过；没有后端源码改动。
- pass：`npm --prefix frontend run build`，TypeScript、应用及 widget 生产构建通过。
- pass：`npm --prefix frontend run check:i18n`、`npm --prefix frontend run test:webui-assets`，113 个产物文件、350 个内部引用通过。
- pass：临时本地服务使用真实 React 弹窗与隔离模拟 API 完成浏览器验证：BytePlus 输入/帮助为 10，提交 maxInstance 为 10，新请求重置为 10，拒绝 0；火山输入/帮助仍为 20。临时 fixture、服务和标签页均已清理；没有真实云端创建。
- pass：`git diff --check`。仅前端改动；Python Ruff/Pyright 和 harness/sidecar smoke 为 not_applicable。
- not_run：完整 Python 回归（仅前端默认值，已有扩容测试覆盖未改动的后端映射）、真实云端扩缩容、提交及推送（未请求）。

- pass：`uv run --extra dev pre-commit run --all-files`，格式、密钥扫描及依赖策略检查通过。
