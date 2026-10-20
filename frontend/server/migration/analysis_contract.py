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

"""The contract Codex speaks when it delivers a project analysis.

Two boundaries live behind this module on purpose, and they are deliberately
different:

* Codex hands Studio a *judgement*.  A probabilistic model drifts in shape, so
  acceptance here is liberal: optional fields take defaults, unknown fields are
  ignored, scalar types are coerced, and anything that cannot be anchored (an
  evidence item without a file path) is dropped with a note instead of failing the
  turn.  A model that cannot write the shape must lose quality, never lose a result.
* Studio then assembles the state file itself and validates it against the strict
  on-disk contract, so persistence stays exact while the model never has to be.

Nothing here asks the model for protocol bookkeeping (``schema_version``, ``attempt``,
``input_sha256``); Studio owns those.  The one thing acceptance insists on is that the
destructive ``unsupported`` verdict cites files the model-free detection actually saw,
because a verdict the user can neither act on nor retry must not be reachable by
accident.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from .contracts import (
    MigrationContractError,
    validate_analysis_result,
)
from .models import (
    MIGRATION_FRAMEWORKS,
    STRUCTURED_MIGRATION_FRAMEWORKS,
    is_valid_structured_entry,
)

RECOMMENDATION_KIND = "recommendation"
NEEDS_INPUT_KIND = "needs_input"
UNSUPPORTED_KIND = "unsupported"
ANALYSIS_KINDS = (RECOMMENDATION_KIND, NEEDS_INPUT_KIND, UNSUPPORTED_KIND)

KIND_BY_STATUS = {
    "recommendation_ready": "recommendation",
    "needs_input": "needs_input",
    "unsupported": "unsupported",
}
STATUS_BY_KIND = {
    RECOMMENDATION_KIND: "recommendation_ready",
    NEEDS_INPUT_KIND: "needs_input",
    UNSUPPORTED_KIND: "unsupported",
}

# The verdict the user cannot act on and cannot retry is the one that must clear a
# deterministic bar: it has to cite files that were really in the archive.
_MINIMUM_UNSUPPORTED_EVIDENCE = 2
_MINIMUM_UNSUPPORTED_SUMMARY = 20
_MINIMUM_EVIDENCE_REASON = 4

_MAX_SUMMARY = 20_000
_MAX_TEXT = 4_000

_SCHEMA_VERSION = 1
# A string evidence item is only read as a citation when it starts with something
# that looks like a project path: guessing a path out of free text would invent
# evidence, so text that does not qualify is dropped and reported instead.
_CITATION = re.compile(
    r"^(?P<path>[^\s:：]+)"
    r"(?::(?P<line>\d{1,7}))?"
    r"(?:[\s:：]+(?P<reason>.*\S))?$",
    re.DOTALL,
)


class AnalysisIssue(NamedTuple):
    """One reason acceptance refused a submission, stated where it can be fixed."""

    path: str
    expected: str
    actual: str


class AnalysisAcceptanceError(ValueError):
    """The submission cannot be accepted as written; the model should fix it."""

    def __init__(self, issues: tuple[AnalysisIssue, ...]) -> None:
        self.issues = issues
        super().__init__(
            "; ".join(f"{issue.path}:{issue.expected}" for issue in issues)
        )


class AnalysisAssemblyError(RuntimeError):
    """Studio assembled a document that violates its own contract (a Studio bug)."""


def analysis_tool_schema(kind: str) -> dict[str, object]:
    """The JSON Schema documented to Codex for one terminal analysis tool."""
    _require_kind(kind)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": _required_fields(kind),
        "properties": _payload_properties(kind),
    }


def analysis_document_schema() -> dict[str, object]:
    """The single-document contract used by the scripted ``codex exec`` fallback."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "summary"],
        "properties": {
            "status": {"enum": list(STATUS_BY_KIND.values())},
            "summary": _summary_schema(),
            "frameworks": _frameworks_schema(),
            "recommended": _recommended_schema(),
            "entries": _entries_schema(),
            "boundary": _boundary_schema(),
            "assumptions": _string_list_schema(),
            "questions": _questions_schema(),
            "evidence": _evidence_schema(),
            "warnings": _string_list_schema(),
        },
        "allOf": [
            {
                "if": {
                    "properties": {"status": {"const": "needs_input"}},
                    "required": ["status"],
                },
                "then": {"required": ["questions"]},
            },
            {
                "if": {
                    "properties": {"status": {"const": "unsupported"}},
                    "required": ["status"],
                },
                "then": {"required": ["evidence"]},
            },
        ],
    }


