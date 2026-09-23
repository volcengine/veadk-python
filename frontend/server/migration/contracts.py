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

"""Strict contracts for state files produced inside a Migration Session."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath

from frontend.server.source_project_limits import (
    SOURCE_PROJECT_MAX_BYTES,
    SOURCE_PROJECT_MAX_FILES,
)

from .models import (
    MIGRATION_FRAMEWORKS,
    STRUCTURED_MIGRATION_FRAMEWORKS,
    is_valid_model_id,
    is_valid_structured_entry,
)
from .evaluation.dimensions import EVALUATION_DIMENSION_IDS, STANDARD_DIMENSION_IDS

_MAX_PATH_BYTES = 4 * 1024
_MAX_PATH_DEPTH = 64
_MAX_TEXT_LENGTH = 20_000
_MAX_DELIVERY_FILES = SOURCE_PROJECT_MAX_FILES
_MAX_DELIVERY_BYTES = SOURCE_PROJECT_MAX_BYTES
_MAX_DELIVERY_FILE_BYTES = SOURCE_PROJECT_MAX_BYTES
_MAX_ARTIFACT_BYTES = SOURCE_PROJECT_MAX_BYTES
_MAX_SOURCE_BYTES = SOURCE_PROJECT_MAX_BYTES
_MAX_SOURCE_EXPANDED_BYTES = SOURCE_PROJECT_MAX_BYTES
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FILE_MODE_RE = re.compile(r"^0[0-7]{1,3}$")
_ENVIRONMENT_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TASK_ID_RE = re.compile(r"^migration-v1-[0-9a-f]{32}$")
_SOURCE_FILE_NAME_RE = re.compile(
    r"^[^/\\\x00-\x1f\x7f]{1,255}\.zip$",
    re.IGNORECASE,
)
_APP_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_PYTHON_OBJECT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_ACTIVE_DELIVERY_STATES = {"migrating", "validating", "packaging"}
_TERMINAL_DELIVERY_STATES = {
    "succeeded",
    "succeeded_with_warnings",
    "partial",
}


class MigrationContractError(ValueError):
    """A remote state file does not match its versioned contract."""


def _exact_keys(
    value: dict[str, object],
    *,
    required: set[str],
    optional: set[str] | frozenset[str] = frozenset(),
) -> None:
    keys = set(value)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        raise MigrationContractError("unexpected object fields")


def _text(
    value: object,
    *,
    allow_empty: bool = True,
    maximum: int = _MAX_TEXT_LENGTH,
) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise MigrationContractError("invalid text")
    if not allow_empty and not value.strip():
        raise MigrationContractError("empty text")
    return value


def _string_list(
    value: object,
    *,
    maximum_items: int,
    allow_empty_items: bool = False,
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise MigrationContractError("invalid string list")
    return [_text(item, allow_empty=allow_empty_items, maximum=4_000) for item in value]


def _relative_path(value: object) -> str:
    text = _text(value, allow_empty=False, maximum=_MAX_PATH_BYTES)
    path = PurePosixPath(text)
    if (
        not path.parts
        or text == "."
        or text != path.as_posix()
        or path.is_absolute()
        or "." in path.parts
        or ".." in path.parts
        or "\\" in text
        or len(path.parts) > _MAX_PATH_DEPTH
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
        or len(text.encode("utf-8")) > _MAX_PATH_BYTES
    ):
        raise MigrationContractError("unsafe relative path")
    return text


def _sha256(value: object) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise MigrationContractError("invalid sha256")
    return value


def _bounded_integer(
    value: object,
    *,
    minimum: int = 0,
    maximum: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise MigrationContractError("invalid integer")
    return value


def _timestamp_text(value: object) -> str:
    text = _text(value, allow_empty=False, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise MigrationContractError("invalid timestamp") from error
    if parsed.tzinfo is None:
        raise MigrationContractError("timestamp is missing a timezone")
    return text


def _reject_path_collisions(paths: set[str]) -> None:
    for value in paths:
        path = PurePosixPath(value)
        for parent in path.parents:
            if parent == PurePosixPath("."):
                break
            if parent.as_posix().casefold() in paths:
                raise MigrationContractError("file and directory paths collide")


def _evidence_list(value: object, *, maximum: int = 100) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) > maximum:
        raise MigrationContractError("invalid evidence list")
    evidence: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise MigrationContractError("invalid evidence")
        _exact_keys(item, required={"path", "line", "reason"})
        _relative_path(item.get("path"))
        _bounded_integer(item.get("line"), minimum=1, maximum=10_000_000)
        _text(item.get("reason"), allow_empty=False, maximum=4_000)
        evidence.append(item)
    return evidence


def _framework(value: object) -> str:
    if value not in MIGRATION_FRAMEWORKS:
        raise MigrationContractError("unsupported framework")
    return str(value)


def validate_migration_request(
    value: object,
    *,
    expected_task_id: str,
    expected_ttl_seconds: int,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MigrationContractError("migration request must be an object")
    _exact_keys(
        value,
        required={
            "schema_version",
            "task_id",
            "source_file_name",
            "instruction",
            "session_ttl_seconds",
            "created_at",
        },
        optional={"model_id", "evaluation"},
    )
    if (
        value.get("schema_version") != 1
        or value.get("task_id") != expected_task_id
        or not _TASK_ID_RE.fullmatch(expected_task_id)
        or value.get("session_ttl_seconds") != expected_ttl_seconds
    ):
        raise MigrationContractError("invalid migration request identity")
    source_file_name = value.get("source_file_name")
    if not isinstance(source_file_name, str) or not _SOURCE_FILE_NAME_RE.fullmatch(
        source_file_name
    ):
        raise MigrationContractError("invalid source file name")
    _text(value.get("instruction"), maximum=_MAX_TEXT_LENGTH)
    if "model_id" in value and not is_valid_model_id(value.get("model_id")):
        raise MigrationContractError("invalid model id")
    evaluation = value.get("evaluation")
    if evaluation is not None:
        if not isinstance(evaluation, dict):
            raise MigrationContractError("invalid evaluation config")
        _exact_keys(
            evaluation,
            required={"enabled", "preset", "dimensions", "locale"},
        )
        enabled = evaluation.get("enabled")
        preset = evaluation.get("preset")
        dimensions = evaluation.get("dimensions")
        locale = evaluation.get("locale")
        if (
            enabled is not True
            or preset not in {"standard", "custom"}
            or locale not in {"zh-CN", "en-US"}
            or not isinstance(dimensions, list)
            or not dimensions
            or len(set(str(item) for item in dimensions)) != len(dimensions)
            or any(item not in EVALUATION_DIMENSION_IDS for item in dimensions)
            or (preset == "standard" and tuple(dimensions) != STANDARD_DIMENSION_IDS)
        ):
            raise MigrationContractError("invalid evaluation config")
    created_at = value.get("created_at")
    if isinstance(created_at, str):
        _timestamp_text(created_at)
    else:
        _bounded_integer(created_at, maximum=10**12)
    return {str(key): item for key, item in value.items()}


def validate_source_status(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MigrationContractError("source status must be an object")
    _exact_keys(
        value,
        required={
            "schema_version",
            "sha256",
            "size",
            "file_count",
            "expanded_bytes",
        },
    )
    if value.get("schema_version") != 1:
        raise MigrationContractError("unsupported source status schema")
    _sha256(value.get("sha256"))
    _bounded_integer(
        value.get("size"),
        minimum=1,
        maximum=_MAX_SOURCE_BYTES,
    )
    _bounded_integer(
        value.get("file_count"),
        minimum=1,
        maximum=_MAX_DELIVERY_FILES,
    )
    _bounded_integer(
        value.get("expanded_bytes"),
        maximum=_MAX_SOURCE_EXPANDED_BYTES,
    )
    return {str(key): item for key, item in value.items()}


def validate_detection_report(value: object) -> dict[str, object]:
    """Validate the model-free detection report written before analysis runs.

    Studio authors this document, so it is checked strictly; the analysis verdict is
    later measured against the file inventory it carries.
    """
    if not isinstance(value, dict):
        raise MigrationContractError("detection report must be an object")
    _exact_keys(
        value,
        required={
            "schema_version",
            "files",
            "documents",
            "candidates",
            "unreadable",
            "degraded",
            "degraded_reason",
        },
    )
    if value.get("schema_version") != 1:
        raise MigrationContractError("unsupported detection report schema")
    files = value.get("files")
    if not isinstance(files, dict):
        raise MigrationContractError("invalid detection files")
    _exact_keys(files, required={"count", "listed"})
    _bounded_integer(files.get("count"), maximum=_MAX_DELIVERY_FILES)
    listed = files.get("listed")
    if not isinstance(listed, list) or len(listed) > 1_000:
        raise MigrationContractError("invalid detection file list")
    for item in listed:
        _relative_path(item)

    documents = value.get("documents")
    if not isinstance(documents, list) or len(documents) > 1_000:
        raise MigrationContractError("invalid detection documents")
    for item in documents:
        if not isinstance(item, dict):
            raise MigrationContractError("invalid detection document")
        _exact_keys(
            item,
            required={"path", "format", "status", "dsl", "signals"},
            optional={"parse_error"},
        )
        _relative_path(item.get("path"))
        if item.get("status") not in {"parsed", "unparsed"}:
            raise MigrationContractError("invalid detection document status")
        _text(item.get("format"), allow_empty=False, maximum=32)
        _text(item.get("dsl"), maximum=64)
        if "parse_error" in item:
            _text(item.get("parse_error"), maximum=64)
        signals = item.get("signals")
        if not isinstance(signals, list) or len(signals) > 100:
            raise MigrationContractError("invalid detection signals")
        for signal in signals:
            if not isinstance(signal, dict):
                raise MigrationContractError("invalid detection signal")
            _exact_keys(signal, required={"path", "line", "reason"})
            _text(signal.get("path"), maximum=_MAX_PATH_BYTES)
            _bounded_integer(signal.get("line"), minimum=1, maximum=10_000_000)
            _text(signal.get("reason"), allow_empty=False, maximum=4_000)

    candidates = value.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 20:
        raise MigrationContractError("invalid detection candidates")
    for item in candidates:
        if not isinstance(item, dict):
            raise MigrationContractError("invalid detection candidate")
        _exact_keys(item, required={"id", "confidence", "evidence"})
        _framework(item.get("id"))
        if item.get("confidence") not in {"high", "medium", "low"}:
            raise MigrationContractError("invalid detection candidate")
        _evidence_list(item.get("evidence"))

    unreadable = value.get("unreadable")
    if not isinstance(unreadable, list) or len(unreadable) > 1_000:
        raise MigrationContractError("invalid detection unreadable list")
    for item in unreadable:
        if not isinstance(item, dict):
            raise MigrationContractError("invalid detection unreadable entry")
        _exact_keys(item, required={"path", "reason"})
        path = item.get("path")
        if path != "":
            _relative_path(path)
        _text(item.get("reason"), allow_empty=False, maximum=64)

    if not isinstance(value.get("degraded"), bool):
        raise MigrationContractError("invalid detection degraded flag")
    _text(value.get("degraded_reason"), maximum=128)
    return {str(key): item for key, item in value.items()}


def validate_analysis_status(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MigrationContractError("analysis status must be an object")
    _exact_keys(
        value,
        required={"schema_version", "attempt", "state", "message"},
        optional={"error"},
    )
    state = value.get("state")
    if value.get("schema_version") != 1 or state not in {
        "preparing",
        "analyzing",
        "needs_input",
        "ready",
        "failed",
    }:
        raise MigrationContractError("invalid analysis status")
    _bounded_integer(value.get("attempt"), minimum=0, maximum=100)
    _text(value.get("message"), allow_empty=False, maximum=4_000)
    if state == "failed":
        if "error" not in value:
            raise MigrationContractError("failed analysis is missing an error")
        _error(value["error"])
    elif "error" in value:
        raise MigrationContractError("non-failed analysis exposed an error")
    return {str(key): item for key, item in value.items()}


def validate_confirmation(
    value: object,
    *,
    expected_task_id: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MigrationContractError("confirmation must be an object")
    _exact_keys(
        value,
        required={
            "schema_version",
            "task_id",
            "analysis_attempt",
            "analysis_sha256",
            "input_sha256",
            "execution_model",
            "framework",
            "entry",
            "app_name",
            "instruction",
            "boundary_confirmed",
            "confirmed_by",
            "confirmed_at",
        },
    )
    if (
        value.get("schema_version") != 1
        or value.get("task_id") != expected_task_id
        or not _TASK_ID_RE.fullmatch(expected_task_id)
    ):
        raise MigrationContractError("invalid confirmation identity")
    _bounded_integer(value.get("analysis_attempt"), minimum=1, maximum=100)
    _sha256(value.get("analysis_sha256"))
    _sha256(value.get("input_sha256"))
    framework = _framework(value.get("framework"))
    expected_execution_model = (
        "structured" if framework in STRUCTURED_MIGRATION_FRAMEWORKS else "agentic"
    )
    if value.get("execution_model") != expected_execution_model:
        raise MigrationContractError("invalid migration execution model")
    entry = value.get("entry")
    if framework in STRUCTURED_MIGRATION_FRAMEWORKS:
        if not is_valid_structured_entry(entry):
            raise MigrationContractError("invalid structured confirmation")
    elif entry is not None:
        raise MigrationContractError("agentic confirmation has an entry")
    app_name = value.get("app_name")
    if not isinstance(app_name, str) or not _APP_NAME_RE.fullmatch(app_name):
        raise MigrationContractError("invalid app name")
    _text(value.get("instruction"), maximum=_MAX_TEXT_LENGTH)
    if value.get("boundary_confirmed") is not True:
        raise MigrationContractError("migration boundary was not confirmed")
    _text(value.get("confirmed_by"), allow_empty=False, maximum=256)
    _bounded_integer(value.get("confirmed_at"), maximum=10**12)
    return {str(key): item for key, item in value.items()}


def validate_process_exit(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MigrationContractError("process exit must be an object")
    _exact_keys(
        value,
        required={"schema_version", "exit_code"},
        optional={"finished_at"},
    )
    if value.get("schema_version") != 1:
        raise MigrationContractError("unsupported process exit schema")
    _bounded_integer(value.get("exit_code"), maximum=255)
    if "finished_at" in value:
        _bounded_integer(value.get("finished_at"), maximum=10**12)
    return {str(key): item for key, item in value.items()}


def validate_migration_driver(
    value: object,
    *,
    expected_run_id: str,
) -> dict[str, object]:
    """Validate the delivery driver lease, including the published artifact.

    The record is written inside the Sandbox by the launch script that supervises the
    migration CLI.  It lets Studio tell a driver that is still working from one whose
    process disappeared, and it carries the artifact digest computed right after the
    CLI exited, so the bytes Studio later pulls can be checked against it.

    ``lost`` is the heartbeat's own verdict that the CLI it was watching is gone: the
    run will never write its result, but the agent's work may still be on disk.
    """
    if not isinstance(value, dict):
        raise MigrationContractError("driver lease must be an object")
    _exact_keys(
        value,
        required={
            "schema_version",
            "run_id",
            "state",
            "heartbeat_at",
            "finished_at",
            "exit_code",
            "artifact",
        },
    )
    state = value.get("state")
    if (
        value.get("schema_version") != 1
        or value.get("run_id") != expected_run_id
        or state not in {"running", "lost", "finished"}
    ):
        raise MigrationContractError("invalid driver lease identity")
    _bounded_integer(value.get("heartbeat_at"), maximum=10**12)
    finished_at = value.get("finished_at")
    exit_code = value.get("exit_code")
    artifact = value.get("artifact")
    if state != "finished":
        if finished_at is not None or exit_code is not None or artifact is not None:
            raise MigrationContractError("unfinished driver lease published a result")
    else:
        _bounded_integer(finished_at, maximum=10**12)
        _bounded_integer(exit_code, maximum=255)
        if artifact is not None:
            if not isinstance(artifact, dict):
                raise MigrationContractError("invalid artifact descriptor")
            _exact_keys(artifact, required={"path", "sha256", "size"})
            if artifact.get("path") != "migration-result.zip":
                raise MigrationContractError("invalid artifact path")
            _bounded_integer(artifact.get("size"), maximum=_MAX_ARTIFACT_BYTES)
            _sha256(artifact.get("sha256"))
    return {str(key): item for key, item in value.items()}


def validate_delivery_report(
    value: object,
    *,
    expected_run_id: str,
    expected_state: str,
) -> dict[str, object]:
    """Validate the verdict the closing delivery turn published.

    The turn explains a delivery; it never decides one.  ``expected_state`` is the
    state Studio derived from the Sandbox, and a report that disagrees with it is
    rejected here as well as inside the turn, so a damaged or replayed record cannot
    describe a delivery other than the one the CLI settled.
    """
    if not isinstance(value, dict):
        raise MigrationContractError("delivery report must be an object")
    _exact_keys(
        value,
        required={
            "schema_version",
            "run_id",
            "driver",
            "state",
            "message",
            "warnings",
            "artifact",
            "created_at",
        },
    )
    state = value.get("state")
    if (
        value.get("schema_version") != 1
        or value.get("run_id") != expected_run_id
        or value.get("driver") != "app-server"
        or state != expected_state
        or state not in {"succeeded", "succeeded_with_warnings", "partial", "failed"}
    ):
        raise MigrationContractError("delivery report identity does not match")
    _text(value.get("message"), allow_empty=False, maximum=4_000)
    _string_list(value.get("warnings"), maximum_items=8)
    artifact = value.get("artifact")
    if state == "failed":
        if artifact is not None:
            raise MigrationContractError("failed delivery report published an artifact")
    else:
        if not isinstance(artifact, dict):
            raise MigrationContractError("invalid delivery report artifact")
        _exact_keys(artifact, required={"path", "sha256", "size"})
        if artifact.get("path") != "migration-result.zip":
            raise MigrationContractError("invalid delivery report artifact path")
        _bounded_integer(artifact.get("size"), maximum=_MAX_ARTIFACT_BYTES)
        _sha256(artifact.get("sha256"))
    _timestamp_text(value.get("created_at"))
    return {str(key): item for key, item in value.items()}


def validate_stopped_status(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MigrationContractError("stopped status must be an object")
    _exact_keys(value, required={"schema_version", "state", "message"})
    if value.get("schema_version") != 1 or value.get("state") != "cancelled":
        raise MigrationContractError("invalid stopped status")
    _text(value.get("message"), allow_empty=False, maximum=4_000)
    return {str(key): item for key, item in value.items()}


def validate_analysis_result(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MigrationContractError("analysis must be an object")
    _exact_keys(
        value,
        required={
            "schema_version",
            "status",
            "attempt",
            "input_sha256",
            "summary",
            "frameworks",
            "recommended",
            "entries",
            "boundary",
            "assumptions",
            "questions",
            "warnings",
        },
    )
    status = value.get("status")
    if value.get("schema_version") != 1 or status not in {
        "needs_input",
        "recommendation_ready",
        "unsupported",
    }:
        raise MigrationContractError("unsupported analysis schema")
    _bounded_integer(value.get("attempt"), minimum=1, maximum=100)
    _sha256(value.get("input_sha256"))
    _text(value.get("summary"), allow_empty=False)

    frameworks = value.get("frameworks")
    if not isinstance(frameworks, list) or len(frameworks) > 20:
        raise MigrationContractError("invalid framework candidates")
    seen_frameworks: set[str] = set()
    for item in frameworks:
        if not isinstance(item, dict):
            raise MigrationContractError("invalid framework candidate")
        _exact_keys(item, required={"id", "confidence", "evidence"})
        framework = _framework(item.get("id"))
        if framework in seen_frameworks or item.get("confidence") not in {
            "high",
            "medium",
            "low",
        }:
            raise MigrationContractError("invalid framework candidate")
        seen_frameworks.add(framework)
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or len(evidence) > 100:
            raise MigrationContractError("invalid framework evidence")
        for evidence_item in evidence:
            if not isinstance(evidence_item, dict):
                raise MigrationContractError("invalid framework evidence")
            _exact_keys(evidence_item, required={"path", "line", "reason"})
            _relative_path(evidence_item.get("path"))
            line = evidence_item.get("line")
            if isinstance(line, bool) or not isinstance(line, int) or line < 1:
                raise MigrationContractError("invalid evidence line")
            _text(evidence_item.get("reason"), allow_empty=False, maximum=4_000)

    recommended = value.get("recommended")
    if status == "unsupported":
        if recommended is not None:
            raise MigrationContractError("unsupported analysis has a recommendation")
    else:
        if not isinstance(recommended, dict):
            raise MigrationContractError("analysis recommendation is missing")
        _exact_keys(recommended, required={"framework", "entry", "reason"})
        recommended_framework = _framework(recommended.get("framework"))
        recommended_entry = recommended.get("entry")
        if recommended_entry is not None and (
            recommended_framework not in STRUCTURED_MIGRATION_FRAMEWORKS
            or not is_valid_structured_entry(recommended_entry)
        ):
            raise MigrationContractError("invalid recommended entry")
        _text(recommended.get("reason"), maximum=4_000)

    entries = value.get("entries")
    if not isinstance(entries, list) or len(entries) > 100:
        raise MigrationContractError("invalid entry candidates")
    seen_entries: set[tuple[str, str]] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise MigrationContractError("invalid entry candidate")
        _exact_keys(item, required={"value", "framework", "evidence"})
        framework = _framework(item.get("framework"))
        entry = item.get("value")
        if (
            framework not in STRUCTURED_MIGRATION_FRAMEWORKS
            or not is_valid_structured_entry(entry)
            or (framework, str(entry)) in seen_entries
        ):
            raise MigrationContractError("invalid entry candidate")
        seen_entries.add((framework, str(entry)))
        _text(item.get("evidence"), allow_empty=False, maximum=4_000)
    if status == "unsupported" and entries:
        raise MigrationContractError("unsupported analysis has entry candidates")

    boundary = value.get("boundary")
    if not isinstance(boundary, dict):
        raise MigrationContractError("invalid migration boundary")
    _exact_keys(boundary, required={"include", "exclude"})
    _string_list(boundary.get("include"), maximum_items=200)
    _string_list(boundary.get("exclude"), maximum_items=200)
    _string_list(value.get("assumptions"), maximum_items=100)

    questions = value.get("questions")
    if not isinstance(questions, list) or len(questions) > 50:
        raise MigrationContractError("invalid questions")
    seen_question_ids: set[str] = set()
    for item in questions:
        if not isinstance(item, dict):
            raise MigrationContractError("invalid question")
        _exact_keys(item, required={"id", "prompt", "required"})
        question_id = _text(
            item.get("id"),
            allow_empty=False,
            maximum=128,
        ).strip()
        if question_id in seen_question_ids or not isinstance(
            item.get("required"),
            bool,
        ):
            raise MigrationContractError("invalid question")
        seen_question_ids.add(question_id)
        _text(item.get("prompt"), allow_empty=False, maximum=4_000)
    if status == "needs_input" and (
        not questions
        or not any(
            isinstance(question, dict) and question.get("required") is True
            for question in questions
        )
    ):
        raise MigrationContractError("analysis needing input has no required question")
    if status != "needs_input" and questions:
        raise MigrationContractError("completed analysis still has questions")

    _string_list(value.get("warnings"), maximum_items=100)
    return {str(key): item for key, item in value.items()}


def _error(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MigrationContractError("invalid delivery error")
    _exact_keys(value, required={"code", "message", "retryable"})
    _text(value.get("code"), allow_empty=False, maximum=128)
    _text(value.get("message"), allow_empty=False, maximum=4_000)
    if value.get("retryable") is not False:
        raise MigrationContractError("delivery errors are not retryable")
    return value


def validate_delivery_status(
    value: object,
    *,
    expected_run_id: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MigrationContractError("delivery status must be an object")
    _exact_keys(
        value,
        required={
            "schema_version",
            "run_id",
            "sequence",
            "state",
            "phase",
            "message",
            "artifact",
            "updated_at",
        },
        optional={"error"},
    )
    sequence = value.get("sequence")
    state = value.get("state")
    if (
        value.get("schema_version") != 1
        or value.get("run_id") != expected_run_id
        or isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence < 1
        or state not in _ACTIVE_DELIVERY_STATES | _TERMINAL_DELIVERY_STATES | {"failed"}
    ):
        raise MigrationContractError("invalid delivery status")
    _text(value.get("phase"), allow_empty=False, maximum=128)
    _text(value.get("message"), allow_empty=False, maximum=4_000)
    _timestamp_text(value.get("updated_at"))

    artifact = value.get("artifact")
    if not isinstance(artifact, dict):
        raise MigrationContractError("invalid artifact status")
    _exact_keys(
        artifact,
        required={
            "state",
            "preview_ready",
            "download_ready",
            "deploy_ready",
        },
    )
    if artifact.get("state") not in {"none", "collecting", "ready", "unavailable"}:
        raise MigrationContractError("invalid artifact state")
    readiness = (
        artifact.get("preview_ready"),
        artifact.get("download_ready"),
        artifact.get("deploy_ready"),
    )
    if any(not isinstance(item, bool) for item in readiness):
        raise MigrationContractError("invalid artifact readiness")
    if state in _ACTIVE_DELIVERY_STATES and (
        any(readiness) or artifact.get("state") not in {"none", "collecting"}
    ):
        raise MigrationContractError("active delivery exposed an artifact")
    if state in _TERMINAL_DELIVERY_STATES and (
        artifact.get("state") != "ready"
        or artifact.get("preview_ready") is not True
        or artifact.get("download_ready") is not True
    ):
        raise MigrationContractError("terminal delivery artifact is incomplete")
    if state == "partial" and artifact.get("deploy_ready") is not False:
        raise MigrationContractError("partial delivery cannot be deployed")
    if state == "failed" and (
        artifact.get("state") != "unavailable" or any(readiness) or "error" not in value
    ):
        raise MigrationContractError("failed delivery state is inconsistent")
    if "error" in value:
        _error(value["error"])
    return {str(key): item for key, item in value.items()}


def validate_delivery_result(
    value: object,
    *,
    expected_run_id: str,
    expected_status: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MigrationContractError("delivery result must be an object")
    _exact_keys(
        value,
        required={
            "schema_version",
            "run_id",
            "cli",
            "migration",
            "status",
            "files",
            "startup",
            "environment",
            "verification",
            "warnings",
            "report",
            "artifact",
            "created_at",
        },
    )
    if (
        value.get("schema_version") != 1
        or value.get("run_id") != expected_run_id
        or value.get("status") != expected_status
        or expected_status not in _TERMINAL_DELIVERY_STATES
    ):
        raise MigrationContractError("delivery result identity does not match")

    cli = value.get("cli")
    if not isinstance(cli, dict):
        raise MigrationContractError("invalid cli descriptor")
    _exact_keys(cli, required={"name", "version"})
    if cli.get("name") != "agentkit-cli":
        raise MigrationContractError("invalid cli name")
    _text(cli.get("version"), allow_empty=False, maximum=128)

    migration = value.get("migration")
    if not isinstance(migration, dict):
        raise MigrationContractError("invalid migration descriptor")
    _exact_keys(
        migration,
        required={
            "engine",
            "framework",
            "source_sha256",
            "provenance_sha256",
        },
        optional={"entry"},
    )
    if migration.get("engine") not in {"structured", "agentic"}:
        raise MigrationContractError("invalid migration engine")
    framework = _framework(migration.get("framework"))
    _sha256(migration.get("source_sha256"))
    _sha256(migration.get("provenance_sha256"))
    entry = migration.get("entry")
    if migration["engine"] == "structured":
        if (
            framework not in STRUCTURED_MIGRATION_FRAMEWORKS
            or not is_valid_structured_entry(entry)
        ):
            raise MigrationContractError("invalid structured migration")
    elif framework in STRUCTURED_MIGRATION_FRAMEWORKS or entry is not None:
        raise MigrationContractError("invalid agentic migration")

    files = value.get("files")
    if not isinstance(files, list) or not files or len(files) > _MAX_DELIVERY_FILES:
        raise MigrationContractError("invalid delivery files")
    file_paths: set[str] = set()
    total_bytes = 0
    for item in files:
        if not isinstance(item, dict):
            raise MigrationContractError("invalid delivery file")
        _exact_keys(item, required={"path", "size", "sha256", "mode"})
        path = _relative_path(item.get("path"))
        folded_path = path.casefold()
        if folded_path in file_paths:
            raise MigrationContractError("duplicate delivery file")
        file_paths.add(folded_path)
        total_bytes += _bounded_integer(
            item.get("size"),
            maximum=_MAX_DELIVERY_FILE_BYTES,
        )
        if total_bytes > _MAX_DELIVERY_BYTES:
            raise MigrationContractError("delivery files exceed size limit")
        _sha256(item.get("sha256"))
        mode = item.get("mode")
        if not isinstance(mode, str) or not _FILE_MODE_RE.fullmatch(mode):
            raise MigrationContractError("invalid delivery file mode")
    _reject_path_collisions(file_paths)

    startup = value.get("startup")
    if not isinstance(startup, dict):
        raise MigrationContractError("invalid startup descriptor")
    _exact_keys(
        startup,
        required={"module", "object"},
        optional={"command"},
    )
    startup_module = _relative_path(startup.get("module"))
    startup_object = startup.get("object")
    if (
        startup_module.casefold() not in file_paths
        or not isinstance(startup_object, str)
        or not _PYTHON_OBJECT_RE.fullmatch(startup_object)
    ):
        raise MigrationContractError("invalid startup descriptor")
    if "command" in startup:
        command = _string_list(
            startup["command"],
            maximum_items=100,
            allow_empty_items=False,
        )
        if not command:
            raise MigrationContractError("empty startup command")

    environment = value.get("environment")
    if not isinstance(environment, dict):
        raise MigrationContractError("invalid environment descriptor")
    _exact_keys(environment, required={"required", "optional"})
    environment_keys: set[str] = set()
    for field in ("required", "optional"):
        keys = _string_list(
            environment.get(field),
            maximum_items=500,
            allow_empty_items=False,
        )
        for key in keys:
            if not _ENVIRONMENT_KEY_RE.fullmatch(key) or key in environment_keys:
                raise MigrationContractError("invalid environment key")
            environment_keys.add(key)

    verification = value.get("verification")
    if not isinstance(verification, dict):
        raise MigrationContractError("invalid verification")
    _exact_keys(verification, required={"status", "checks"})
    verification_status = verification.get("status")
    checks = verification.get("checks")
    if (
        verification_status not in {"passed", "failed", "degraded"}
        or not isinstance(checks, list)
        or len(checks) > 1_000
    ):
        raise MigrationContractError("invalid verification")
    failed_checks = 0
    for check in checks:
        if not isinstance(check, dict):
            raise MigrationContractError("invalid verification check")
        _exact_keys(
            check,
            required={"name", "status"},
            optional={"detail"},
        )
        _text(check.get("name"), allow_empty=False, maximum=512)
        if check.get("status") not in {"passed", "failed"}:
            raise MigrationContractError("invalid verification check")
        if check.get("status") == "failed":
            failed_checks += 1
        if "detail" in check:
            _text(check["detail"], maximum=_MAX_TEXT_LENGTH)
    if (
        verification_status == "passed"
        and failed_checks
        or verification_status == "failed"
        and failed_checks == 0
    ):
        raise MigrationContractError("verification status is inconsistent")

    _string_list(
        value.get("warnings"),
        maximum_items=1_000,
        allow_empty_items=False,
    )

    report = value.get("report")
    if not isinstance(report, dict):
        raise MigrationContractError("invalid report descriptor")
    _exact_keys(report, required={"path"})
    report_path = _relative_path(report.get("path"))
    if report_path.casefold() not in file_paths:
        raise MigrationContractError("migration report is not in delivery files")

    artifact = value.get("artifact")
    if not isinstance(artifact, dict):
        raise MigrationContractError("invalid artifact descriptor")
    _exact_keys(artifact, required={"path", "size", "sha256"})
    if artifact.get("path") != "migration-result.zip":
        raise MigrationContractError("invalid artifact path")
    _bounded_integer(artifact.get("size"), maximum=_MAX_ARTIFACT_BYTES)
    _sha256(artifact.get("sha256"))
    _timestamp_text(value.get("created_at"))
    return {str(key): item for key, item in value.items()}


__all__ = [
    "MigrationContractError",
    "validate_analysis_result",
    "validate_detection_report",
    "validate_analysis_status",
    "validate_confirmation",
    "validate_delivery_result",
    "validate_delivery_report",
    "validate_delivery_status",
    "validate_migration_driver",
    "validate_migration_request",
    "validate_process_exit",
    "validate_source_status",
    "validate_stopped_status",
]
