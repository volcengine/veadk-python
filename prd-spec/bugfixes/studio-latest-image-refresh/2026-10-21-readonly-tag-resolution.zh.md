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
| 全部 | 部署已测源码并创建全新 Studio MPA | 支持的 Studio update、部署模块哈希、页面成功、原生 ready/选中标签、应用就绪、实际 Worker 源码/image ID、有界任务完成 | 部署/创建/镜像采用及新会话冒烟 pass；首次功能失败保留如下 |

## 风险与恢复

读取权限和标签策略可能变化；无匹配项或访问失败必须给出安全诊断，不能继续创建旧版本。有限枚举和时间预算可能拒绝过大或过慢仓库。标签不是密码学不可变，仍需发布方保证不覆盖，重试校验能发现内容变化。需要公共网络出站访问；发现采用直连 HTTPS，明确不读取环境代理和 netrc。失败保留云资源和原持久意图，必要时通过支持的发布路径回滚 Studio。不宣称缓存失效，也不宣称修复先前独立收尾异常。未观察到的在线结果保持未验证。

## 2026-10-21 本地及真实匿名验证

改生产代码前，前三个仅 GET 回归在原依赖凭据的实现上失败。更新后 **93 passed**，解析模块行/分支覆盖率 **100%**。相对 origin/main，解析模块及 service 接入新增的 **173/173 个可执行生产代码行**全部覆盖。覆盖执行在 pytest 前预加载 `pydantic_settings` 和 SDK Runtime 类型，规避已有上游导入身份问题，未引入依赖或业务代码绕过。

- pass：`.venv/bin/python -m pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q`，**1266 passed**。
- pass：前端 **118 passed**、生产构建、改动文件 Pyright（0 errors）、全文件 pre-commit（含 Ruff/format/密钥扫描）和 `git diff --check`。
- pass：使用生产解析模块，真实匿名选择及重试校验两个平台的 Agent/Worker；把云凭据入口替换为调用即抛异常的函数。BP 选择已有 digest 命名标签，国内选择上述已有 master 标签。没有创建或修改任何标签；脱敏证据在 Git 外本地保存。
- pass：更新后的 BP Studio 部署、新 MPA 创建、实际 Worker 源码和新会话命令冒烟；首次功能失败记录保留如下。完整 A2A、Codex/Pi/Harness、国内真实部署、日历和真人 IM 仍不属于此次有界验证。

## 2026-10-21 部署源码、新 MPA 及功能边界

提交 `09e124e8be59ae379c6f1a7e87aba2d568cc1282` 已推送到原 PR #1178，通过支持的 BP Studio update 路径部署，并使用 `--skip-cronjob-scheduler`。应用 `3463b27bd210` / 函数 `cst7puxr` 于 Asia/Shanghai 17:46:56 达到稳定函数 revision **12**，发布状态 `done`。原环境变量值和 scheduler 设置均保留。部署 wheel 中解析模块哈希为 `5028f8feb77cadd5b615f0248a23783c5f7798fdb31ccda3d3f8196a6448cc06`，service 哈希为 `a1e21d2dab3e34bcd5d05860eb4d98b3e1e22ef4f8b3e38a4ce5546c423688d1`，均与已测源码一致。

复用已授权 Chrome 会话创建 **`studio-readonly-1021-a`**，页面显示创建成功。原生状态为 `ready`，保留两个请求的 latest 地址以及已选中的现有标签：

| 资源 | 实测结果 |
| --- | --- |
| Agent | `mi-5c74df2575dc5e89ad445d76` |
| Runtime | `r-yexqmg6z9cy9bkt9hm42`，Ready，version 2；带鉴权 health/readiness HTTP 200 |
| Worker Tool | `t-yexqlmcetcy9bkt9ihdf`，Ready；17:48 创建，同一请求重试复用 |
| Agent 选中标签 | `mpa_agent:mpa-sha256-63d32384da817cb38b55b6dfeda7d2cd8a851e9d119d18abb30ee8632aec599f` |
| Worker 选中标签 | `mpa_codex_worker:mpa-sha256-1e40dd91e8c10b067a31ef4113eb9829575baf9101cf9d5e6103144b9491f862` |
| Worker 函数 / revision / 实际 image ID | `ptlrrzjl` / 1 / **`ayk6eadc2t`**，不是旧 `vollyz6n0i` |
| 实际 Worker 源码 | 215 个 Python 文件；指纹 `30c2b491f1fe460e731627bda9f40f160a6d26f4d7d8398ff91a3056a2943490`，匹配已发布 Worker，存在私有用户模块 |
| 业务 PG / SkillSpace / OV | `sunny-bluet-3db026cb`，aidb ready / `ss-yexqmg5kowdlwzgmqn9d` / `ov-f54074c915387e15`，READY |
| 成功的有界冒烟 | 新 Studio 会话 `8606260b-eeb7-4752-9782-0a860fc6fd07` 执行 `/bin/bash -lc 'printf STUDIO_READONLY_1021_FRESH_OK'`；真实 stdout 一致，退出码 0，完成的页面回答显示了两者 |

镜像地址前缀为 `agentkit-platform-3001037806-ap-southeast-1.cr.bytepluses.com/mpa/`。两个标签原本已经存在，发现阶段没有发布任何标签。专用源码探针 Session `s-yexqlugkxsuexbvqjn6i` 已删除。脱敏原生/部署/API 证据及创建/功能截图在 Git 外本地保存，未提交凭据或原始云记录。

观察到两个独立条件，不能被后续新会话成功掩盖：

1. 创建任务 `49556dec-276c-4053-9507-ed08cdb98bf3` 最初遇到 OV `InvalidParameter`。海外 CloudTrail 中请求 `2026102109482052668D9A8D2903007881`、`20261021095118D4C86EA35A3890F6A34D` 证明库数量超过账号上限 **20**；既有 UI 泛化显示为模型/配置拒绝。用户明确授权后，仅对上次测试 `studio-snapshot-1021-a` 的库 `ov-4dcc6e25514a5979` 核验归属并删除；删除成功，随后 Get 确认 collection-not-found。该旧验证 MPA 现在没有可用的 OV 记忆库。原创建请求随后成功，Worker 和两个镜像选择均保留。没有修改 OV 代码、模型设置、配额，也没有用 Runtime 配置变通。
2. 首次 Studio 会话 `de1ce841-0f42-4087-be22-8845b1014798` **没有执行**所请求的 printf。页面报告 `inactive_worker_dispatch` 和 `harness invocation plan update was not persisted`，最后回复失败解释。持久 harness/control 状态为 `completed`，不能据此证明命令执行。源码将前者定位到 Agent MainRuntime active-grant 检查，后者定位到有条件的计划持久化；确切根因未建立，本次未修改这两条路径。检查时任务已完成，因此没有发起暂停变更。另一个新会话使用遇错即止的有界提示词，随后成功执行命令。这证明创建/镜像/新会话冒烟通过，**不证明**全部初始会话或显式 Worker 派发路径可靠。

剩余边界：完整 A2A/日历/IM 和国内 Runtime 部署未验证，仍要求发布方保留版本标签且不覆盖。新 MPA 及两个功能对话保留供核查，不升级既有 MPA。
