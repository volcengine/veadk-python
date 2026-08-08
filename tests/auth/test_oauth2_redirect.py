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

import pytest
from starlette.requests import Request

from veadk.auth.middleware.oauth2_auth import _resolve_redirect_after_auth


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "server": ("studio.example.com", 443),
            "path": "/oauth2/login",
            "query_string": b"",
            "headers": [(b"host", b"studio.example.com")],
        }
    )


@pytest.mark.parametrize(
    "redirect",
    [
        "//evil.example/phish",
        r"/\\evil.example/phish",
        "/safe\nlocation",
        "https://evil.example/phish",
    ],
)
def test_redirect_rejects_external_or_ambiguous_targets(redirect: str) -> None:
    assert _resolve_redirect_after_auth(_request(), redirect) == "/"


@pytest.mark.parametrize(
    ("redirect", "expected"),
    [
        ("/agents?tab=mine", "/agents?tab=mine"),
        ("agents", "/agents"),
        (
            "https://studio.example.com/agents",
            "https://studio.example.com/agents",
        ),
    ],
)
def test_redirect_keeps_local_targets(redirect: str, expected: str) -> None:
    assert _resolve_redirect_after_auth(_request(), redirect) == expected
