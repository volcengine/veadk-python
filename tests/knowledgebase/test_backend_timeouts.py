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

"""Regression tests: knowledgebase backends must bound their outbound calls.

Search, control-plane, and the pre-signed TOS upload all carry the same shared
`DEFAULT_HTTP_TIMEOUT`. There is no separate, longer allowance for bulk
transfers: one socket-level default covers every call, on the reasoning that a
gap anywhere near a minute means the peer is unhealthy whatever the payload is.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from veadk.utils.http_defaults import DEFAULT_HTTP_TIMEOUT


def _response(payload: dict | None = None, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.raise_for_status.return_value = None
    response.json.return_value = payload if payload is not None else {}
    return response


def test_context_search_search_uses_default_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.knowledgebase.backends import context_search_backend as module

    backend = module.ContextSearchBackend(
        index="123456789",
        volcengine_access_key="ak",
        volcengine_secret_key="sk",
        context_search_engine_endpoint="https://ctxsearch.test/engine",
        context_search_engine_apikey="apikey",
    )

    post = MagicMock(
        return_value=_response({"documents": [{"content": {"sys.content": "doc"}}]})
    )
    monkeypatch.setattr(module.requests, "post", post)

    assert backend.search("hello", top_k=3) == ["doc"]
    assert post.call_count == 1
    assert post.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT


def test_context_search_upload_file_uses_default_http_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from veadk.knowledgebase.backends import context_search_backend as module

    backend = module.ContextSearchBackend(
        index="123456789",
        volcengine_access_key="ak",
        volcengine_secret_key="sk",
    )

    upload = tmp_path / "doc.txt"
    upload.write_text("payload", encoding="utf-8")

    put = MagicMock(return_value=_response())
    monkeypatch.setattr(module.requests, "put", put)

    backend._upload_file(
        file_path=str(upload),
        upload_url="https://tos.test/signed",
        headers={"Content-Type": "text/plain"},
    )

    assert put.call_count == 1
    assert put.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT


def test_vikingdb_do_request_uses_default_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.knowledgebase.backends import vikingdb_knowledge_backend as module

    # `model_post_init` probes the remote collection; skip it so the backend can
    # be built offline.
    monkeypatch.setattr(
        module.VikingDBKnowledgeBackend,
        "model_post_init",
        lambda self, __context: None,
    )

    backend = module.VikingDBKnowledgeBackend(
        index="vikingkl_timeout",
        volcengine_access_key="ak",
        volcengine_secret_key="sk",
        region="cn-beijing",
        base_url="https://api-knowledgebase.mlp.cn-beijing.volces.com",
        host="api-knowledgebase.mlp.cn-beijing.volces.com",
    )

    request: Any = MagicMock(return_value=_response({"data": {}}))
    monkeypatch.setattr(module.requests, "request", request)

    backend._do_request(body={"collection_name": "vikingkl_timeout"}, path="/api/info")

    assert request.call_count == 1
    assert request.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT
