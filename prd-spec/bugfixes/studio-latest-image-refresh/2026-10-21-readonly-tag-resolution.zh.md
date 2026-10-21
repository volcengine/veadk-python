# Studio latest 只读标签解析

[English](2026-10-21-readonly-tag-resolution.md)

- 变更 ID：`studio-latest-image-refresh`；修订：2026-10-21。
- 状态：approved；用户已明确要求修改并验证只读匹配方案，授权实现、部署和在线验证。
- 替代[原快照设计](2026-10-20-latest-image-snapshots.zh.md)中的仓库写入部分；既有部署选择和历史验证记录仍有效。
- 组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-1/3/6/8/9。

## 证据与范围

不携带凭据的匿名探针已确认，两个内置公共仓库的 Agent、Worker 均支持仓库范围匿名 pull token、完整标签列表和 manifest digest 精确匹配。BP 匹配项包括 `master-a72afa274fe5-20261020`、`master-31fc42b4c521-20261021-1205`；国内包括 `master-d8665d03578a-20261016`、`master-a63685214d07-20261016`。这证明探测时可读和内容一致，不证明 Runtime 采用情况或仓库强制标签不可变。

原实现要求源仓库写权限，不适用于使用平台公共仓库的普通用户。改为匿名只读选择同仓库已有标签，不新增 CI、镜像搬运、依赖、前端字段、IAM 变更，不修改既有 MPA 或独立 CLI。需要鉴权的私有 latest 仓库不属于公共发现契约；显式固定 tag 保留原行为。

## 需求与设计

- **RO-1：** 读取 latest，校验原始 Docker/OCI manifest 或 index 字节与 `Docker-Content-Digest` 一致；只用 HTTPS GET 和匿名 `repository:<repo>:pull` token 列举标签。绝不读取云凭据、netrc、Docker 配置，并禁用 requests 环境鉴权。认证挑战须为同仓库主机、HTTPS、默认端口，无用户信息及重定向。
- **RO-2：** 先完整读取有界分页再选择。仅接受合法标签名；优先已有 `mpa-sha256-<digest>`，其次按标签字典倒序检查其他非 latest 标签。核验候选 manifest 字节；候选删除（404）可跳过，非法内容、鉴权及传输错误明确失败。采用第一个 digest 精确匹配项。标签不覆盖由发布方保证，不能凭名称宣称不可变。
- **RO-3：** 无匹配版本标签时明确失败；绝不发布标签或静默回退 latest。每次移动 latest，发布方须保留对应的不覆盖版本标签。选择固定的是初次解析时观察到的 latest，其后变化不改变本次部署意图。
- **RO-4：** 保留原生 `image_snapshots.requested/selected` 和既有锁内双镜像持久化。新选择可为校验通过的同仓库任意非 latest 标签，兼容原有 digest 命名快照。重试只读取保存的 tag 并核验 digest；已保存内容变更或缺失时失败，绝不重新选择。保留旧未完成意图拒绝规则以及独立 CLI、固定 tag 兼容性。
- **RO-5：** 单响应限制 1 MiB，枚举限制 20 页 / 1000 个标签项，解析预算 120 秒，在 HTTP 调用前及读取响应块时检查（已在途读取可持续到其有界读取超时）。单请求连接/读取上限为 10/30 秒，或更小的剩余预算。分页必须保持同主机、同仓库 tags-list 路径，只允许 `n`/`last` 参数，无用户信息/片段和循环；非法或跨源链接失败。取消不持久化部分选择，由现有子进程 supervisor 处理终止。错误保持脱敏。

生产模块继续使用 `managed/image_snapshot.py` 以兼容现有接入，service 和原生表结构不变。更新协议测试、双语组件/操作文档、前端操作说明和 PR 描述。保留原快照设计作为历史证据，并明确标为已替代。

## 审查与批准

没有可用 review-spec 技能；改代码前直接审查了公共仓库/普通用户权限边界、匿名 token scope、主机/路径/分页校验、原始 digest 完整性、非法/大响应、超时预算、取消、可变/删除标签、旧持久选择、重试幂等、CLI 隔离、测试映射和双语一致性。用户批准涵盖实现、更新 PR #1178、BP Studio 部署以及新建隔离 MPA 测试。镜像发现不扩大权限、不写仓库。

## 任务、验收与验证

| 需求 | 任务 / 验收 | 验证 | 结果 |
| --- | --- | --- | --- |
| RO-1/2/3/5 | 匿名精确匹配，严格有界 GET 协议，明确失败 | 先写失败回归；模拟 HTTP 协议/安全/预算；真实匿名解析 | pass；证据见下文 |
| RO-4 | 锁内持久化两个选择，兼容新旧保存标签，保留 CLI/固定 tag | managed service/集成和 CLI 回归 | pass；证据见下文 |
| 全部 | 增量覆盖率高于 95%，质量/安全门禁和文档同步 | 定向分支覆盖、managed/CLI 回归、改动文件 Ruff/Pyright、全文件 pre-commit、前端测试/构建 | pass；证据见下文 |
| 全部 | 部署已测源码并创建全新 Studio MPA | 支持的 Studio update、部署模块哈希、页面成功、原生 ready/选中标签、应用就绪、实际 Worker 源码/image ID、有界任务完成 | pending |

## 风险与恢复

读取权限和标签策略可能变化；无匹配项或访问失败必须给出安全诊断，不能继续创建旧版本。有限枚举和时间预算可能拒绝过大或过慢仓库。标签不是密码学不可变，仍需发布方保证不覆盖，重试校验能发现内容变化。需要公共网络出站访问。失败保留云资源和原持久意图，必要时通过支持的发布路径回滚 Studio。不宣称缓存失效，也不宣称修复先前独立收尾异常。未观察到的在线结果保持未验证。

## 2026-10-21 本地及真实匿名验证

改生产代码前，前三个仅 GET 回归在原依赖凭据的实现上失败。更新后 **93 passed**，解析模块行/分支覆盖率 **100%**。相对 origin/main，解析模块及 service 接入新增的 **173/173 个可执行生产代码行**全部覆盖。覆盖执行在 pytest 前预加载 `pydantic_settings` 和 SDK Runtime 类型，规避已有上游导入身份问题，未引入依赖或业务代码绕过。

- pass：`.venv/bin/python -m pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q`，**1266 passed**。
- pass：前端 **118 passed**、生产构建、改动文件 Pyright（0 errors）、全文件 pre-commit（含 Ruff/format/密钥扫描）和 `git diff --check`。
- pass：使用生产解析模块，真实匿名选择及重试校验两个平台的 Agent/Worker；把云凭据入口替换为调用即抛异常的函数。BP 选择已有 digest 命名标签，国内选择上述已有 master 标签。没有创建或修改任何标签；脱敏证据在 Git 外本地保存。
- not_run：更新后的 Studio 部署、全新 MPA/Runtime/Worker 页面验证，观察完成后追加。完整 A2A、Codex/Pi/Harness、国内真实部署、日历和真人 IM 不属于此次有界验证。
