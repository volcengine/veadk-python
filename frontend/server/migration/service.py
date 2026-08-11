# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Stateless Studio orchestration for migrations inside Dev Sandbox Sessions."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import mimetypes
import re
import shlex
import stat
import time
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from frontend.server.deployment_source import (
    DeploymentSourceError,
    extract_migration_source,
)

from .contracts import (
    MigrationContractError,
    validate_analysis_result,
    validate_analysis_status,
    validate_confirmation,
    validate_delivery_result,
    validate_delivery_status,
    validate_migration_request,
    validate_process_exit,
    validate_source_status,
    validate_stopped_status,
)
from .gateway import (
    MigrationGateway,
    MigrationGatewayError,
    MigrationRemoteFileNotFound,
    MigrationSandboxSession,
)
from .models import (
    MIGRATION_FRAMEWORKS,
    STRUCTURED_MIGRATION_FRAMEWORKS,
    ConfirmMigrationBody,
    CreateMigrationTaskBody,
)

MIGRATION_ROOT = "/home/gem/.studio/migration/v1"
MIGRATION_SESSION_TTL_SECONDS = 60 * 60
MIGRATION_UPLOAD_MAX_BYTES = 50 * 1024 * 1024
_MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
_MAX_ARCHIVE_FILES = 20_000
_MAX_ARCHIVE_PATH_BYTES = 4 * 1024
_MAX_ARCHIVE_DEPTH = 64
_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_PROVENANCE_BYTES = 64 * 1024
_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
_MAX_PREVIEW_BYTES = 2 * 1024 * 1024
_FILE_OPERATION_TIMEOUT_SECONDS = 300
_TASK_ID_RE = re.compile(r"^migration-v1-[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ACTIVE_STATES = {"analyzing", "migrating", "validating", "packaging"}
_REQUEST_PATH = f"{MIGRATION_ROOT}/request.json"
_SOURCE_PATH = f"{MIGRATION_ROOT}/input/source.zip"
_PROJECT_PATH = f"{MIGRATION_ROOT}/input/project"
_SOURCE_STATUS_PATH = f"{MIGRATION_ROOT}/state/source.json"
_ANALYSIS_STATUS_PATH = f"{MIGRATION_ROOT}/state/analysis-status.json"
_ANALYSIS_RESULT_PATH = f"{MIGRATION_ROOT}/state/analysis.json"
_ANALYSIS_PROMPT_PATH = f"{MIGRATION_ROOT}/state/analysis-prompt.md"
_ANALYSIS_SCHEMA_PATH = f"{MIGRATION_ROOT}/state/analysis-schema.json"
_ANALYSIS_PROCESS_EXIT_PATH = f"{MIGRATION_ROOT}/state/analysis-process-exit.json"
_CONFIRMATION_PATH = f"{MIGRATION_ROOT}/state/confirmation.json"
_INSTRUCTION_PATH = f"{MIGRATION_ROOT}/state/migration-instructions.md"
_STOPPED_PATH = f"{MIGRATION_ROOT}/state/stopped.json"
_PROCESS_EXIT_PATH = f"{MIGRATION_ROOT}/state/migration-process-exit.json"
_DELIVERY_STATUS_PATH = f"{MIGRATION_ROOT}/delivery/migration-status.json"
_DELIVERY_RESULT_PATH = f"{MIGRATION_ROOT}/delivery/migration-result.json"
_DELIVERY_ARTIFACT_PATH = f"{MIGRATION_ROOT}/delivery/migration-result.zip"

logger = logging.getLogger(__name__)


class MigrationError(RuntimeError):
    """A bounded migration failure safe to expose through Studio."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable

    def detail(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class SourceArchiveSummary:
    file_count: int
    expanded_bytes: int


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def validate_source_archive(content: bytes) -> SourceArchiveSummary:
    """Validate ZIP structure without assuming a source framework or root layout."""
    if not content:
        raise MigrationError(
            "MIGRATION_SOURCE_EMPTY",
            "上传的 ZIP 文件为空。",
            status_code=422,
        )
    if len(content) > MIGRATION_UPLOAD_MAX_BYTES:
        raise MigrationError(
            "MIGRATION_SOURCE_TOO_LARGE",
            "项目 ZIP 不能超过 50 MiB。",
            status_code=413,
        )
    seen: set[str] = set()
    file_count = 0
    expanded_bytes = 0
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for info in archive.infolist():
                raw_path = info.filename
                path = PurePosixPath(raw_path)
                normalized = path.as_posix()
                if (
                    not raw_path
                    or "\\" in raw_path
                    or _has_control_character(raw_path)
                    or path.is_absolute()
                    or ".." in path.parts
                    or _utf8_length(normalized) > _MAX_ARCHIVE_PATH_BYTES
                    or len(path.parts) > _MAX_ARCHIVE_DEPTH
                ):
                    raise MigrationError(
                        "MIGRATION_SOURCE_UNSAFE_PATH",
                        f"项目 ZIP 包含不安全路径：{raw_path}",
                        status_code=422,
                    )
                folded = normalized.casefold()
                if folded in seen:
                    raise MigrationError(
                        "MIGRATION_SOURCE_DUPLICATE_PATH",
                        f"项目 ZIP 包含重复路径：{raw_path}",
                        status_code=422,
                    )
                seen.add(folded)
                mode = info.external_attr >> 16
                if stat.S_IFMT(mode) == stat.S_IFLNK:
                    raise MigrationError(
                        "MIGRATION_SOURCE_SYMLINK",
                        f"项目 ZIP 不允许符号链接：{raw_path}",
                        status_code=422,
                    )
                if info.flag_bits & 0x1:
                    raise MigrationError(
                        "MIGRATION_SOURCE_ENCRYPTED",
                        "项目 ZIP 不支持加密文件。",
                        status_code=422,
                    )
                if info.is_dir():
                    continue
                file_count += 1
                expanded_bytes += info.file_size
                if file_count > _MAX_ARCHIVE_FILES:
                    raise MigrationError(
                        "MIGRATION_SOURCE_FILE_COUNT",
                        f"项目 ZIP 文件数不能超过 {_MAX_ARCHIVE_FILES} 个。",
                        status_code=413,
                    )
                if expanded_bytes > _MAX_EXPANDED_BYTES:
                    raise MigrationError(
                        "MIGRATION_SOURCE_EXPANDED_TOO_LARGE",
                        "项目 ZIP 解压后不能超过 1 GiB。",
                        status_code=413,
                    )
    except zipfile.BadZipFile as error:
        raise MigrationError(
            "MIGRATION_SOURCE_INVALID",
            "请选择有效的 ZIP 项目文件。",
            status_code=422,
        ) from error
    if file_count == 0:
        raise MigrationError(
            "MIGRATION_SOURCE_EMPTY",
            "项目 ZIP 中没有可迁移文件。",
            status_code=422,
        )
    return SourceArchiveSummary(
        file_count=file_count,
        expanded_bytes=expanded_bytes,
    )


def _utf8_length(value: str) -> int:
    return len(value.encode("utf-8"))


def _timestamp(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _iso_timestamp(value: float) -> str:
    return (
        datetime.fromtimestamp(value, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_json_command(path: str, value: object) -> str:
    temporary = f"{path}.tmp"
    return (
        f"printf '%s\\n' {shlex.quote(json.dumps(value, ensure_ascii=False))} "
        f"> {shlex.quote(temporary)} && mv {shlex.quote(temporary)} {shlex.quote(path)}"
    )


def _accept_request_command(candidate_path: str, expected_sha256: str) -> str:
    script = f"""
import fcntl
import hashlib
import json
import os
from pathlib import Path

root = Path({MIGRATION_ROOT!r})
candidate = Path({candidate_path!r})
request = Path({_REQUEST_PATH!r})
lock = root / "state" / "request-accept.lock"
expected_sha256 = {expected_sha256!r}
immutable_fields = (
    "schema_version",
    "task_id",
    "source_file_name",
    "instruction",
    "session_ttl_seconds",
)

root.mkdir(parents=True, exist_ok=True)
lock.parent.mkdir(parents=True, exist_ok=True)
if not candidate.is_file():
    raise RuntimeError("migration request candidate is missing")
candidate_content = candidate.read_bytes()
if hashlib.sha256(candidate_content).hexdigest() != expected_sha256:
    raise RuntimeError("migration request candidate digest does not match")
candidate_value = json.loads(candidate_content)

fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    if request.exists():
        current = json.loads(request.read_text(encoding="utf-8"))
        if any(current.get(field) != candidate_value.get(field) for field in immutable_fields):
            raise RuntimeError("migration request conflicts with the accepted request")
        candidate.unlink(missing_ok=True)
    else:
        candidate.replace(request)
finally:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
"""
    return "set -euo pipefail\npython3 - <<'PY'\n" + script.strip() + "\nPY"


def _analysis_schema() -> dict[str, object]:
    evidence = {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "line", "reason"],
        "properties": {
            "path": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4_096,
                "pattern": (
                    r"^(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))"
                    r"(?!.*//)(?!.*\\)[^\x00-\x1f\x7f]+$"
                ),
            },
            "line": {"type": "integer", "minimum": 1},
            "reason": {"type": "string", "minLength": 1, "maxLength": 4_000},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "summary",
            "frameworks",
            "recommended",
            "entries",
            "boundary",
            "questions",
            "warnings",
        ],
        "properties": {
            "schema_version": {"const": 1},
            "summary": {"type": "string", "maxLength": 20_000},
            "frameworks": {
                "type": "array",
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "confidence", "evidence"],
                    "properties": {
                        "id": {
                            "enum": list(MIGRATION_FRAMEWORKS),
                        },
                        "confidence": {"enum": ["high", "medium", "low"]},
                        "evidence": {
                            "type": "array",
                            "maxItems": 100,
                            "items": evidence,
                        },
                    },
                },
            },
            "recommended": {
                "type": "object",
                "additionalProperties": False,
                "required": ["framework", "entry", "reason"],
                "properties": {
                    "framework": {"enum": list(MIGRATION_FRAMEWORKS)},
                    "entry": {
                        "type": ["string", "null"],
                        "maxLength": 512,
                    },
                    "reason": {"type": "string", "maxLength": 4_000},
                },
            },
            "entries": {
                "type": "array",
                "maxItems": 100,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["value", "framework", "evidence"],
                    "properties": {
                        "value": {"type": "string", "maxLength": 512},
                        "framework": {"enum": list(MIGRATION_FRAMEWORKS)},
                        "evidence": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 4_000,
                        },
                    },
                },
            },
            "boundary": {
                "type": "object",
                "additionalProperties": False,
                "required": ["include", "exclude"],
                "properties": {
                    "include": {
                        "type": "array",
                        "maxItems": 200,
                        "items": {"type": "string", "maxLength": 4_000},
                    },
                    "exclude": {
                        "type": "array",
                        "maxItems": 200,
                        "items": {"type": "string", "maxLength": 4_000},
                    },
                },
            },
            "questions": {
                "type": "array",
                "maxItems": 50,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "prompt", "required"],
                    "properties": {
                        "id": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 128,
                        },
                        "prompt": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 4_000,
                        },
                        "required": {"type": "boolean"},
                    },
                },
            },
            "warnings": {
                "type": "array",
                "maxItems": 100,
                "items": {"type": "string", "maxLength": 4_000},
            },
        },
    }


def _analysis_prompt(request: dict[str, object]) -> str:
    instruction = str(request.get("instruction") or "").strip()
    return f"""你是 AgentKit 项目迁移分析器。此阶段只分析，不执行迁移。

## 安全与操作边界

- 只读检查 `{_PROJECT_PATH}`，禁止修改、安装依赖、联网或执行来源项目代码。
- 不要调用 `ak migrate inspect`，也不要开始任何迁移。
- 通过依赖文件、导入、对象定义、配置和调用关系识别框架、候选入口与迁移边界。
- 每个结论必须给出文件路径、行号和理由；证据不足时降低置信度，不得猜测。
- Structured 候选仅限 langchain、langgraph、adk、strands、agentcore。
- Dify 导出选择 dify；无法可靠归类、需要 Agentic 改写的项目选择 any。
- 最终迁移方式必须由用户选择并确认，本阶段只给建议和待确认问题。
- 用户使用什么语言，你就使用什么语言；JSON 字段名保持 Schema 约定。
- 最终响应必须严格符合提供的 JSON Schema，不要输出 Markdown 围栏或额外文字。

## 用户补充要求

{instruction or "用户未补充额外要求。"}
"""


def _prepare_source_command(
    *,
    candidate_path: str,
    source_sha256: str,
    source_size: int,
    summary: SourceArchiveSummary,
) -> str:
    script = f"""
import hashlib
import json
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

root = Path({MIGRATION_ROOT!r})
candidate = Path({candidate_path!r})
source = Path({_SOURCE_PATH!r})
project = Path({_PROJECT_PATH!r})
marker = Path({_SOURCE_STATUS_PATH!r})
lock = root / "state" / "source-accept.lock"
expected_sha = {source_sha256!r}
expected_size = {source_size}
expected_files = {summary.file_count}
expected_expanded = {summary.expanded_bytes}
max_files = {_MAX_ARCHIVE_FILES}
max_bytes = {_MAX_EXPANDED_BYTES}
max_path_bytes = {_MAX_ARCHIVE_PATH_BYTES}
max_depth = {_MAX_ARCHIVE_DEPTH}

for relative in ("input", "state", "events", "logs", "workspace", "work", "output", "delivery"):
    (root / relative).mkdir(parents=True, exist_ok=True)

if marker.exists():
    current = json.loads(marker.read_text(encoding="utf-8"))
    if current.get("sha256") == expected_sha:
        candidate.unlink(missing_ok=True)
        raise SystemExit(0)
    raise RuntimeError("migration source is immutable after acceptance")

try:
    lock.mkdir()
except FileExistsError as error:
    raise RuntimeError("migration source acceptance is already running") from error

extracting = root / "input" / f".extract-{{expected_sha}}"
normalized = root / "input" / f".project-{{expected_sha}}"
try:
    if not candidate.is_file() or candidate.stat().st_size != expected_size:
        raise RuntimeError("uploaded source size does not match")
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if digest != expected_sha:
        raise RuntimeError("uploaded source digest does not match")
    shutil.rmtree(extracting, ignore_errors=True)
    shutil.rmtree(normalized, ignore_errors=True)
    extracting.mkdir()
    files = 0
    expanded = 0
    with zipfile.ZipFile(candidate) as archive:
        for info in archive.infolist():
            raw = info.filename
            path = PurePosixPath(raw)
            if (
                not raw
                or "\\\\" in raw
                or any(ord(character) < 32 or ord(character) == 127 for character in raw)
                or path.is_absolute()
                or ".." in path.parts
                or len(raw.encode("utf-8")) > max_path_bytes
                or len(path.parts) > max_depth
            ):
                raise RuntimeError("unsafe archive path")
            if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                raise RuntimeError("archive links are not allowed")
            target = extracting.joinpath(*path.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            files += 1
            expanded += info.file_size
            if files > max_files or expanded > max_bytes:
                raise RuntimeError("expanded archive exceeds limits")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source_file, target.open("wb") as output:
                shutil.copyfileobj(source_file, output, length=1024 * 1024)
    if files != expected_files or expanded != expected_expanded:
        raise RuntimeError("uploaded source metadata changed during transfer")
    children = list(extracting.iterdir())
    if len(children) == 1 and children[0].is_dir():
        children[0].rename(normalized)
        extracting.rmdir()
    else:
        extracting.rename(normalized)
    if project.exists():
        raise RuntimeError("migration project is immutable after extraction")
    normalized.rename(project)
    candidate.replace(source)
    payload = {{
        "schema_version": 1,
        "sha256": expected_sha,
        "size": expected_size,
        "file_count": files,
        "expanded_bytes": expanded,
    }}
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(marker)
finally:
    shutil.rmtree(extracting, ignore_errors=True)
    shutil.rmtree(normalized, ignore_errors=True)
    try:
        lock.rmdir()
    except OSError:
        pass
"""
    return "set -euo pipefail\npython3 - <<'PY'\n" + script.strip() + "\nPY"


def _start_analysis_command() -> str:
    running_status = {
        "schema_version": 1,
        "state": "analyzing",
        "message": "正在分析项目框架、入口与迁移边界",
    }
    ready_status = {
        "schema_version": 1,
        "state": "ready",
        "message": "项目分析完成，请确认迁移方式",
    }
    failed_status = {
        "schema_version": 1,
        "state": "failed",
        "message": "项目分析未完成，请查看日志后重试",
        "error": {
            "code": "MIGRATION_ANALYSIS_FAILED",
            "message": "Codex 未能完成只读项目分析。",
            "retryable": False,
        },
    }
    start_failed_status = {
        "schema_version": 1,
        "state": "failed",
        "message": "项目分析启动失败，请新建迁移后重试",
        "error": {
            "code": "MIGRATION_ANALYSIS_START_FAILED",
            "message": "Codex 只读项目分析未能启动。",
            "retryable": False,
        },
    }
    result_tmp = f"{_ANALYSIS_RESULT_PATH}.tmp"
    log_path = f"{MIGRATION_ROOT}/logs/analysis.log"
    pid_path = f"{MIGRATION_ROOT}/state/analysis.pid"
    lock_path = f"{MIGRATION_ROOT}/state/analysis-start.lock"
    validate_json = shlex.quote(
        "import json,sys; json.load(open(sys.argv[1], encoding='utf-8'))"
    )
    inner = "\n".join(
        [
            "set +e",
            (
                "codex exec --sandbox read-only --skip-git-repo-check "
                f"--cd {shlex.quote(_PROJECT_PATH)} "
                f"--output-schema {shlex.quote(_ANALYSIS_SCHEMA_PATH)} "
                f"--output-last-message {shlex.quote(result_tmp)} - "
                f"< {shlex.quote(_ANALYSIS_PROMPT_PATH)} "
                f"> {shlex.quote(log_path)} 2>&1"
            ),
            "code=$?",
            (
                f'if [ "$code" -eq 0 ] && '
                f"python3 -c {validate_json} "
                f"{shlex.quote(result_tmp)}; then"
            ),
            f"  mv {shlex.quote(result_tmp)} {shlex.quote(_ANALYSIS_RESULT_PATH)}",
            f"  {_atomic_json_command(_ANALYSIS_STATUS_PATH, ready_status)}",
            "else",
            f"  rm -f {shlex.quote(result_tmp)}",
            f"  {_atomic_json_command(_ANALYSIS_STATUS_PATH, failed_status)}",
            "fi",
            (
                f'printf \'%s\\n\' "{{\\"schema_version\\":1,'
                f'\\"exit_code\\":$code}}" > '
                f"{shlex.quote(_ANALYSIS_PROCESS_EXIT_PATH)}.tmp"
            ),
            (
                f"mv {shlex.quote(_ANALYSIS_PROCESS_EXIT_PATH)}.tmp "
                f"{shlex.quote(_ANALYSIS_PROCESS_EXIT_PATH)}"
            ),
            'exit "$code"',
        ]
    )
    return "\n".join(
        [
            "set -euo pipefail",
            f"test -d {shlex.quote(_PROJECT_PATH)}",
            f"if test -f {shlex.quote(_ANALYSIS_STATUS_PATH)}; then exit 0; fi",
            "command -v bash >/dev/null",
            "command -v codex >/dev/null",
            "command -v setsid >/dev/null",
            f"if ! mkdir {shlex.quote(lock_path)}; then",
            (f"  if test -f {shlex.quote(_ANALYSIS_STATUS_PATH)}; then exit 0; fi"),
            (
                f"  if test -s {shlex.quote(pid_path)} && "
                f'kill -0 "$(cat {shlex.quote(pid_path)})" 2>/dev/null; '
                "then exit 0; fi"
            ),
            '  echo "analysis start lock exists without a live process" >&2',
            "  exit 1",
            "fi",
            "analysis_start_complete=0",
            "cleanup_analysis_start() {",
            "  code=$?",
            '  if [ "$analysis_start_complete" -ne 1 ]; then',
            f"    rm -f {shlex.quote(pid_path)} {shlex.quote(f'{pid_path}.tmp')}",
            (
                f"    {_atomic_json_command(_ANALYSIS_STATUS_PATH, start_failed_status)} "
                "|| true"
            ),
            f"    rmdir {shlex.quote(lock_path)} 2>/dev/null || true",
            "  fi",
            '  return "$code"',
            "}",
            "trap cleanup_analysis_start EXIT",
            _atomic_json_command(_ANALYSIS_STATUS_PATH, running_status),
            f"setsid bash -c {shlex.quote(inner)} </dev/null >/dev/null 2>&1 &",
            "pid=$!",
            f"printf '%s\\n' \"$pid\" > {shlex.quote(pid_path)}.tmp",
            f"mv {shlex.quote(pid_path)}.tmp {shlex.quote(pid_path)}",
            'kill -0 "$pid"',
            "analysis_start_complete=1",
            "trap - EXIT",
        ]
    )


def _migration_instruction(
    request: dict[str, object],
    confirmation: dict[str, object],
    analysis: dict[str, object],
) -> str:
    answers = confirmation.get("answers")
    answer_lines = []
    if isinstance(answers, dict):
        answer_lines = [
            f"- {key}: {value}"
            for key, value in answers.items()
            if isinstance(key, str) and isinstance(value, str) and value
        ]
    boundary = analysis.get("boundary")
    boundary_text = json.dumps(boundary, ensure_ascii=False, indent=2)
    return "\n".join(
        [
            "# Confirmed migration requirements",
            "",
            str(request.get("instruction") or "No initial instruction."),
            "",
            str(confirmation.get("instruction") or "No additional instruction."),
            "",
            "## Confirmed answers",
            "",
            *(answer_lines or ["- No additional answers."]),
            "",
            "## Analysis boundary",
            "",
            boundary_text,
            "",
            "Preserve observable behavior and external integration boundaries.",
            "Apply AgentKit best practices without claiming unverified fidelity.",
            "Use the same language as the user's instructions in reports.",
            "",
        ]
    )


def _ak_command(
    task_id: str,
    confirmation: dict[str, object],
) -> str:
    framework = str(confirmation["framework"])
    app_name = str(confirmation["app_name"])
    source = f"{MIGRATION_ROOT}/workspace/source"
    common = [
        "ak",
        "migrate",
        source,
        "--framework",
        framework,
        "--name",
        app_name,
        "--delivery-dir",
        f"{MIGRATION_ROOT}/delivery",
        "--provenance-file",
        _CONFIRMATION_PATH,
        "--run-id",
        task_id,
    ]
    if framework in STRUCTURED_MIGRATION_FRAMEWORKS:
        common.extend(
            [
                "--entry",
                str(confirmation["entry"]),
                "--output",
                "migrated",
                "--verify",
            ]
        )
    else:
        common.extend(
            [
                "--execution",
                "in-place",
                "--output",
                f"{MIGRATION_ROOT}/output/veadk",
                "--work-dir",
                f"{MIGRATION_ROOT}/work/agentic",
                "--non-interactive",
                "--instruction-file",
                _INSTRUCTION_PATH,
            ]
        )
    return " ".join(shlex.quote(item) for item in common)


def _start_migration_command(
    task_id: str,
    confirmation: dict[str, object],
    confirmation_sha256: str,
    confirmation_candidate: str,
    instruction_candidate: str,
) -> str:
    pid_path = f"{MIGRATION_ROOT}/state/migration.pid"
    log_path = f"{MIGRATION_ROOT}/logs/migration.log"
    lock_path = f"{MIGRATION_ROOT}/state/migration-start.lock"
    cli = _ak_command(task_id, confirmation)
    inner = "\n".join(
        [
            "set +e",
            f"{cli} > {shlex.quote(log_path)} 2>&1",
            "code=$?",
            (
                f'printf \'%s\\n\' "{{\\"schema_version\\":1,'
                f'\\"exit_code\\":$code}}" > {shlex.quote(_PROCESS_EXIT_PATH)}.tmp'
            ),
            (
                f"mv {shlex.quote(_PROCESS_EXIT_PATH)}.tmp "
                f"{shlex.quote(_PROCESS_EXIT_PATH)}"
            ),
            'exit "$code"',
        ]
    )
    return "\n".join(
        [
            "set -euo pipefail",
            (
                f"if test -f {shlex.quote(_CONFIRMATION_PATH)} || "
                f"test -f {shlex.quote(_DELIVERY_STATUS_PATH)} || "
                f"test -f {shlex.quote(_PROCESS_EXIT_PATH)}; then exit 0; fi"
            ),
            "command -v ak >/dev/null",
            "command -v awk >/dev/null",
            "command -v bash >/dev/null",
            "command -v cp >/dev/null",
            "command -v setsid >/dev/null",
            "command -v sha256sum >/dev/null",
            f"if ! mkdir {shlex.quote(lock_path)}; then",
            (
                f"  if test -f {shlex.quote(_CONFIRMATION_PATH)} || "
                f"test -f {shlex.quote(_DELIVERY_STATUS_PATH)} || "
                f"test -f {shlex.quote(_PROCESS_EXIT_PATH)}; then exit 0; fi"
            ),
            (
                f"  if test -s {shlex.quote(pid_path)} && "
                f'kill -0 "$(cat {shlex.quote(pid_path)})" 2>/dev/null; '
                "then exit 0; fi"
            ),
            '  echo "migration start lock exists without a live process" >&2',
            "  exit 1",
            "fi",
            "migration_start_complete=0",
            "cleanup_migration_start() {",
            "  code=$?",
            '  if [ "$migration_start_complete" -ne 1 ]; then',
            f"    rm -f {shlex.quote(pid_path)} {shlex.quote(f'{pid_path}.tmp')}",
            (
                f"    {_atomic_json_command(_PROCESS_EXIT_PATH, {'schema_version': 1, 'exit_code': 125})} "
                "|| true"
            ),
            f"    rmdir {shlex.quote(lock_path)} 2>/dev/null || true",
            "  fi",
            '  return "$code"',
            "}",
            "trap cleanup_migration_start EXIT",
            (
                f'test "$(sha256sum {shlex.quote(confirmation_candidate)} '
                f"| awk '{{print $1}}')\" = {shlex.quote(confirmation_sha256)}"
            ),
            (
                f"mv {shlex.quote(confirmation_candidate)} "
                f"{shlex.quote(_CONFIRMATION_PATH)}"
            ),
            (
                f"mv {shlex.quote(instruction_candidate)} "
                f"{shlex.quote(_INSTRUCTION_PATH)}"
            ),
            f"test -d {shlex.quote(_PROJECT_PATH)}",
            f"mkdir -p {shlex.quote(f'{MIGRATION_ROOT}/workspace')}",
            f"test ! -e {shlex.quote(f'{MIGRATION_ROOT}/workspace/source')}",
            (
                f"cp -a {shlex.quote(_PROJECT_PATH)} "
                f"{shlex.quote(f'{MIGRATION_ROOT}/workspace/source')}"
            ),
            f"setsid bash -c {shlex.quote(inner)} </dev/null >/dev/null 2>&1 &",
            "pid=$!",
            f"printf '%s\\n' \"$pid\" > {shlex.quote(pid_path)}.tmp",
            f"mv {shlex.quote(pid_path)}.tmp {shlex.quote(pid_path)}",
            'kill -0 "$pid"',
            "migration_start_complete=1",
            "trap - EXIT",
        ]
    )


def _stop_command() -> str:
    status = {
        "schema_version": 1,
        "state": "cancelled",
        "message": "迁移已终止",
    }
    python = f"""
import os
import signal
import time
from pathlib import Path

root = Path({MIGRATION_ROOT!r})
root_marker = str(root).encode()
for name in ("analysis.pid", "migration.pid"):
    path = root / "state" / name
    if not path.exists():
        continue
    try:
        pid = int(path.read_text(encoding="ascii").strip())
        command = Path(f"/proc/{{pid}}/cmdline").read_bytes().replace(b"\\0", b" ")
        if root_marker not in command or (
            b"codex exec" not in command and b"ak migrate" not in command
        ):
            raise RuntimeError("pid does not belong to this migration")
        process_group = os.getpgid(pid)
        os.killpg(process_group, signal.SIGTERM)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        pass
    finally:
        path.unlink(missing_ok=True)
"""
    return "\n".join(
        [
            "set -euo pipefail",
            "python3 - <<'PY'",
            python.strip(),
            "PY",
            _atomic_json_command(_STOPPED_PATH, status),
        ]
    )


class MigrationService:
    """Derive task state from remote Sessions and files without a local repository."""

    def __init__(
        self,
        gateway: MigrationGateway,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._gateway = gateway
        self._clock = clock

    @staticmethod
    def _translate(error: MigrationGatewayError) -> MigrationError:
        return MigrationError(
            error.code,
            str(error),
            status_code=error.status_code,
            retryable=error.retryable,
        )

    def capabilities(self) -> dict[str, object]:
        capability = self._gateway.capabilities()
        return {
            "enabled": bool(capability.get("enabled")),
            "reason": str(capability.get("reason") or ""),
            "maxUploadBytes": MIGRATION_UPLOAD_MAX_BYTES,
            "sessionTtlSeconds": MIGRATION_SESSION_TTL_SECONDS,
            "frameworks": list(MIGRATION_FRAMEWORKS),
        }

    @staticmethod
    def _validate_task_id(task_id: str) -> None:
        if not _TASK_ID_RE.fullmatch(task_id):
            raise MigrationError(
                "MIGRATION_TASK_NOT_FOUND",
                "迁移会话不存在或已过期。",
                status_code=404,
            )

    def _session(self, task_id: str, owner_id: str) -> MigrationSandboxSession:
        self._validate_task_id(task_id)
        try:
            return self._gateway.find_session(task_id, owner_id)
        except MigrationGatewayError as error:
            raise self._translate(error) from error

    def _put(
        self,
        session: MigrationSandboxSession,
        path: str,
        content: bytes,
        *,
        media_type: str,
    ) -> None:
        try:
            self._gateway.put_file(
                session,
                path,
                content,
                media_type=media_type,
            )
        except MigrationGatewayError as error:
            raise self._translate(error) from error

    def _execute(
        self,
        session: MigrationSandboxSession,
        command: str,
        *,
        operation: str,
        timeout_seconds: int = 120,
    ) -> dict[str, object]:
        try:
            return self._gateway.execute_bash(
                session,
                command,
                operation=operation,
                timeout_seconds=timeout_seconds,
            )
        except MigrationGatewayError as error:
            raise self._translate(error) from error

    def _read(
        self,
        session: MigrationSandboxSession,
        path: str,
        *,
        max_bytes: int = _MAX_JSON_BYTES,
        optional: bool = False,
    ) -> bytes | None:
        try:
            return self._gateway.get_file(
                session,
                path,
                max_bytes=max_bytes,
            )
        except MigrationRemoteFileNotFound as error:
            if optional:
                return None
            raise self._translate(error) from error
        except MigrationGatewayError as error:
            raise self._translate(error) from error

    def _read_json(
        self,
        session: MigrationSandboxSession,
        path: str,
        *,
        optional: bool = False,
    ) -> dict[str, object] | None:
        content = self._read(session, path, optional=optional)
        if content is None:
            return None
        try:
            value = json.loads(content)
        except (UnicodeDecodeError, ValueError) as error:
            raise MigrationError(
                "MIGRATION_REMOTE_STATE_INVALID",
                "迁移会话状态文件格式无效。",
                status_code=502,
            ) from error
        if not isinstance(value, dict):
            raise MigrationError(
                "MIGRATION_REMOTE_STATE_INVALID",
                "迁移会话状态文件格式无效。",
                status_code=502,
            )
        return {str(key): item for key, item in value.items()}

    def create_task(
        self,
        body: CreateMigrationTaskBody,
        owner_id: str,
        creator_name: str,
    ) -> dict[str, object]:
        capability = self.capabilities()
        if not capability["enabled"]:
            raise MigrationError(
                "MIGRATION_DEVENV_UNAVAILABLE",
                str(capability["reason"]) or "Dev Sandbox 暂不可用。",
                status_code=503,
            )
        task_id = body.task_id or f"migration-v1-{uuid.uuid4().hex}"
        request = {
            "schema_version": 1,
            "task_id": task_id,
            "source_file_name": body.source_file_name,
            "instruction": body.instruction,
            "session_ttl_seconds": MIGRATION_SESSION_TTL_SECONDS,
        }
        try:
            session = self._gateway.create_session(
                task_id=task_id,
                owner_id=owner_id,
                creator_name=creator_name,
                display_name="存量迁移",
                ttl_seconds=MIGRATION_SESSION_TTL_SECONDS,
            )
            existing_request = self._read_json(
                session,
                _REQUEST_PATH,
                optional=True,
            )
            if existing_request is not None:
                self._validate_request(existing_request, request)
                return self._task_from_session(session)
            request["created_at"] = session.created_at or int(self._clock())
            request_content = _json_bytes(request)
            request_sha256 = hashlib.sha256(request_content).hexdigest()
            request_candidate = f"{MIGRATION_ROOT}/state/.request-{request_sha256}.json"
            self._put(
                session,
                request_candidate,
                request_content,
                media_type="application/json",
            )
            self._execute(
                session,
                _accept_request_command(request_candidate, request_sha256),
                operation="accept_request",
                timeout_seconds=30,
            )
            accepted_request = self._read_json(session, _REQUEST_PATH)
            if accepted_request is None:
                raise MigrationError(
                    "MIGRATION_REQUEST_MISSING",
                    "迁移请求文件不存在。",
                    status_code=502,
                )
            self._validate_request(accepted_request, request)
        except MigrationGatewayError as error:
            raise self._translate(error) from error
        return self._task_payload(session, request)

    @staticmethod
    def _validated_request(
        value: object,
        task_id: str,
    ) -> dict[str, object]:
        try:
            return validate_migration_request(
                value,
                expected_task_id=task_id,
                expected_ttl_seconds=MIGRATION_SESSION_TTL_SECONDS,
            )
        except MigrationContractError as error:
            raise MigrationError(
                "MIGRATION_REQUEST_INVALID",
                "迁移请求文件与当前 Session 不匹配或格式无效。",
                status_code=502,
            ) from error

    @staticmethod
    def _validated_source(value: object) -> dict[str, object]:
        try:
            return validate_source_status(value)
        except MigrationContractError as error:
            raise MigrationError(
                "MIGRATION_SOURCE_STATE_INVALID",
                "上传项目的来源状态无效。",
                status_code=502,
            ) from error

    @staticmethod
    def _validated_confirmation(
        value: object,
        task_id: str,
    ) -> dict[str, object]:
        try:
            return validate_confirmation(value, expected_task_id=task_id)
        except MigrationContractError as error:
            raise MigrationError(
                "MIGRATION_CONFIRMATION_INVALID",
                "迁移确认状态无效。",
                status_code=502,
            ) from error

    @staticmethod
    def _validated_process_exit(
        value: object,
        *,
        analysis: bool = False,
    ) -> dict[str, object]:
        try:
            return validate_process_exit(value)
        except MigrationContractError as error:
            raise MigrationError(
                (
                    "MIGRATION_ANALYSIS_PROCESS_STATE_INVALID"
                    if analysis
                    else "MIGRATION_PROCESS_STATE_INVALID"
                ),
                (
                    "Codex 分析进程状态无效。"
                    if analysis
                    else "AgentKit CLI 进程状态无效。"
                ),
                status_code=502,
            ) from error

    @staticmethod
    def _validate_request(
        existing: dict[str, object],
        expected: dict[str, object],
    ) -> None:
        MigrationService._validated_request(
            existing,
            str(expected["task_id"]),
        )
        if (
            existing.get("source_file_name") != expected["source_file_name"]
            or existing.get("instruction") != expected["instruction"]
            or existing.get("session_ttl_seconds") != expected["session_ttl_seconds"]
        ):
            raise MigrationError(
                "MIGRATION_REQUEST_CONFLICT",
                "该迁移会话 ID 已用于其他迁移请求。",
                status_code=409,
                retryable=False,
            )

    def upload_source(
        self,
        task_id: str,
        owner_id: str,
        content: bytes,
    ) -> dict[str, object]:
        summary = validate_source_archive(content)
        session = self._session(task_id, owner_id)
        current = self.get_task(task_id, owner_id)
        if current["state"] != "awaiting_upload":
            raise MigrationError(
                "MIGRATION_SOURCE_LOCKED",
                "分析开始后不能修改项目附件；请等待完成或终止当前迁移。",
                status_code=409,
            )
        digest = hashlib.sha256(content).hexdigest()
        accepted_source = self._read_json(
            session,
            _SOURCE_STATUS_PATH,
            optional=True,
        )
        if accepted_source is not None:
            accepted_source = self._validated_source(accepted_source)
            accepted_digest = accepted_source.get("sha256")
            if accepted_digest != digest:
                raise MigrationError(
                    "MIGRATION_SOURCE_LOCKED",
                    "项目附件已锁定；只能使用原 ZIP 继续启动分析。",
                    status_code=409,
                )
        else:
            candidate = f"{MIGRATION_ROOT}/input/.source-{digest}.zip"
            self._put(
                session,
                candidate,
                content,
                media_type="application/zip",
            )
            self._execute(
                session,
                _prepare_source_command(
                    candidate_path=candidate,
                    source_sha256=digest,
                    source_size=len(content),
                    summary=summary,
                ),
                operation="prepare_source",
                timeout_seconds=_FILE_OPERATION_TIMEOUT_SECONDS,
            )
        request = self._read_json(session, _REQUEST_PATH)
        if request is None:
            raise MigrationError(
                "MIGRATION_REQUEST_MISSING",
                "迁移请求文件不存在。",
                status_code=502,
            )
        request = self._validated_request(request, task_id)
        self._put(
            session,
            _ANALYSIS_SCHEMA_PATH,
            _json_bytes(_analysis_schema()),
            media_type="application/json",
        )
        self._put(
            session,
            _ANALYSIS_PROMPT_PATH,
            _analysis_prompt(request).encode("utf-8"),
            media_type="text/markdown",
        )
        self._execute(
            session,
            _start_analysis_command(),
            operation="start_analysis",
            timeout_seconds=30,
        )
        return self.get_task(task_id, owner_id)

    def list_tasks(self, owner_id: str) -> dict[str, list[dict[str, object]]]:
        try:
            sessions = self._gateway.list_sessions(owner_id)
        except MigrationGatewayError as error:
            raise self._translate(error) from error
        tasks = []
        for session in sessions:
            try:
                tasks.append(self._task_from_session(session))
            except MigrationError as error:
                logger.warning(
                    "Ignoring invalid state for one migration Session "
                    "task_id=%s code=%s retryable=%s",
                    session.task_id,
                    error.code,
                    str(error.retryable).lower(),
                )
                tasks.append(
                    self._task_payload(
                        session,
                        None,
                        state="failed",
                        message=(
                            "暂时无法读取该迁移会话，请稍后刷新。"
                            if error.retryable
                            else "该迁移会话初始化或状态文件不完整，请新建迁移。"
                        ),
                        error=error.detail(),
                    )
                )
        return {"items": tasks}

    def get_task(self, task_id: str, owner_id: str) -> dict[str, object]:
        return self._task_from_session(self._session(task_id, owner_id))

    @staticmethod
    def _artifact_status(value: object = None) -> dict[str, object]:
        data = value if isinstance(value, dict) else {}
        return {
            "state": str(data.get("state") or "none"),
            "previewReady": bool(data.get("preview_ready")),
            "downloadReady": bool(data.get("download_ready")),
            "deployReady": bool(data.get("deploy_ready")),
        }

    def _task_payload(
        self,
        session: MigrationSandboxSession,
        request: dict[str, object] | None,
        *,
        state: str = "awaiting_upload",
        message: str = "请上传本地项目 ZIP",
        artifact: object = None,
        analysis: dict[str, object] | None = None,
        confirmation: dict[str, object] | None = None,
        error: object = None,
    ) -> dict[str, object]:
        request = request or {}
        expiry = self._session_expiry(session, request)
        payload: dict[str, object] = {
            "id": session.task_id,
            "state": state,
            "message": message,
            "sourceFileName": str(request.get("source_file_name") or "项目 ZIP"),
            "instruction": str(request.get("instruction") or ""),
            "createdAt": session.created_at or request.get("created_at") or "",
            "expiresAt": _iso_timestamp(expiry) if expiry is not None else "",
            "sessionTtlSeconds": MIGRATION_SESSION_TTL_SECONDS,
            "canModify": state in {"awaiting_upload", "analysis_ready"},
            "canUpload": state == "awaiting_upload",
            "canConfirm": state == "analysis_ready",
            "canStop": state in _ACTIVE_STATES,
            "artifact": self._artifact_status(artifact),
        }
        if analysis is not None:
            payload["analysis"] = analysis
        if confirmation is not None:
            payload["confirmation"] = confirmation
        if isinstance(error, dict):
            payload["error"] = error
        return payload

    @staticmethod
    def _session_expiry(
        session: MigrationSandboxSession,
        request: dict[str, object] | None = None,
    ) -> float | None:
        explicit = _timestamp(session.expire_at)
        if explicit is not None:
            candidates = [explicit]
        else:
            candidates = []
        created = _timestamp(session.created_at)
        if created is not None:
            candidates.append(created + MIGRATION_SESSION_TTL_SECONDS)
        request_created = _timestamp((request or {}).get("created_at"))
        if request_created is not None:
            candidates.append(request_created + MIGRATION_SESSION_TTL_SECONDS)
        return min(candidates) if candidates else None

    def _session_expired(
        self,
        session: MigrationSandboxSession,
        request: dict[str, object] | None = None,
    ) -> bool:
        expiry = self._session_expiry(session, request)
        return expiry is not None and self._clock() >= expiry

    def _task_from_session(
        self,
        session: MigrationSandboxSession,
    ) -> dict[str, object]:
        if session.released or not session.endpoint or self._session_expired(session):
            return self._task_payload(
                session,
                None,
                state="expired",
                message="Dev Sandbox 已超过 1 小时 TTL，迁移内容和产物不可再访问。",
            )
        request = self._read_json(session, _REQUEST_PATH)
        if request is None:
            raise MigrationError(
                "MIGRATION_REQUEST_INVALID",
                "迁移请求文件不存在。",
                status_code=502,
            )
        request = self._validated_request(request, session.task_id)
        if self._session_expired(session, request):
            return self._task_payload(
                session,
                request,
                state="expired",
                message="Dev Sandbox 已超过 1 小时 TTL，迁移内容和产物不可再访问。",
            )
        stopped = self._read_json(session, _STOPPED_PATH, optional=True)
        if stopped is not None:
            try:
                stopped = validate_stopped_status(stopped)
            except MigrationContractError as error:
                raise MigrationError(
                    "MIGRATION_STOP_STATE_INVALID",
                    "迁移终止状态无效。",
                    status_code=502,
                ) from error
            return self._task_payload(
                session,
                request,
                state="cancelled",
                message=str(stopped.get("message") or "迁移已终止"),
            )
        confirmation = self._read_json(session, _CONFIRMATION_PATH, optional=True)
        if confirmation is not None:
            confirmation = self._validated_confirmation(
                confirmation,
                session.task_id,
            )
        delivery = self._read_json(session, _DELIVERY_STATUS_PATH, optional=True)
        if delivery is not None:
            try:
                delivery = validate_delivery_status(
                    delivery,
                    expected_run_id=session.task_id,
                )
            except MigrationContractError as error:
                raise MigrationError(
                    "MIGRATION_DELIVERY_INVALID",
                    "迁移交付状态无效。",
                    status_code=502,
                ) from error
            state = str(delivery["state"])
            return self._task_payload(
                session,
                request,
                state=state,
                message=str(delivery.get("message") or "正在迁移项目"),
                artifact=delivery.get("artifact"),
                confirmation=confirmation,
                error=delivery.get("error"),
            )
        process_exit = self._read_json(session, _PROCESS_EXIT_PATH, optional=True)
        if process_exit is not None:
            process_exit = self._validated_process_exit(process_exit)
            exit_code = process_exit["exit_code"]
            if exit_code != 0:
                return self._task_payload(
                    session,
                    request,
                    state="failed",
                    message="迁移命令未成功完成，请查看日志。",
                    confirmation=confirmation,
                    error={
                        "code": "MIGRATION_PROCESS_FAILED",
                        "message": "AgentKit CLI 迁移命令执行失败。",
                        "retryable": False,
                    },
                )
            return self._task_payload(
                session,
                request,
                state="failed",
                message="迁移命令已结束，但没有生成交付状态。",
                confirmation=confirmation,
                error={
                    "code": "MIGRATION_DELIVERY_MISSING",
                    "message": "AgentKit CLI 未生成完整的迁移交付状态。",
                    "retryable": False,
                },
            )
        if confirmation is not None:
            return self._task_payload(
                session,
                request,
                state="migrating",
                message="正在启动 AgentKit CLI 迁移",
                confirmation=confirmation,
            )
        analysis_status = self._read_json(
            session,
            _ANALYSIS_STATUS_PATH,
            optional=True,
        )
        if analysis_status is not None:
            try:
                analysis_status = validate_analysis_status(analysis_status)
            except MigrationContractError as error:
                raise MigrationError(
                    "MIGRATION_ANALYSIS_STATE_INVALID",
                    "Codex 分析状态无效。",
                    status_code=502,
                ) from error
            analysis_state = str(analysis_status.get("state") or "")
            if analysis_state == "ready":
                analysis = self._read_json(session, _ANALYSIS_RESULT_PATH)
                try:
                    analysis = validate_analysis_result(analysis)
                except MigrationContractError as error:
                    raise MigrationError(
                        "MIGRATION_ANALYSIS_INVALID",
                        "Codex 分析结果格式无效。",
                        status_code=502,
                    ) from error
                return self._task_payload(
                    session,
                    request,
                    state="analysis_ready",
                    message=str(analysis_status.get("message") or "请确认迁移方式"),
                    analysis=analysis,
                )
            if analysis_state == "failed":
                return self._task_payload(
                    session,
                    request,
                    state="failed",
                    message=str(analysis_status.get("message") or "项目分析未完成"),
                    error=analysis_status.get("error"),
                )
            if analysis_state == "analyzing":
                analysis_exit = self._read_json(
                    session,
                    _ANALYSIS_PROCESS_EXIT_PATH,
                    optional=True,
                )
                if analysis_exit is not None:
                    analysis_exit = self._validated_process_exit(
                        analysis_exit,
                        analysis=True,
                    )
                    exit_code = analysis_exit["exit_code"]
                    result_missing = exit_code == 0
                    return self._task_payload(
                        session,
                        request,
                        state="failed",
                        message=(
                            "项目分析已结束，但没有生成分析结果。"
                            if result_missing
                            else "项目分析未成功完成，请查看日志。"
                        ),
                        error={
                            "code": (
                                "MIGRATION_ANALYSIS_RESULT_MISSING"
                                if result_missing
                                else "MIGRATION_ANALYSIS_FAILED"
                            ),
                            "message": (
                                "Codex 未生成完整的项目分析结果。"
                                if result_missing
                                else "Codex 只读项目分析执行失败。"
                            ),
                            "retryable": False,
                        },
                    )
                return self._task_payload(
                    session,
                    request,
                    state="analyzing",
                    message=str(analysis_status.get("message") or "正在分析项目"),
                )
            raise MigrationError(
                "MIGRATION_ANALYSIS_STATE_INVALID",
                "Codex 分析状态无效。",
                status_code=502,
            )
        source = self._read_json(session, _SOURCE_STATUS_PATH, optional=True)
        if source is not None:
            self._validated_source(source)
            return self._task_payload(
                session,
                request,
                state="awaiting_upload",
                message="项目已上传，请重新选择同一 ZIP 继续启动分析。",
            )
        return self._task_payload(session, request)

    def confirm(
        self,
        task_id: str,
        owner_id: str,
        body: ConfirmMigrationBody,
    ) -> dict[str, object]:
        session = self._session(task_id, owner_id)
        task = self._task_from_session(session)
        if task["state"] != "analysis_ready":
            raise MigrationError(
                "MIGRATION_DECISION_LOCKED",
                (
                    "迁移执行中不能修改迁移方式；请等待完成或终止当前迁移。"
                    if task["state"] in _ACTIVE_STATES
                    else "请等待项目分析完成后再确认迁移方式。"
                ),
                status_code=409,
            )
        request = self._read_json(session, _REQUEST_PATH)
        analysis = self._read_json(session, _ANALYSIS_RESULT_PATH)
        if request is None or analysis is None:
            raise MigrationError(
                "MIGRATION_ANALYSIS_MISSING",
                "项目分析结果不存在。",
                status_code=502,
            )
        request = self._validated_request(request, task_id)
        try:
            analysis = validate_analysis_result(analysis)
        except MigrationContractError as error:
            raise MigrationError(
                "MIGRATION_ANALYSIS_INVALID",
                "Codex 分析结果格式无效。",
                status_code=502,
            ) from error
        source = self._read_json(session, _SOURCE_STATUS_PATH)
        if source is None:
            raise MigrationError(
                "MIGRATION_SOURCE_STATE_INVALID",
                "上传项目的来源状态无效。",
                status_code=502,
            )
        source = self._validated_source(source)
        source_sha256 = str(source["sha256"])
        confirmation = {
            "schema_version": 1,
            "task_id": task_id,
            "source_archive_sha256": source_sha256,
            "framework": body.framework,
            "entry": body.entry,
            "app_name": body.app_name,
            "instruction": body.instruction,
            "answers": body.answers,
            "confirmed_at": int(self._clock()),
        }
        confirmation_content = _json_bytes(confirmation)
        confirmation_sha = hashlib.sha256(confirmation_content).hexdigest()
        confirmation_candidate = (
            f"{MIGRATION_ROOT}/state/.confirmation-{confirmation_sha}.json"
        )
        instruction_content = _migration_instruction(
            request,
            confirmation,
            analysis,
        ).encode("utf-8")
        instruction_sha = hashlib.sha256(instruction_content).hexdigest()
        instruction_candidate = (
            f"{MIGRATION_ROOT}/state/.instructions-{instruction_sha}.md"
        )
        self._put(
            session,
            confirmation_candidate,
            confirmation_content,
            media_type="application/json",
        )
        self._put(
            session,
            instruction_candidate,
            instruction_content,
            media_type="text/markdown",
        )
        self._execute(
            session,
            _start_migration_command(
                task_id,
                confirmation,
                confirmation_sha,
                confirmation_candidate,
                instruction_candidate,
            ),
            operation="start_migration",
            timeout_seconds=_FILE_OPERATION_TIMEOUT_SECONDS,
        )
        return self.get_task(task_id, owner_id)

    def stop(self, task_id: str, owner_id: str) -> dict[str, object]:
        session = self._session(task_id, owner_id)
        task = self._task_from_session(session)
        if task["state"] == "expired":
            raise MigrationError(
                "MIGRATION_SESSION_EXPIRED",
                "Dev Sandbox 已清理，无法再终止任务。",
                status_code=410,
                retryable=False,
            )
        if task["state"] not in _ACTIVE_STATES:
            raise MigrationError(
                "MIGRATION_NOT_RUNNING",
                "当前迁移不处于可终止状态。",
                status_code=409,
            )
        self._execute(
            session,
            _stop_command(),
            operation="stop",
            timeout_seconds=30,
        )
        return self.get_task(task_id, owner_id)

    def artifact(self, task_id: str, owner_id: str) -> dict[str, object]:
        session = self._session(task_id, owner_id)
        task = self._task_from_session(session)
        return self._artifact_result(session, task, readiness="previewReady")

    def _artifact_result(
        self,
        session: MigrationSandboxSession,
        task: dict[str, object],
        *,
        readiness: str,
    ) -> dict[str, object]:
        artifact = task.get("artifact")
        if (
            not isinstance(artifact, dict)
            or not artifact.get(readiness)
            or task["state"] not in {"succeeded", "succeeded_with_warnings", "partial"}
        ):
            raise MigrationError(
                "MIGRATION_ARTIFACT_NOT_READY",
                "迁移产物尚未准备完成。",
                status_code=409,
            )
        result = self._read_json(session, _DELIVERY_RESULT_PATH)
        if result is None:
            raise MigrationError(
                "MIGRATION_ARTIFACT_MISSING",
                "迁移产物清单不存在。",
                status_code=502,
            )
        confirmation_content = self._read(
            session,
            _CONFIRMATION_PATH,
            max_bytes=_MAX_PROVENANCE_BYTES,
        )
        if confirmation_content is None:
            raise MigrationError(
                "MIGRATION_CONFIRMATION_MISSING",
                "迁移确认文件不存在。",
                status_code=502,
            )
        source = self._read_json(session, _SOURCE_STATUS_PATH)
        if source is None:
            raise MigrationError(
                "MIGRATION_SOURCE_STATE_INVALID",
                "上传项目的来源状态无效。",
                status_code=502,
            )
        source = self._validated_source(source)
        source_sha256 = str(source["sha256"])
        try:
            result = validate_delivery_result(
                result,
                expected_run_id=session.task_id,
                expected_status=str(task["state"]),
            )
        except MigrationContractError as error:
            raise MigrationError(
                "MIGRATION_ARTIFACT_INVALID",
                "AgentKit CLI 产物清单格式无效。",
                status_code=502,
            ) from error
        self._validate_result_binding(
            result,
            expected_provenance_sha256=hashlib.sha256(confirmation_content).hexdigest(),
            expected_source_archive_sha256=source_sha256,
            confirmation=task.get("confirmation"),
        )
        return result

    @staticmethod
    def _validate_result_binding(
        result: dict[str, object],
        *,
        expected_provenance_sha256: str,
        expected_source_archive_sha256: str,
        confirmation: object,
    ) -> None:
        migration = result.get("migration")
        assert isinstance(migration, dict)
        if migration.get("provenance_sha256") != expected_provenance_sha256:
            raise MigrationError(
                "MIGRATION_ARTIFACT_PROVENANCE_MISMATCH",
                "AgentKit CLI 产物与当前迁移确认不匹配。",
                status_code=502,
            )
        if not isinstance(confirmation, dict):
            raise MigrationError(
                "MIGRATION_CONFIRMATION_INVALID",
                "迁移确认状态无效。",
                status_code=502,
            )
        if confirmation.get("source_archive_sha256") != expected_source_archive_sha256:
            raise MigrationError(
                "MIGRATION_ARTIFACT_SOURCE_MISMATCH",
                "AgentKit CLI 产物与当前上传项目不匹配。",
                status_code=502,
            )
        framework = confirmation.get("framework")
        expected_engine = (
            "structured" if framework in STRUCTURED_MIGRATION_FRAMEWORKS else "agentic"
        )
        if (
            migration.get("framework") != framework
            or migration.get("engine") != expected_engine
            or (
                expected_engine == "structured"
                and migration.get("entry") != confirmation.get("entry")
            )
        ):
            raise MigrationError(
                "MIGRATION_ARTIFACT_DECISION_MISMATCH",
                "AgentKit CLI 产物与已确认的迁移方式不匹配。",
                status_code=502,
            )

    def preview_file(
        self,
        task_id: str,
        owner_id: str,
        path: str,
    ) -> tuple[bytes, str]:
        session = self._session(task_id, owner_id)
        task = self._task_from_session(session)
        result = self._artifact_result(session, task, readiness="previewReady")
        normalized = PurePosixPath(path).as_posix()
        files = result.get("files")
        if not isinstance(files, list):
            raise MigrationError(
                "MIGRATION_ARTIFACT_INVALID",
                "AgentKit CLI 产物文件清单格式无效。",
                status_code=502,
            )
        descriptor = next(
            (
                item
                for item in files
                if isinstance(item, dict) and item.get("path") == normalized
            ),
            None,
        )
        if descriptor is None:
            raise MigrationError(
                "MIGRATION_ARTIFACT_FILE_NOT_FOUND",
                "迁移产物中不存在该文件。",
                status_code=404,
            )
        size = descriptor["size"]
        if not isinstance(size, int) or size > _MAX_PREVIEW_BYTES:
            raise MigrationError(
                "MIGRATION_ARTIFACT_FILE_TOO_LARGE",
                "该文件超过 2 MiB，无法在线预览，请下载产物后查看。",
                status_code=413,
            )
        migration = result["migration"]
        assert isinstance(migration, dict)
        project_root = (
            f"{MIGRATION_ROOT}/workspace/source"
            if migration.get("engine") == "structured"
            else f"{MIGRATION_ROOT}/output/veadk"
        )
        content = self._read(
            session,
            f"{project_root}/{normalized}",
            max_bytes=_MAX_PREVIEW_BYTES,
        )
        if content is None:
            raise MigrationError(
                "MIGRATION_ARTIFACT_FILE_NOT_FOUND",
                "迁移产物文件不存在。",
                status_code=404,
            )
        if (
            len(content) != size
            or hashlib.sha256(content).hexdigest() != descriptor["sha256"]
        ):
            raise MigrationError(
                "MIGRATION_ARTIFACT_INTEGRITY_FAILED",
                "迁移产物文件完整性校验失败。",
                status_code=502,
            )
        media_type = mimetypes.guess_type(normalized)[0] or "application/octet-stream"
        return content, media_type

    def download(
        self,
        task_id: str,
        owner_id: str,
    ) -> tuple[bytes, str]:
        session = self._session(task_id, owner_id)
        task = self._task_from_session(session)
        result = self._artifact_result(session, task, readiness="downloadReady")
        content = self._verified_artifact_content(session, result)
        request = self._read_json(session, _REQUEST_PATH)
        if request is None:
            raise MigrationError(
                "MIGRATION_REQUEST_INVALID",
                "迁移请求文件不存在。",
                status_code=502,
            )
        request = self._validated_request(request, task_id)
        source_name = str(request.get("source_file_name") or "project.zip")
        stem = source_name[:-4] if source_name.lower().endswith(".zip") else source_name
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-") or "project"
        return content, f"{safe_stem}-migrated.zip"

    def _verified_artifact_content(
        self,
        session: MigrationSandboxSession,
        result: dict[str, object],
    ) -> bytes:
        descriptor = result["artifact"]
        assert isinstance(descriptor, dict)
        content = self._read(
            session,
            _DELIVERY_ARTIFACT_PATH,
            max_bytes=_MAX_ARTIFACT_BYTES,
        )
        if content is None:
            raise MigrationError(
                "MIGRATION_ARTIFACT_MISSING",
                "迁移产物不存在。",
                status_code=502,
            )
        if (
            len(content) != descriptor["size"]
            or hashlib.sha256(content).hexdigest() != descriptor["sha256"]
        ):
            raise MigrationError(
                "MIGRATION_ARTIFACT_INTEGRITY_FAILED",
                "迁移产物完整性校验失败。",
                status_code=502,
            )
        return content

    def materialize_deployment(
        self,
        task_id: str,
        owner_id: str,
        target: Path,
    ) -> str:
        session = self._session(task_id, owner_id)
        task = self._task_from_session(session)
        artifact_status = task.get("artifact")
        if (
            task.get("state") not in {"succeeded", "succeeded_with_warnings"}
            or not isinstance(artifact_status, dict)
            or not artifact_status.get("deployReady")
        ):
            raise MigrationError(
                "MIGRATION_ARTIFACT_NOT_DEPLOYABLE",
                "迁移产物未通过部署校验，无法部署到 Runtime。",
                status_code=409,
            )
        result = self._artifact_result(session, task, readiness="deployReady")
        content = self._verified_artifact_content(session, result)
        try:
            return extract_migration_source(target, content, result)
        except DeploymentSourceError as error:
            raise MigrationError(
                "MIGRATION_ARTIFACT_INTEGRITY_FAILED",
                str(error),
                status_code=502,
                retryable=False,
            ) from error

    def delete(self, task_id: str, owner_id: str) -> None:
        session = self._session(task_id, owner_id)
        try:
            self._gateway.delete_session(session)
        except MigrationGatewayError as error:
            raise self._translate(error) from error


__all__ = [
    "MIGRATION_ROOT",
    "MIGRATION_SESSION_TTL_SECONDS",
    "MIGRATION_UPLOAD_MAX_BYTES",
    "MigrationError",
    "MigrationService",
    "SourceArchiveSummary",
    "validate_source_archive",
]
