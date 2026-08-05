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

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Self
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from veadk.cli.frontend_issue_feedback import (
    _TRACE_FIELD_MAX_CHARS,
    IssueFeedbackRequest,
    _build_form_fields,
    _trace_json_text,
    mount_issue_feedback_route,
)


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = {"code": 0} if payload is None else payload

    def json(self) -> dict[str, Any]:
        return self._payload


def _request_body() -> dict[str, Any]:
    return {
        "source": "agent_exec",
        "module": "conversation",
        "issues": ["slow", "tool_error"],
        "problem": "工具响应缓慢",
        "description": "检索完成后长时间没有返回。",
        "page": "conversation",
        "appName": "support-agent",
        "runtimeId": "runtime-1",
        "sessionId": "session-1",
        "eventId": "event-1",
        "invocationId": "invocation-1",
        "input": "查询今天的工单",
        "output": "共找到 3 条工单。",
        "toolCalls": [
            {
                "name": "search_tickets",
                "args": {"query": "今天", "apiKey": "secret-value"},
                "response": {"count": 3, "items": ["A", "B", "C"]},
            }
        ],
        "trace": [
            {
                "name": "call_llm",
                "trace_id": 22,
                "span_id": 11,
                "attributes": {
                    "invocation.id": "invocation-1",
                    "authorization": "Bearer private-token",
                },
            }
        ],
    }


def _field_text(fields: dict[str, Any], field_id: str) -> str:
    return fields[field_id]["value"][0]["text"]


def test_trace_json_keeps_complete_spans_from_the_end() -> None:
    trace = [
        {"span_id": "old", "output": "旧" * 40},
        {"span_id": "middle", "output": "中" * 40},
        {"span_id": "latest", "output": "新" * 40},
    ]
    expected = json.dumps(
        trace[1:],
        ensure_ascii=False,
        separators=(",", ":"),
    )

    result = _trace_json_text(trace, max_chars=len(expected))

    assert len(result) <= len(expected)
    assert json.loads(result) == trace[1:]


def test_trace_json_keeps_valid_tail_when_one_span_exceeds_limit() -> None:
    trace = [{"span_id": "large", "output": "前" * 200 + "后" * 200}]

    result = _trace_json_text(trace, max_chars=180)
    parsed = json.loads(result)

    assert len(result) <= 180
    assert parsed[0]["_truncated"] is True
    assert "后" in parsed[0]["content_tail"]
    assert parsed[0]["content_tail"].endswith('"}')


def test_trace_form_field_stays_below_lark_text_limit() -> None:
    report = IssueFeedbackRequest.model_validate(_request_body())
    report.trace = [{"span_id": "large", "output": "结果" * 60_000}]

    fields = _build_form_fields(report, datetime.now(timezone.utc))
    trace_text = _field_text(fields, "fldENXpcnH")

    assert len(trace_text) <= _TRACE_FIELD_MAX_CHARS
    assert json.loads(trace_text)[0]["_truncated"] is True


@pytest.mark.parametrize(
    ("source", "field_id"),
    [("agent_exec", "fld7wNWKv5"), ("platform", "flduL6ptO2")],
)
def test_feedback_time_uses_beijing_time(source: str, field_id: str) -> None:
    report = IssueFeedbackRequest.model_validate({**_request_body(), "source": source})
    created_at = datetime(2026, 8, 5, 11, 37, 53, tzinfo=timezone.utc)

    fields = _build_form_fields(report, created_at)

    expected = created_at.astimezone(ZoneInfo("Asia/Shanghai")).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert _field_text(fields, field_id) == expected


def test_agent_feedback_posts_redacted_data_to_public_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    authorized: list[str] = []
    requests: list[dict[str, Any]] = []

    def _authorize(request: Request) -> None:
        authorized.append(request.url.path)

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["follow_redirects"] is True
            self.cookies = {"_csrf_token": "csrf-test"}

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def get(self, url: str) -> _FakeResponse:
            requests.append({"method": "GET", "url": url})
            return _FakeResponse()

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            requests.append({"method": "POST", "url": url, **kwargs})
            return _FakeResponse()

    monkeypatch.setattr(
        "veadk.cli.frontend_issue_feedback.httpx.AsyncClient",
        _FakeAsyncClient,
    )
    mount_issue_feedback_route(app, authorize=_authorize)

    response = TestClient(app).post("/web/issue-feedback", json=_request_body())

    assert response.status_code == 200
    assert response.json() == {"submitted": True}
    assert authorized == ["/web/issue-feedback"]
    assert requests[0] == {
        "method": "GET",
        "url": (
            "https://bytedance.larkoffice.com/share/base/form/"
            "shrcnrOCNuZL9w8lfotEIMleAyd"
        ),
    }
    submission = requests[1]
    assert submission["method"] == "POST"
    assert submission["url"] == (
        "https://bytedance.larkoffice.com/space/api/bitable/share/content"
    )
    assert submission["headers"]["X-CSRFToken"] == "csrf-test"
    assert submission["json"]["shareToken"] == "shrcnrOCNuZL9w8lfotEIMleAyd"
    assert submission["json"]["preUploadEnable"] is False

    fields = json.loads(submission["json"]["data"])
    assert fields["fldaoAcljY"] == {
        "type": 4,
        "value": ["optjOXnpdK", "optizRXKAz"],
    }
    assert _field_text(fields, "fldpj26Zd0") == "runtime-1"
    assert _field_text(fields, "fldNYQWLoj") == (
        "工具响应缓慢\n检索完成后长时间没有返回。"
    )
    assert _field_text(fields, "fldO54V6ch") == "查询今天的工单"
    assert _field_text(fields, "fld7DNJPlU") == "共找到 3 条工单。"
    assert json.loads(_field_text(fields, "fldbBn9zPh"))[0]["args"] == {
        "query": "今天",
        "apiKey": "***",
    }
    assert (
        json.loads(_field_text(fields, "fldENXpcnH"))[0]["attributes"]["authorization"]
        == "***"
    )


