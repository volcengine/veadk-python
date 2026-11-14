# Bash 缓存并发初始化修复

[English](2026-10-24-concurrent-cache.md)

- 变更 ID：`studio-blesh-cache`
- 创建/修订日期：2026-10-24
- 状态：implemented
- 组件影响：仅修正内部实现，不改变公开 API、Shell 配置契约、最终缓存格式或权限，无需修改组件 spec。

## 证据与范围

固定使用的 ble.sh v0.4.0-devel3 在 `ble/builtin/bind/read-user-settings/.collect` 中写入并重命名同一个 `$cache.part`。多个 Shell 并发启动时可能移走其他 Shell 的临时文件，首次进入工作区出现 `mv: cannot stat`。已核对线上版本及这两行实现。上游 [src/decode.sh](https://github.com/akinomyoga/ble.sh/blob/master/src/decode.sh) 已改用进程独立的临时文件名。

保留 Bash、高亮、快捷键和共享最终缓存。不升级无关依赖、不修改项目文件、不发布镜像、不重启正在运行的工作。用户在 2026-10-24 确认同时修复镜像源码和当前工作区。

## 需求与方案

- FR-1：多个 Shell 必须能并发生成完整 Readline 缓存，不共用临时文件。移植上游的 `$$` 文件名后缀，使管道写入和随后重命名使用相同的进程标识。
- FR-2：全量和增量镜像构建应用同一份可重复执行的修复。上游源码不符合预期时，修改前报错。通过同目录临时文件原子替换插件文件，保留文件权限。
- FR-3：不改变权限设置，修复当前工作区。系统插件只读且 sudo 被禁用，因此将已安装插件复制到用户本地数据目录，应用相同修复，备份 `.bashrc` 后仅调整插件加载路径。新终端使用副本，保留已运行的终端。

代码范围：`frontend/sandbox-image/runtime/ble_cache.py`（新增）、`install-image.py` 和 `refresh-editor.py`。回归测试位于 `frontend/sandbox-image/tests/`。当前工作区的修改在仓库外，不包含凭据或项目文件变更。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| FR-1 | T-1：复现后修复 | AC-1：同步启动的竞争写入者均成功，不丢失临时文件，缓存完整 | 定向 Bash 子进程回归 | pass：旧版丢失一个写入者，修复后两者均成功 |
| FR-2 | T-2：接入两种构建 | AC-2：重复修复保留内容、权限和修改时间；异常源码不变 | Python 修复测试和构建入口审查 | pass |
| FR-3 | T-3：修复线上工作区 | AC-3：新终端加载修复版 ble.sh 并正常执行命令 | 浏览器终端验证 | pass：新终端已确认加载路径和修复函数，并执行 `echo ok` |

命令：`python3 -m unittest discover -s frontend/sandbox-image/tests -v`；对改动 Python 文件执行 Ruff、Pyright；`git diff --check`。

## 审查、风险与恢复

直接设计审查确认不改变 API、归属、凭据或依赖；中英文需求和验收一致。固定源码校验防止上游变化后误改。确定性并发测试覆盖实际写入/重命名冲突，仅验证界面不足以证明并发安全。修复不屏蔽真实文件系统错误，临时文件后缀不改变持久缓存名称。

当前工作区可通过恢复备份的 `.bashrc` 回滚，不修改系统文件。完整镜像构建、发布和大范围应用测试不在本次授权范围；镜像源码先保存在本地，新云端工作区需后续发布镜像。线上修复的保留时间取决于当前沙箱文件系统的生命周期。

2026-10-24 验证，基于 `c662cc8d4` 的本地改动：`python3 -m unittest discover -s frontend/sandbox-image/tests -v` 的 15 项测试全部通过，提交前复跑亦通过。使用仓库已有 Python 环境对 `runtime/ble_cache.py`、`runtime/install-image.py`、`runtime/refresh-editor.py` 和 `tests/test_ble_cache.py` 执行 Ruff、Pyright：pass，无错误。`pre-commit run --all-files`：pass，包含 Ruff、格式、密钥扫描和依赖规则检查。`git diff --check`：pass。完整 Docker 构建和大范围应用测试：not_run，本次限定为源码修复和轻量检查。2026-10-24 已要求提交 Draft PR；镜像发布仍不在本次范围。
