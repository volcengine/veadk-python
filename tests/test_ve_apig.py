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

from types import SimpleNamespace
from typing import Any

from veadk.integrations.ve_apig.ve_apig import APIGateway


def test_disable_route_cors_turns_off_credentials_and_origin_reflection() -> None:
    captured: dict[str, Any] = {}

    class _Result:
        def __init__(self, value: Any) -> None:
            self.value = value

        def get(self) -> Any:
            return self.value

    class _Client:
        def get_route(self, request: Any, *, async_req: bool) -> _Result:
            captured["get_request"] = request
            return _Result(
                SimpleNamespace(
                    route=SimpleNamespace(
                        name="studio-route",
                        enable=True,
                        fallback_setting="fallback",
                        match_rule="match",
                        priority=10,
                        upstream_list="upstream",
                        advanced_setting=SimpleNamespace(
                            header_operations="headers",
                            mirror_policies="mirrors",
                            retry_policy_setting="retry",
                            timeout_setting="timeout",
                            url_rewrite_setting="rewrite",
                        ),
                    )
                )
            )

        def update_route(self, request: Any, *, async_req: bool) -> _Result:
            captured["request"] = request
            captured["async_req"] = async_req
            return _Result(None)

    gateway = object.__new__(APIGateway)
    gateway.apig_20221112_client = _Client()

    gateway.disable_route_cors("route-1")

    request = captured["request"]
    cors = request.advanced_setting.cors_policy_setting
    assert request.id == "route-1"
    assert request.name == "studio-route"
    assert request.match_rule == "match"
    assert request.upstream_list == "upstream"
    assert request.advanced_setting.timeout_setting == "timeout"
    assert cors.enable is False
    assert cors.allow_credentials is False
    assert captured["async_req"] is True
