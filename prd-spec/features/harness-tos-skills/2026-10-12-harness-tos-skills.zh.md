# Harness TOS Skills

[English](2026-10-12-harness-tos-skills.md)

## 元数据

| 字段 | 值 |
| --- | --- |
| Change ID | `harness-tos-skills` |
| 创建日期 | 2026-10-12 |
| 状态 | implemented |
| 相关规格 | 不更新组件规格；本变更扩展现有 Harness selected-skill 请求契约，不改变组件职责边界。 |

## 背景和证据

Harness 当前已经支持加载 SkillHub Skill 和 Skill Space Skill。Skill Space 加载最终会通过现有 materializer 下载 TOS 上的 Skill archive，但调用方不能直接提供对象存储 Skill 目录。

目标行为对齐 AWS AgentCore Harness S3 Skills：一个对象存储 URI 指向一个包含 `SKILL.md` 的 Skill 目录；多个 Skill 通过多条 selected-skill entry 表达。

## 目标

- 为 `HarnessSelectedSkill` 增加 `source="tos"`。
- 支持通过 Runtime 云身份读取当前账号 TOS 目录。
- 支持公开读 TOS zip URL，不要求 AK/SK。
- 保持现有 SkillHub 和 Skill Space 行为不变。

## 非目标

- 不做父目录自动发现多个 Skill。
- 不在 Harness 请求中接收明文 AK/SK。
- MVP 不支持跨账号私有 TOS 的 credential reference。

## 需求

| ID | 需求 |
| --- | --- |
| FR-1 | TOS selected Skill 使用 `tos_url="tos://bucket/path/to/skill/"` 时只加载一个 Skill directory，且该 URL 根目录必须直接包含 `SKILL.md` 或 `skill.md`。 |
| FR-2 | 多个 TOS Skill 通过多条 `selected_skills` entry 加载。 |
| FR-3 | 公开读 TOS zip URL 可以加载一个 Skill archive。 |
| FR-4 | 空 URL、bucket 根路径 URL、父目录 URL、不支持的公开 URL、非 TOS host、带凭据的公开 URL，以及跳转到非 TOS host 的公开 URL 必须失败关闭。 |
| FR-5 | TOS 下载失败或 Skill 目录非法时，整个 SkillToolset 构建失败。 |
| FR-6 | 公开 TOS zip 下载、公开 zip 解压和私有 TOS 目录下载必须在 Skill 加载前执行文件/对象数和字节数上限。 |

## 设计

`HarnessSelectedSkill.source` 接受 `tos`，并支持以下两种形式：

```python
HarnessSelectedSkill(source="tos", tos_url="tos://bucket/skills/reporting/", region="cn-beijing")
HarnessSelectedSkill(source="tos", tos_public_url="https://bucket.tos-cn-beijing.volces.com/skills/reporting.zip")
```

多个 Skill 通过多条 entry 表达：

```python
selected_skills=[
    HarnessSelectedSkill(source="tos", tos_url="tos://bucket/skills/reporting/", region="cn-beijing"),
    HarnessSelectedSkill(source="tos", tos_url="tos://bucket/skills/search/", region="cn-beijing"),
]
```

Harness 将其序列化为内部 ref，并在 `build_skill_toolset` 中分发。TOS selected Skill 只使用 `tos_url` 和 `tos_public_url` 作为 locator 字段。materializer 解析 `tos://` URL，通过 `VeTOS` 下载单个目录，校验路径没有逃逸，要求根目录直接包含 `SKILL.md` 或 `skill.md`，再用 ADK 加载。指向包含多个子 Skill 的父目录 URL 会被拒绝，不会自动选择某个子目录。公开 URL 不允许包含 userinfo 或 TOS 签名 query 凭据。公开 URL 按 zip archive 流式下载，每一跳 redirect 在请求前都必须指向 TOS host，并且现有安全解压路径会对公开 TOS archive 执行展开后的文件数和未压缩字节数上限。

被拒绝的 TOS ref 在包装成 Harness skill-load 错误时会脱敏，避免无效 userinfo 或签名 query 值返回给调用方，或被 Harness 错误路径写入日志。

## 任务

| ID | 任务 |
| --- | --- |
| T-1 | 增加 TOS selected Skill schema 字段和校验。 |
| T-2 | 增加 TOS directory 和 public zip materializer，包括严格根 manifest 校验和资源上限。 |
| T-3 | 将 Harness SkillToolset 构建接入 TOS refs。 |
| T-4 | 增加聚焦的契约测试和 materializer 测试。 |

## 验证

| 需求 | 命令 | 结果 |
| --- | --- | --- |
| FR-1..FR-6 | `uv run --extra dev pytest tests/skills/test_adk_skill_materializer.py tests/test_ve_tos.py::test_download_can_propagate_tos_error tests/test_ve_tos.py::test_download_rejects_object_over_byte_limit tests/test_ve_tos.py::test_download_directory_rejects_too_many_objects tests/test_ve_tos.py::test_download_directory_rejects_total_bytes_from_listing -q` | pass，2026-10-12 执行，30 passed |
| FR-4..FR-5 | `uv run --extra dev pytest tests/cloud/test_harness_app_contract.py::TestHarnessOverrides::test_tos_selected_skill_rejects_public_url_userinfo tests/cloud/test_harness_app_contract.py::TestHarnessOverrides::test_tos_selected_skill_rejects_public_url_signature_query tests/cloud/test_harness_skill_download.py::test_build_skill_toolset_redacts_tos_ref_on_error -q` | pass，2026-10-13 执行，3 passed |
| FR-1..FR-6 | `uv run --extra dev pytest tests/cloud/test_harness_skill_download.py::test_build_skill_toolset_loads_tos_skill_uri tests/cloud/test_harness_skill_download.py::test_build_skill_toolset_loads_multiple_tos_entries -q` | pass，2026-10-12 执行，2 passed |
| FR-1..FR-6 | `uv run --extra dev ruff check veadk/skills/materializer.py veadk/integrations/ve_tos/ve_tos.py tests/skills/test_adk_skill_materializer.py tests/test_ve_tos.py` | pass，2026-10-12 执行 |
| FR-1..FR-6 | `uv run --extra dev pre-commit run --all-files` | pass，2026-10-12 执行 |
| FR-1..FR-6 | `git diff --check` | pass，2026-10-12 执行 |
| FR-1..FR-6 | `uv run --extra dev pytest tests/skills/test_adk_skill_materializer.py tests/test_ve_tos.py -q` | fail，现有环境限制：`tests/test_ve_tos.py` 中 4 个 async 测试需要 pytest async 插件；TOS 聚焦测试已通过。 |

## 风险

- 真实 TOS IAM 行为需要额外的云端 smoke 验证，离线单测无法证明。
- 公开目录 URL 仍不纳入范围，因为对象存储没有稳定通用的 HTTP 目录清单契约。
