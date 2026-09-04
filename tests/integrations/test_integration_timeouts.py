# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Regression tests: Volcengine integration helpers must be bounded.

These are the signed control-plane calls (APIG, FaaS, CozeLoop) plus the GitHub
webhook registration. All of them are made synchronously from deployment paths,
so an unbounded `requests` call hangs the caller indefinitely.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from veadk.utils.http_defaults import DEFAULT_HTTP_TIMEOUT


def _response(payload: dict | None = None, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = ""
    response.json.return_value = payload if payload is not None else {}
    return response


def test_ve_apig_request_passes_default_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.integrations.ve_apig import ve_apig_utils as module

    request = MagicMock(return_value=_response({"Result": {}}))
    monkeypatch.setattr(module.requests, "request", request)

    module.request(
        method="GET",
        date=datetime.datetime(2025, 1, 1, 0, 0, 0),
        query={},
        header={},
        region="cn-beijing",
        ak="ak",
        sk="sk",
        token="token",
        action="ListRoutes",
        body="",
    )

    assert request.call_count == 1
    assert request.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT


def test_ve_faas_request_passes_default_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.integrations.ve_faas import ve_faas_utils as module

    request = MagicMock(return_value=_response({"Result": {}}))
    monkeypatch.setattr(module.requests, "request", request)

    module.request(
        method="GET",
        date=datetime.datetime(2025, 1, 1, 0, 0, 0),
        query={},
        header={},
        ak="ak",
        sk="sk",
        token="token",
        action="ListGateways",
        body="",
    )

    assert request.call_count == 1
    assert request.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT


def test_cozeloop_search_workspace_id_passes_default_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.integrations.ve_cozeloop import ve_cozeloop as module

    get = MagicMock(
        return_value=_response(
            {"code": 0, "data": {"workspaces": [{"name": "veadk", "id": "ws-1"}]}}
        )
    )
    monkeypatch.setattr(module.requests, "get", get)

    workspace_id = module.VeCozeloop(api_key="key").search_workspace_id(
        workspace_name="veadk"
    )

    assert workspace_id == "ws-1"
    assert get.call_count == 1
    assert get.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT


def test_cozeloop_create_workspace_passes_default_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.integrations.ve_cozeloop import ve_cozeloop as module

    # A failing lookup is what pushes `create_workspace` past its early return
    # and onto the POST we care about.
    monkeypatch.setattr(
        module.requests,
        "get",
        MagicMock(return_value=_response({"code": 1})),
    )
    post = MagicMock(return_value=_response({"code": 0, "data": {"id": "ws-2"}}))
    monkeypatch.setattr(module.requests, "post", post)

    workspace_id = module.VeCozeloop(api_key="key").create_workspace(
        workspace_name="veadk"
    )

    assert workspace_id == "ws-2"
    assert post.call_count == 1
    assert post.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT


def test_code_pipeline_github_webhook_passes_default_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.integrations.ve_code_pipeline import ve_code_pipeline as module

    post = MagicMock(
        return_value=_response(
            {"id": 1, "url": "https://api.github.com/hooks/1", "events": ["push"]},
            status_code=201,
        )
    )
    monkeypatch.setattr(module.requests, "post", post)

    pipeline = module.VeCodePipeline(
        volcengine_access_key="ak",
        volcengine_secret_key="sk",
        region="cn-beijing",
    )
    result = pipeline._set_github_webhook(
        webhook_url="https://cp.test/webhook",
        github_url="https://github.com/owner/repo",
        github_token="gh-token",
    )

    assert result is not None
    assert post.call_count == 1
    assert post.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT
    assert (
        post.call_args.kwargs["url"] == "https://api.github.com/repos/owner/repo/hooks"
    )