def is_model_document(value: object) -> bool:
    """Whether a decoded object is a judgement Codex produced, not a state file."""
    return (
        isinstance(value, dict)
        and value.get("status") in KIND_BY_STATUS
        and isinstance(value.get("summary"), str)
        and bool(value["summary"].strip())
    )


def build_analysis_result(
    kind: str,
    payload: dict[str, object],
    *,
    attempt: int,
    input_sha256: str,
    detection: dict[str, object] | None = None,
) -> tuple[dict[str, object], list[str]]:
    """Accept one submission and assemble the on-disk analysis document.

    Returns the validated document plus the notes describing everything that was
    dropped or defaulted, so a degraded submission stays visible in diagnostics.
    """
    _require_kind(kind)
    notes: list[str] = []
    if not isinstance(payload, dict):
        raise AnalysisAcceptanceError(
            (AnalysisIssue("payload", "一个 JSON 对象", _type_name(payload)),)
        )
    _note_unknown_fields(payload, kind, notes)
    summary = _summary(payload, notes)
    if kind == RECOMMENDATION_KIND:
        body = _recommendation_body(payload, detection, notes)
    elif kind == NEEDS_INPUT_KIND:
        body = _needs_input_body(payload, detection, notes)
    else:
        body = _unsupported_body(payload, summary, detection, notes)
    document: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": STATUS_BY_KIND[kind],
        "attempt": attempt,
        "input_sha256": input_sha256,
        "summary": summary,
        **body,
    }
    try:
        return validate_analysis_result(document), notes
    except MigrationContractError as error:  # Studio's own output, so a Studio bug
        raise AnalysisAssemblyError(str(error)) from error


def acceptance_feedback(kind: str, error: AnalysisAcceptanceError) -> str:
    """Render refusal reasons as a short instruction the model can act on."""
    lines = [
        f"{issue.path} 需要 {issue.expected}，收到 {issue.actual}。"
        for issue in error.issues
    ]
    tool = {
        RECOMMENDATION_KIND: "reportRecommendation",
        NEEDS_INPUT_KIND: "reportNeedsInput",
        UNSUPPORTED_KIND: "reportUnsupported",
    }[kind]
    return (
        "这次提交没有被接受：\n"
        + "\n".join(f"- {line}" for line in lines)
        + f"\n修正后重新调用 {tool}；不要为此重做已经完成的分析。"
    )


# --------------------------------------------------------------------------- payloads


def _recommendation_body(
    payload: dict[str, object],
    detection: dict[str, object] | None,
    notes: list[str],
) -> dict[str, object]:
    frameworks = _frameworks(payload.get("frameworks"), detection, notes)
    recommended = _recommended(payload.get("recommended"), frameworks, notes)
    entries = _entries(payload.get("entries"), notes)
    if recommended["framework"] in STRUCTURED_MIGRATION_FRAMEWORKS:
        if not any(
            candidate["framework"] == recommended["framework"]
            and candidate["value"] == recommended["entry"]
            for candidate in entries
        ):
            if recommended["entry"] is not None and not any(
                candidate["framework"] == recommended["framework"]
                for candidate in entries
            ):
                notes.append("推荐入口没有对应的入口候选，已改为 null")
                recommended = {**recommended, "entry": None}
    else:
        recommended = {**recommended, "entry": None}
    return {
        "frameworks": frameworks,
        "recommended": recommended,
        "entries": entries,
        "boundary": _boundary(payload.get("boundary"), notes),
        "assumptions": _text_list(payload.get("assumptions"), "assumptions", notes),
        "questions": [],
        "warnings": _text_list(payload.get("warnings"), "warnings", notes),
    }


