# 预签名 TOS URL Skill 下载修复

## 背景和证据

`VeSkillRegistry.get_skill()` 会通过 `load_skills_from_cloud()` 刷新 Skill Space 元数据，选中远端 Skill 后调用 `materialize_remote_skill()` 本地物化。对于 legacy AgentKit Skill Space，`_build_skill_from_space_item()` 会把 `TosPath` 映射到 `Skill.path`，把 `BucketName` 映射到 `Skill.bucket_name`。

当前 `_download_legacy_skill_space_skill()` 假设 `Skill.path` 是 `skills/<skill_id>/<version>/<name>.zip` 这类 TOS 对象 key。如果云端 API 在 `TosPath` 中返回完整 HTTPS 预签名 TOS URL，非 Vestack 分支会把这个 URL 当作 object key 传给 `VeTOS.download()`，Vestack 分支则会把它误拆成 legacy 对象路径。针对 `ss-yey3lbgruoq7vcs7xlp4` 的真实验证还显示，sharing bucket 中的 object-key Skill 可能返回 `403 AccessDenied`，但同一 Skill 通过 `GenTempTosObjectDownloadUrlSharing` 可以拿到可用 signed URL。

## 目标

- 当 `TosPath` 是完整预签名 HTTPS TOS ZIP URL 时，普通 Skill Space Skill 可以正常加载。
- 保留可直接读取的 object-key 下载路径，并在直连被拒绝时 fallback 到 sharing signed URL。
- 复用现有归档安全检查：流式大小限制、ZIP 校验、安全解压和 ADK `SKILL.md` 加载校验。
- 除脱敏的合成测试 URL 外，不在错误信息和源码 fixture 中保留 signed URL 内容。

## 非目标

- 不修改 Harness `tos_public_url` 校验。用户传入的 Harness public URL 仍然必须拒绝 TOS 凭证 query 参数。
- 不修改通过 `tos://bucket/prefix/` 加载私有 TOS 目录的逻辑。
- 不修改 `ListSkillsBySpaceId`。

## 场景

1. `ListSkillsBySpaceId` 返回 `BucketName` 加 object-key `TosPath`；可读对象仍然通过 SDK TOS 直连下载。
2. `ListSkillsBySpaceId` 返回 object-key `TosPath`，但 SDK TOS 直连下载被拒绝；materializer 调用 `GenTempTosObjectDownloadUrlSharing`，下载 `Result.SignedUrl` 并加载 Skill。
3. `ListSkillsBySpaceId` 返回 `TosPath=https://bucket.tos-cn-beijing.volces.com/...zip?X-Tos-Signature=...`；materializer 直接下载该 URL 并加载 Skill。
4. signed URL 重定向到非 TOS host，或返回非 ZIP 内容；物化失败关闭。

## 需求

- 只对云端返回的 Skill Space 元数据识别 signed HTTPS TOS ZIP URL。
- 对这条云端返回路径允许 TOS 签名 query key。
- 要求 URL 使用 HTTPS、TOS endpoint host、`.zip` 路径，并且不包含 username/password。
- 下载必须流式执行，并沿用 public TOS ZIP 的 64 MiB 归档大小限制。
- 缓存 key 优先使用 `version_id`；没有版本时，metadata digest 可以包含 URL。
- fallback 过程中不得记录原始 signed URL 或携带凭证的 query string。

## 设计

为云端返回的 signed TOS ZIP URL 增加 materializer 分支。`_build_skill_from_space_item()` 会把 HTTPS TOS ZIP URL 形式的 `TosPath` 识别为 signed URL source。`materialize_remote_skill()` 随后走 signed URL 下载器，而不是 legacy TOS object-key 下载器。

signed URL 下载器应复用 public TOS ZIP 的流式下载实现，但使用允许 TOS 签名 query key 的校验器。Harness `tos_public_url` 继续使用更严格的 public 校验器，仍然拒绝凭证 query key。

对于 legacy object-key 元数据，先保留当前 `VeTOS.download()` 直连尝试。如果直连失败或抛错，则使用 skill id 和 version 调用 `GenTempTosObjectDownloadUrlSharing`，读取 `Result.SignedUrl`，并交给同一个 signed URL 下载器处理。

## 影响文件

- `veadk/skills/utils.py`
- `veadk/skills/materializer.py`
- `tests/skills/test_adk_skill_materializer.py`

## 组件契约评估

不需要更新组件 spec。外部 Skill Space 元数据契约已经允许 `TosPath` 承载 AgentKit 返回的位置；本次只修复本地物化对其中一种返回形态的处理。公开 Python API、Harness 请求 schema 和用户配置均不变化。

## 任务

- 为 `TosPath` 中云端返回的预签名 TOS URL 增加失败回归测试。
- 为 object-key `TosPath` 在 TOS 直连被拒绝后 fallback 到 sharing signed URL 增加失败回归测试。
- 在 Skill 构造时识别 signed TOS URL 元数据。
- 增加 materializer 下载路径，仅对云端返回的 TOS URL 允许签名 query key。
- 复用 signed URL 下载路径处理 sharing signed URL fallback。
- 运行目标 Skill 测试和空白检查。

## 测试

- `uv run --extra dev pytest tests/skills/test_adk_skill_materializer.py`
- `uv run --extra dev pytest tests/skills/test_adk_skill_registry.py tests/skills/test_skill_space_policy.py`
- `git diff --check`

## 风险

- signed URL 的 query 参数包含凭证；日志和错误信息不能回显原始 URL。
- 如果刷新后的 signed URL 改变且没有稳定版本号，URL 可能影响缓存 key。存在 `version_id` 时仍以版本号为准，这一点保持权威。
- sharing signed URL 生成可能因 Skill 后端元数据不完整而失败；这类 Skill 仍然失败关闭，需要单独诊断。

## 验收标准

- `TosPath` 为预签名 HTTPS TOS ZIP URL 的 Skill Space Skill 可以成功下载并加载。
- 现有可读 object-key Skill Space 下载测试仍然通过。
- TOS 直连被拒绝的 object-key Skill Space 下载可以通过 sharing signed URL fallback 加载。
- Harness `tos_public_url` 拒绝签名 query 凭证的测试仍然通过。
- 不提交真实凭证或生产 signed URL。

## 设计评审

当前 checkout 没有仓库本地 `review-spec` skill，因此已执行直接评审。设计边界限定在云端返回元数据，保留 Harness 用户输入校验，对不安全 URL 形态失败关闭，并具备目标回归覆盖。