def test_agent_feedback_loads_apmplus_trace_when_request_has_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    submissions: list[dict[str, Any]] = []

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs
            self.cookies = {"_csrf_token": "csrf-test"}

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def get(self, url: str) -> _FakeResponse:
            del url
            return _FakeResponse()

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            submissions.append({"url": url, **kwargs})
            return _FakeResponse()

    async def _load_trace(
        report: IssueFeedbackRequest,
        request: Request,
    ) -> list[dict[str, Any]]:
        assert report.runtime_id == "runtime-1"
        assert request.url.path == "/web/issue-feedback"
        return [{"trace_id": "trace-1", "span_id": "span-1"}]

    monkeypatch.setattr(
        "veadk.cli.frontend_issue_feedback.httpx.AsyncClient",
        _FakeAsyncClient,
    )
    mount_issue_feedback_route(app, trace_loader=_load_trace)
    body = _request_body()
    body["trace"] = []

    response = TestClient(app).post("/web/issue-feedback", json=body)

    assert response.json() == {"submitted": True}
    fields = json.loads(submissions[0]["json"]["data"])
    assert json.loads(_field_text(fields, "fldENXpcnH")) == [
        {"trace_id": "trace-1", "span_id": "span-1"}
    ]


def test_platform_feedback_posts_module_and_issues_to_platform_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    submissions: list[dict[str, Any]] = []

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs
            self.cookies = {"_csrf_token": "csrf-test"}

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def get(self, url: str) -> _FakeResponse:
            del url
            return _FakeResponse()

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            submissions.append({"url": url, **kwargs})
            return _FakeResponse()

    monkeypatch.setattr(
        "veadk.cli.frontend_issue_feedback.httpx.AsyncClient",
        _FakeAsyncClient,
    )
    mount_issue_feedback_route(app)
    body = _request_body()
    body.update(
        {
            "source": "platform",
            "module": "agents",
            "issues": ["page_slow", "display_error"],
            "page": "agents",
        }
    )

    response = TestClient(app).post("/web/issue-feedback", json=body)

    assert response.json() == {"submitted": True}
    assert submissions[0]["json"]["shareToken"] == ("shrcnK0TsxiTEtuW9Z9TjgIIqTg")
    fields = json.loads(submissions[0]["json"]["data"])
    assert fields["fldP53ofOH"] == {"type": 3, "value": "optJZ9Z6aj"}
    assert fields["fldjXM1FiG"] == {
        "type": 4,
        "value": ["optNPa6aST", "opts6HDK4U"],
    }
    assert _field_text(fields, "fldmRW2Tf2") == "runtime-1"


def test_issue_feedback_requires_user_description_or_issue() -> None:
    app = FastAPI()
    mount_issue_feedback_route(app)
    body = _request_body()
    body["issues"] = []
    body["problem"] = ""
    body["description"] = "  "

    response = TestClient(app).post("/web/issue-feedback", json=body)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("status_code", "payload"),
    [(403, {"code": 0}), (200, {"code": 1200, "msg": "invalid"})],
)
def test_issue_feedback_surfaces_public_form_failures(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    payload: dict[str, Any],
) -> None:
    app = FastAPI()

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs
            self.cookies = {"_csrf_token": "csrf-test"}

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def get(self, url: str) -> _FakeResponse:
            del url
            return _FakeResponse()

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            del url, kwargs
            return _FakeResponse(status_code, payload)

    monkeypatch.setattr(
        "veadk.cli.frontend_issue_feedback.httpx.AsyncClient",
        _FakeAsyncClient,
    )
    mount_issue_feedback_route(app)

    response = TestClient(app).post("/web/issue-feedback", json=_request_body())

    assert response.status_code == 502
    assert response.json()["detail"] == "问题反馈上报失败，请稍后重试"


def test_issue_feedback_surfaces_public_form_network_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def get(self, url: str) -> _FakeResponse:
            raise httpx.ConnectError(
                "offline",
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "veadk.cli.frontend_issue_feedback.httpx.AsyncClient",
        _FakeAsyncClient,
    )
    mount_issue_feedback_route(app)

    response = TestClient(app).post("/web/issue-feedback", json=_request_body())

    assert response.status_code == 502
    assert response.json()["detail"] == "问题反馈上报失败，请稍后重试"