def _needs_input_body(
    payload: dict[str, object],
    detection: dict[str, object] | None,
    notes: list[str],
) -> dict[str, object]:
    questions = _questions(payload.get("questions"), notes)
    if not questions:
        raise AnalysisAcceptanceError(
            (
                AnalysisIssue(
                    "questions",
                    "至少一个需要用户回答的问题（每项含 prompt）",
                    "空",
                ),
            )
        )
    # A needs_input document still carries the best recommendation so far: the
    # confirmation page and the state-file contract both expect one, and the user may
    # end up confirming it after answering.
    frameworks = _frameworks(payload.get("frameworks"), detection, notes)
    recommended = _recommended(payload.get("recommended"), frameworks, notes)
    return {
        "frameworks": frameworks,
        "recommended": recommended,
        "entries": [],
        "boundary": _boundary(payload.get("boundary"), notes),
        "assumptions": _text_list(payload.get("assumptions"), "assumptions", notes),
        "questions": questions,
        "warnings": _text_list(payload.get("warnings"), "warnings", notes),
    }


def _unsupported_body(
    payload: dict[str, object],
    summary: str,
    detection: dict[str, object] | None,
    notes: list[str],
) -> dict[str, object]:
    evidence = _evidence(payload.get("evidence"), notes)
    issues: list[AnalysisIssue] = []
    if len(evidence) < _MINIMUM_UNSUPPORTED_EVIDENCE:
        issues.append(
            AnalysisIssue(
                "evidence",
                f"至少 {_MINIMUM_UNSUPPORTED_EVIDENCE} 条指向项目文件的证据"
                "（每项含 path、line、reason）",
                f"{len(evidence)} 条可用",
            )
        )
    if len(summary.strip()) < _MINIMUM_UNSUPPORTED_SUMMARY:
        issues.append(
            AnalysisIssue(
                "summary",
                f"面向用户的说明，至少 {_MINIMUM_UNSUPPORTED_SUMMARY} 个字，"
                "依次写清发现了什么、为什么不能迁移、建议用户怎么做",
                f"{len(summary.strip())} 个字",
            )
        )
    issues.extend(_unknown_evidence_paths(evidence, detection))
    if issues:
        raise AnalysisAcceptanceError(tuple(issues))
    # The user never sees the raw tool arguments, so the evidence that justifies the
    # verdict is folded into warnings, which the analysis page renders verbatim.
    warnings = _text_list(payload.get("warnings"), "warnings", notes)
    warnings.extend(
        f"证据：{item['path']}:{item['line']} — {item['reason']}" for item in evidence
    )
    return {
        "frameworks": [],
        "recommended": None,
        "entries": [],
        "boundary": {"include": [], "exclude": []},
        "assumptions": [],
        "questions": [],
        "warnings": warnings,
    }


def _unknown_evidence_paths(
    evidence: list[dict[str, object]],
    detection: dict[str, object] | None,
) -> list[AnalysisIssue]:
    """Reject a verdict that cites files the archive never contained."""
    inventory = _inventory(detection)
    if not inventory:
        # Detection could not run: an unknown inventory must not block a verdict.
        return []
    known = {name.casefold() for name in inventory}
    unknown = [
        str(item["path"])
        for item in evidence
        if not _in_inventory(str(item["path"]), known)
    ]
    if not unknown:
        return []
    return [
        AnalysisIssue(
            "evidence.path",
            "确实存在于项目中的文件（可用文件：" + "、".join(inventory[:20]) + "）",
            "、".join(unknown),
        )
    ]


def _in_inventory(path: str, known: set[str]) -> bool:
    folded = path.casefold().lstrip("./")
    if folded in known:
        return True
    return any(name.endswith("/" + folded) for name in known)


# --------------------------------------------------------------------------- pieces


def _note_unknown_fields(
    payload: dict[str, object],
    kind: str,
    notes: list[str],
) -> None:
    """Record fields the model sent that this kind does not take.

    Echoed bookkeeping (``schema_version``, ``attempt``, ``input_sha256``) lands here,
    which keeps a prompt drift visible without costing the analysis anything.
    """
    allowed = set(_payload_properties(kind)) | {"status"}
    extra = sorted(str(key) for key in payload if key not in allowed)
    if extra:
        notes.append("已忽略模型输出了本工具不接收的字段：" + "、".join(extra))


def _summary(payload: dict[str, object], notes: list[str]) -> str:
    value = payload.get("summary")
    if not isinstance(value, str) or not value.strip():
        raise AnalysisAcceptanceError(
            (
                AnalysisIssue(
                    "summary",
                    "非空字符串，用简体中文概括本次分析结论",
                    _type_name(value),
                ),
            )
        )
    text = value.strip()
    if len(text) > _MAX_SUMMARY:
        notes.append(f"summary 超长，已截断到 {_MAX_SUMMARY} 字符")
        text = text[:_MAX_SUMMARY]
    return text


