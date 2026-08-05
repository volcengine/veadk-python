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

"""Submit redacted Studio issue feedback to public Lark forms."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

_LARK_ORIGIN = "https://bytedance.larkoffice.com"
_LARK_FORM_SUBMIT_URL = f"{_LARK_ORIGIN}/space/api/bitable/share/content"
_FORM_SHARE_TOKENS = {
    "agent_exec": "shrcnrOCNuZL9w8lfotEIMleAyd",
    "platform": "shrcnK0TsxiTEtuW9Z9TjgIIqTg",
}
_MAX_REPORT_BYTES = 20 * 1024 * 1024
_TRACE_FIELD_MAX_CHARS = 95_000

_AGENT_FIELDS = {
    "runtime_id": "fldpj26Zd0",
    "issues": "fldaoAcljY",
    "description": "fldNYQWLoj",
    "feedback_time": "fld7wNWKv5",
    "trace": "fldENXpcnH",
    "session_id": "fldvJRATq1",
    "page": "fldmJcCrWc",
    "app_name": "fld8KxHFyQ",
    "output": "fld7DNJPlU",
    "tool_calls": "fldbBn9zPh",
    "event_id": "fldOsYCTNX",
    "input": "fldO54V6ch",
    "invocation_id": "fldetNumah",
}
_PLATFORM_FIELDS = {
    "description": "fldqH8W79e",
    "runtime_id": "fldmRW2Tf2",
    "feedback_time": "flduL6ptO2",
    "module": "fldP53ofOH",
    "tool_calls": "fldOQFIs8h",
    "app_name": "fldQ594BYD",
    "session_id": "fldnmzAeCL",
    "issues": "fldjXM1FiG",
    "page": "fldzAlD421",
    "trace": "fldcDRrz18",
    "output": "fld2Ycrld4",
    "input": "flddEJ8odt",
}
_AGENT_ISSUE_OPTIONS = {
    "slow": "optjOXnpdK",
    "crash": "optG5zFscJ",
    "incorrect": "opttHqgmOd",
    "tool_error": "optizRXKAz",
    "other": "optEMk03mM",
}
_PLATFORM_ISSUE_OPTIONS = {
    "page_slow": "optNPa6aST",
    "feature_unavailable": "opt2PLHHxS",
    "display_error": "opts6HDK4U",
    "no_response": "optqI0f63c",
    "other": "optCZqML3G",
}
_PLATFORM_MODULE_OPTIONS = {
    "conversation": "optLUYTCmV",
    "agents": "optJZ9Z6aj",
    "applications": "opt1WCki7j",
    "search": "optRZctXz7",
    "other": "optfHBKjl6",
}
_ISSUE_LABELS = {
    "slow": "执行速度慢",
    "crash": "运行崩溃",
    "incorrect": "结果不正确",
    "tool_error": "工具调用失败",
    "page_slow": "页面加载慢",
    "feature_unavailable": "功能无法使用",
    "display_error": "页面显示异常",
    "no_response": "操作无响应",
    "other": "其他问题",
}

_SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[._-])(?:authorization|api_key|access_key(?:_id)?|secret(?:_key)?|"
    r"auth_token|access_token|session_token|security_token|refresh_token|"
    r"id_token|jwt_token|client_secret|credential|signature|password)"
    r"(?:$|[._-])",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)((?:api[_-]?key|access[_-]?key(?:[_-]?id)?|secret[_-]?key|"
    r"auth[_-]?token|access[_-]?token|session[_-]?token|client[_-]?secret|"
    r"credential|signature|password)\s*[:=]\s*)"
    r"(?:[\"'][^\"']*[\"']|[^\s,;]+)"
)

IssueKind = Literal[
    "slow",
    "crash",
    "incorrect",
    "tool_error",
    "page_slow",
    "feature_unavailable",
    "display_error",
    "no_response",
    "other",
]
IssueSource = Literal["agent_exec", "platform"]
IssueModule = Literal["conversation", "agents", "applications", "search", "other"]


class IssueFeedbackRequest(BaseModel):
    """One user-authored issue report and its associated execution details."""

    model_config = ConfigDict(populate_by_name=True)

    source: IssueSource
    module: IssueModule
    issues: list[IssueKind] = Field(default_factory=list, max_length=5)
    problem: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=4000)
    page: str = Field(default="", max_length=500)
    app_name: str = Field(alias="appName", default="", max_length=500)
    runtime_id: str = Field(alias="runtimeId", default="", max_length=500)
    region: str = Field(default="cn-beijing", max_length=100)
    session_id: str = Field(alias="sessionId", default="", max_length=500)
    event_id: str = Field(alias="eventId", default="", max_length=500)
    invocation_id: str = Field(alias="invocationId", default="", max_length=500)
    input: str = ""
    output: str = ""
    tool_calls: list[dict[str, Any]] = Field(alias="toolCalls", default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_feedback_content(self) -> IssueFeedbackRequest:
        if (
            not self.issues
            and not self.problem.strip()
            and not self.description.strip()
        ):
            raise ValueError("Select an issue or provide a description")
        return self


def _normalized_key(value: object) -> str:
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value))
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", key).lower()


def _redact_text(value: str) -> str:
    redacted = value
    for key, secret in os.environ.items():
        if (
            secret
            and len(secret) >= 8
            and any(
                marker in key.upper()
                for marker in ("KEY", "SECRET", "TOKEN", "PASSWORD")
            )
        ):
            redacted = redacted.replace(secret, "***")
    redacted = re.sub(
        r"(?i)(\bbearer\s+)[a-z0-9._~+/=-]+",
        r"\1***",
        redacted,
    )
    return _SENSITIVE_VALUE_RE.sub(r"\1***", redacted)


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Mapping):
        redacted: dict[str, object] = {}
        for key, item in value.items():
            safe_key = str(key)
            redacted[safe_key] = (
                "***"
                if _SENSITIVE_KEY_RE.search(_normalized_key(safe_key))
                else _redact_value(item)
            )
        return redacted
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_redact_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(str(value))


def _text_field(value: str) -> dict[str, object]:
    return {"type": 1, "value": [{"type": "text", "text": value}]}


def _selection_field(field_type: int, values: list[str]) -> dict[str, object]:
    return {"type": field_type, "value": values}


def _put_text(
    fields: dict[str, dict[str, object]],
    field_id: str,
    value: str,
) -> None:
    if value:
        fields[field_id] = _text_field(value)


def _json_text(value: object) -> str:
    return json.dumps(
        _redact_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _trace_json_text(
    trace: list[dict[str, Any]],
    *,
    max_chars: int = _TRACE_FIELD_MAX_CHARS,
) -> str:
    redacted = _redact_value(trace)
    if not isinstance(redacted, list):
        return "[]"

    full_text = json.dumps(
        redacted,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(full_text) <= max_chars:
        return full_text

    suffix: list[object] = []
    for span in reversed(redacted):
        candidate = [span, *suffix]
        candidate_text = json.dumps(
            candidate,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(candidate_text) > max_chars:
            break
        suffix = candidate

    if suffix:
        return json.dumps(
            suffix,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    last_span_text = json.dumps(
        redacted[-1],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    low = 0
    high = len(last_span_text)
    best = "[]"
    while low <= high:
        tail_length = (low + high) // 2
        marker = [
            {
                "_truncated": True,
                "content_tail": last_span_text[-tail_length:] if tail_length else "",
            }
        ]
        marker_text = json.dumps(
            marker,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(marker_text) <= max_chars:
            best = marker_text
            low = tail_length + 1
        else:
            high = tail_length - 1
    return best


def _feedback_description(report: IssueFeedbackRequest) -> str:
    return "\n".join(
        value
        for value in (
            _redact_text(report.problem).strip(),
            _redact_text(report.description).strip(),
        )
        if value
    )


def _feedback_time(created_at: datetime) -> str:
    return created_at.astimezone(ZoneInfo("Asia/Shanghai")).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _build_form_fields(
    report: IssueFeedbackRequest,
    created_at: datetime,
) -> dict[str, dict[str, object]]:
    fields: dict[str, dict[str, object]] = {}
    description = _feedback_description(report)
    feedback_time = _feedback_time(created_at)

    if report.source == "agent_exec":
        field_ids = _AGENT_FIELDS
        option_ids = [
            _AGENT_ISSUE_OPTIONS[issue]
            for issue in report.issues
            if issue in _AGENT_ISSUE_OPTIONS
        ]
        if option_ids:
            fields[field_ids["issues"]] = _selection_field(4, option_ids)
        _put_text(fields, field_ids["event_id"], _redact_text(report.event_id))
        _put_text(
            fields,
            field_ids["invocation_id"],
            _redact_text(report.invocation_id),
        )
    else:
        field_ids = _PLATFORM_FIELDS
        option_ids = [
            _PLATFORM_ISSUE_OPTIONS[issue]
            for issue in report.issues
            if issue in _PLATFORM_ISSUE_OPTIONS
        ]
        if option_ids:
            fields[field_ids["issues"]] = _selection_field(4, option_ids)
        fields[field_ids["module"]] = {
            "type": 3,
            "value": _PLATFORM_MODULE_OPTIONS[report.module],
        }

    _put_text(fields, field_ids["feedback_time"], feedback_time)
    _put_text(fields, field_ids["description"], description)
    _put_text(fields, field_ids["runtime_id"], _redact_text(report.runtime_id))
    _put_text(fields, field_ids["session_id"], _redact_text(report.session_id))
    _put_text(fields, field_ids["page"], _redact_text(report.page))
    _put_text(fields, field_ids["app_name"], _redact_text(report.app_name))
    _put_text(fields, field_ids["input"], _redact_text(report.input))
    _put_text(fields, field_ids["output"], _redact_text(report.output))
    if report.tool_calls:
        _put_text(fields, field_ids["tool_calls"], _json_text(report.tool_calls))
    if report.trace:
        _put_text(fields, field_ids["trace"], _trace_json_text(report.trace))
    return fields


def mount_issue_feedback_route(
    app: Any,
    *,
    authorize: Callable[[Request], object] | None = None,
    trace_loader: Callable[
        [IssueFeedbackRequest, Request],
        Awaitable[list[dict[str, Any]]],
    ]
    | None = None,
) -> None:
    """Mount the authenticated Studio issue-feedback submission endpoint."""

    @app.post("/web/issue-feedback")
    async def _submit_issue_feedback(
        report: IssueFeedbackRequest,
        request: Request,
    ) -> dict[str, bool]:
        if authorize is not None:
            authorize(request)

        if trace_loader is not None and report.runtime_id and not report.trace:
            try:
                report.trace = await trace_loader(report, request)
            except Exception:  # noqa: BLE001 - trace is optional diagnostic context
                # Trace is diagnostic context, not a prerequisite for accepting
                # the user's report. The Studio callback logs provider details.
                report.trace = []

        created_at = datetime.now(timezone.utc)
        share_token = _FORM_SHARE_TOKENS[report.source]
        share_url = f"{_LARK_ORIGIN}/share/base/form/{share_token}"
        data = json.dumps(
            _build_form_fields(report, created_at),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(data.encode("utf-8")) > _MAX_REPORT_BYTES:
            raise HTTPException(status_code=413, detail="问题反馈内容过大，无法上报")

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
            ) as client:
                page_response = await client.get(share_url)
                if not 200 <= page_response.status_code < 300:
                    raise HTTPException(
                        status_code=502,
                        detail="问题反馈上报失败，请稍后重试",
                    )
                csrf_token = client.cookies.get("_csrf_token")
                if not csrf_token:
                    raise HTTPException(
                        status_code=502,
                        detail="问题反馈上报失败，请稍后重试",
                    )
                response = await client.post(
                    _LARK_FORM_SUBMIT_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Referer": share_url,
                        "X-CSRFToken": csrf_token,
                    },
                    json={
                        "shareToken": share_token,
                        "data": data,
                        "preUploadEnable": False,
                    },
                )
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502,
                detail="问题反馈上报失败，请稍后重试",
            ) from error

        if not 200 <= response.status_code < 300:
            raise HTTPException(
                status_code=502,
                detail="问题反馈上报失败，请稍后重试",
            )
        try:
            result = response.json()
        except ValueError as error:
            raise HTTPException(
                status_code=502,
                detail="问题反馈上报失败，请稍后重试",
            ) from error
        if not isinstance(result, dict) or result.get("code") != 0:
            raise HTTPException(
                status_code=502,
                detail="问题反馈上报失败，请稍后重试",
            )
        return {"submitted": True}
