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

from __future__ import annotations

import pytest

from veadk.tools.builtin_tools.parallel_web_search import parallel_web_search
from veadk.tools.builtin_tools.web_search import web_search


class _FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {
            "Result": {
                "WebResults": [
                    {
                        "Title": "Result",
                        "Url": "https://example.com",
                        "Summary": "BytePlus result summary.",
                    }
                ]
            }
        }


def test_web_search_uses_byteplus_api_key_without_volcengine_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("BYTEPLUS_WEB_SEARCH_API_KEY", "bp-search-key")
    monkeypatch.delenv("VOLCENGINE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_SECRET_KEY", raising=False)
    monkeypatch.setattr(
        "veadk.tools.builtin_tools.web_search.get_credential_from_vefaas_iam",
        lambda: (_ for _ in ()).throw(AssertionError("should not need IAM creds")),
    )

    def _post(**kwargs):
        calls.append(kwargs)
        return _FakeResponse()

    monkeypatch.setattr("veadk.tools.builtin_tools.web_search.requests.post", _post)

    assert web_search("hello") == ["BytePlus result summary."]
    assert calls[0]["headers"]["Authorization"] == "Bearer bp-search-key"


@pytest.mark.asyncio
async def test_parallel_web_search_uses_byteplus_searchinfinity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("BYTEPLUS_WEB_SEARCH_API_KEY", "bp-search-key")
    monkeypatch.setattr(
        "veadk.tools.builtin_tools.web_search.requests.post",
        lambda **_: _FakeResponse(),
    )

    assert await parallel_web_search(["hello", "world"]) == {
        "hello": ["BytePlus result summary."],
        "world": ["BytePlus result summary."],
    }