def _frameworks(
    value: object,
    detection: dict[str, object] | None,
    notes: list[str],
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    # Verified candidates come first: they are the ones later stages may act on.
    for item in _detection_candidates(detection):
        if item["id"] not in seen:
            seen.add(str(item["id"]))
            candidates.append(item)
    for raw in _as_list(value, "frameworks", notes):
        if not isinstance(raw, dict):
            notes.append("已忽略一个不是对象的框架候选")
            continue
        framework = str(raw.get("id") or "").strip()
        if framework not in MIGRATION_FRAMEWORKS:
            notes.append(f"已忽略未知框架候选 {framework or '(空)'}")
            continue
        if framework in seen:
            continue
        seen.add(framework)
        confidence = raw.get("confidence")
        if confidence not in {"high", "medium", "low"}:
            notes.append(f"框架候选 {framework} 的置信度无效，已按 low 处理")
            confidence = "low"
        candidates.append(
            {
                "id": framework,
                "confidence": confidence,
                "evidence": _evidence(raw.get("evidence"), notes),
            }
        )
    if not candidates:
        notes.append("没有任何框架候选，已按 Any 处理")
        candidates.append({"id": "any", "confidence": "low", "evidence": []})
    return candidates


def _recommended(
    value: object,
    frameworks: list[dict[str, object]],
    notes: list[str],
) -> dict[str, object]:
    fallback = str(frameworks[0]["id"])
    raw = value if isinstance(value, dict) else {}
    framework = str(raw.get("framework") or "").strip()
    if framework not in MIGRATION_FRAMEWORKS:
        if framework:
            notes.append(f"推荐的迁移方式 {framework} 无效，已按 {fallback} 处理")
        else:
            notes.append(f"没有给出推荐的迁移方式，已按 {fallback} 处理")
        framework = fallback
    if not any(str(item["id"]) == framework for item in frameworks):
        # The confirmation page only offers the candidates, so the recommendation
        # has to be selectable.
        frameworks.append({"id": framework, "confidence": "low", "evidence": []})
    entry = raw.get("entry")
    if framework in STRUCTURED_MIGRATION_FRAMEWORKS:
        valid = isinstance(entry, str) and is_valid_structured_entry(entry)
        if entry is not None and not valid:
            notes.append(f"入口 {entry!r} 不是合法的结构化入口，已改为 null")
        entry = entry if valid else None
    else:
        if entry is not None:
            notes.append("Dify/Any 的入口必须为 null，已忽略给出的入口")
        entry = None
    reason = raw.get("reason")
    if not isinstance(reason, str):
        reason = ""
    return {
        "framework": framework,
        "entry": entry,
        "reason": reason.strip()[:_MAX_TEXT],
    }


def _entries(value: object, notes: list[str]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for raw in _as_list(value, "entries", notes):
        if not isinstance(raw, dict):
            notes.append("已忽略一个不是对象的入口候选")
            continue
        framework = str(raw.get("framework") or "").strip()
        entry = raw.get("value")
        if framework not in STRUCTURED_MIGRATION_FRAMEWORKS:
            notes.append(
                f"已忽略入口候选 {entry!r}：框架 {framework or '(空)'} 不需要入口"
            )
            continue
        if not isinstance(entry, str) or not is_valid_structured_entry(entry):
            notes.append(f"已忽略入口候选 {entry!r}：不是合法的结构化入口")
            continue
        if (framework, entry) in seen:
            continue
        evidence = raw.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            notes.append(f"已忽略入口候选 {entry}：缺少说明")
            continue
        seen.add((framework, entry))
        entries.append(
            {
                "value": entry,
                "framework": framework,
                "evidence": evidence.strip()[:_MAX_TEXT],
            }
        )
    return entries


def _boundary(value: object, notes: list[str]) -> dict[str, object]:
    raw = value if isinstance(value, dict) else {}
    include = _text_list(raw.get("include"), "boundary.include", notes)
    exclude = _text_list(raw.get("exclude"), "boundary.exclude", notes)
    if not include:
        notes.append("没有给出迁移范围，已按项目内全部文件处理")
        include = ["项目内全部文件"]
    return {"include": include, "exclude": exclude}


def _evidence(value: object, notes: list[str]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if not isinstance(value, list):
        if value is not None:
            notes.append("evidence 不是数组，已忽略")
        return items
    dropped = 0
    for raw in value:
        item = _evidence_item(raw, notes)
        if item is None:
            dropped += 1
            continue
        items.append(item)
    if dropped:
        notes.append(f"已丢弃 {dropped} 条无法定位到文件的证据")
    return items


def _evidence_item(
    raw: object,
    notes: list[str] | None = None,
) -> dict[str, object] | None:
    if isinstance(raw, str):
        text = raw.strip()
        match = _CITATION.match(text)
        if match is None or not _looks_like_path(match.group("path")):
            return None
        raw = {
            "path": match.group("path"),
            "line": match.group("line"),
            "reason": match.group("reason") or text,
        }
    if not isinstance(raw, dict):
        return None
    path = _relative_path(raw.get("path"))
    reason = raw.get("reason")
    if path is None or not isinstance(reason, str) or not reason.strip():
        return None
    line = _positive_int(raw.get("line"))
    if line is None:
        if notes is not None and raw.get("line") is not None:
            notes.append("evidence.line 不是正整数，已按 1 处理")
        line = 1
    return {
        "path": path,
        "line": line,
        "reason": reason.strip()[:_MAX_TEXT],
    }


def _questions(value: object, notes: list[str]) -> list[dict[str, object]]:
    questions: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_as_list(value, "questions", notes), start=1):
        if not isinstance(raw, dict):
            notes.append("已忽略一个不是对象的问题")
            continue
        prompt = raw.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            prompt = raw.get("question")
        if not isinstance(prompt, str) or not prompt.strip():
            notes.append(f"已忽略第 {index} 个没有内容的问题")
            continue
        question_id = str(raw.get("id") or f"q{index}").strip() or f"q{index}"
        if question_id in seen:
            question_id = f"{question_id}-{index}"
        seen.add(question_id)
        required = raw.get("required")
        if not isinstance(required, bool):
            required = index == 1
        questions.append(
            {
                "id": question_id[:128],
                "prompt": prompt.strip()[:_MAX_TEXT],
                "required": required,
            }
        )
        if len(questions) >= 50:
            notes.append("问题过多，已截断到 50 个")
            break
    if questions and not any(question["required"] for question in questions):
        questions[0]["required"] = True
    return questions


def _as_list(value: object, field: str, notes: list[str]) -> list[object]:
    """A field that should be a list, reported instead of silently ignored."""
    if value is None:
        return []
    if not isinstance(value, list):
        notes.append(f"{field} 不是数组，已忽略")
        return []
    return list(value)


def _text_list(value: object, field: str, notes: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        notes.append(f"{field} 不是数组，已忽略")
        return []
    items: list[str] = []
    for raw in value:
        if isinstance(raw, str) and raw.strip():
            items.append(raw.strip()[:_MAX_TEXT])
        elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
            items.append(str(raw))
        else:
            notes.append(f"{field} 中有一项不是文字，已忽略")
    return items


def detection_candidates(
    detection: dict[str, object] | None,
) -> list[dict[str, object]]:
    """The framework candidates Studio verified without a model."""
    return _detection_candidates(detection)


def _detection_candidates(
    detection: dict[str, object] | None,
) -> list[dict[str, object]]:
    if not isinstance(detection, dict):
        return []
    candidates: list[dict[str, object]] = []
    for raw in detection.get("candidates", []):
        if not isinstance(raw, dict):
            continue
        framework = raw.get("id")
        if framework not in MIGRATION_FRAMEWORKS:
            continue
        candidates.append(
            {
                "id": framework,
                "confidence": (
                    raw.get("confidence")
                    if raw.get("confidence") in {"high", "medium", "low"}
                    else "low"
                ),
                "evidence": [
                    item
                    for item in (
                        _evidence_item(entry) for entry in raw.get("evidence", [])
                    )
                    if item is not None
                ],
            }
        )
    return candidates


def _inventory(detection: dict[str, object] | None) -> list[str]:
    if not isinstance(detection, dict) or detection.get("degraded"):
        return []
    files = detection.get("files")
    if not isinstance(files, dict):
        return []
    listed = files.get("listed")
    if not isinstance(listed, list):
        return []
    return [str(item) for item in listed if isinstance(item, str)]


def _looks_like_path(value: str) -> bool:
    return len(value) <= 512 and ("/" in value or "." in value)


def _relative_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().replace("\\", "/").lstrip("/")
    while text.startswith("./"):
        text = text[2:]
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)[:4_096]


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 1 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed >= 1 else None
    return None


def _type_name(value: object) -> str:
    return {
        str: "字符串",
        dict: "对象",
        list: "数组",
        int: "整数",
        float: "小数",
        bool: "布尔值",
        type(None): "null",
    }.get(type(value), type(value).__name__)


def _require_kind(kind: str) -> None:
    if kind not in ANALYSIS_KINDS:
        raise ValueError(f"unknown analysis kind: {kind}")


# --------------------------------------------------------------------------- schemas


def _required_fields(kind: str) -> list[str]:
    if kind == RECOMMENDATION_KIND:
        return ["summary"]
    if kind == NEEDS_INPUT_KIND:
        return ["summary", "questions"]
    return ["summary", "evidence"]


def _payload_properties(kind: str) -> dict[str, object]:
    if kind == RECOMMENDATION_KIND:
        return {
            "summary": _summary_schema(),
            "frameworks": _frameworks_schema(),
            "recommended": _recommended_schema(),
            "entries": _entries_schema(),
            "boundary": _boundary_schema(),
            "assumptions": _string_list_schema(),
            "warnings": _string_list_schema(),
        }
    if kind == NEEDS_INPUT_KIND:
        return {
            "summary": _summary_schema(),
            "questions": _questions_schema(),
            "frameworks": _frameworks_schema(),
            "recommended": _recommended_schema(),
            "boundary": _boundary_schema(),
            "assumptions": _string_list_schema(),
            "warnings": _string_list_schema(),
        }
    return {
        "summary": _summary_schema(),
        "evidence": _evidence_schema(),
        "warnings": _string_list_schema(),
    }


def _summary_schema() -> dict[str, object]:
    return {"type": "string", "minLength": 1, "maxLength": _MAX_SUMMARY}


def _evidence_schema() -> dict[str, object]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["path", "reason"],
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "line": {"type": "integer", "minimum": 1},
                "reason": {"type": "string", "minLength": 1},
            },
        },
    }


def _frameworks_schema() -> dict[str, object]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id"],
            "properties": {
                "id": {"enum": list(MIGRATION_FRAMEWORKS)},
                "confidence": {"enum": ["high", "medium", "low"]},
                "evidence": _evidence_schema(),
            },
        },
    }


def _recommended_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["framework"],
        "properties": {
            "framework": {"enum": list(MIGRATION_FRAMEWORKS)},
            "entry": {"type": ["string", "null"]},
            "reason": {"type": "string"},
        },
    }


def _entries_schema() -> dict[str, object]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["value", "framework", "evidence"],
            "properties": {
                "value": {"type": "string", "minLength": 1},
                "framework": {"enum": list(STRUCTURED_MIGRATION_FRAMEWORKS)},
                "evidence": {"type": "string", "minLength": 1},
            },
        },
    }


def _boundary_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "include": _string_list_schema(),
            "exclude": _string_list_schema(),
        },
    }


def _questions_schema() -> dict[str, object]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["prompt"],
            "properties": {
                "id": {"type": "string"},
                "prompt": {"type": "string", "minLength": 1},
                "required": {"type": "boolean"},
            },
        },
    }


def _string_list_schema() -> dict[str, object]:
    return {"type": "array", "items": {"type": "string", "maxLength": _MAX_TEXT}}


__all__ = [
    "ANALYSIS_KINDS",
    "KIND_BY_STATUS",
    "NEEDS_INPUT_KIND",
    "RECOMMENDATION_KIND",
    "STATUS_BY_KIND",
    "UNSUPPORTED_KIND",
    "AnalysisAcceptanceError",
    "AnalysisAssemblyError",
    "AnalysisIssue",
    "acceptance_feedback",
    "analysis_document_schema",
    "analysis_tool_schema",
    "build_analysis_result",
    "detection_candidates",
    "is_model_document",
]
