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

import asyncio
import json
from types import SimpleNamespace

from veadk.integrations.mpa.managed.gateway_cloud import GatewayCloud


def test_gateway_reads_universal_sdk_raw_response_when_decoded_result_is_empty(
    monkeypatch,
):
    import volcenginesdkcore
    from volcenginesdkcore import universal

    credentials = SimpleNamespace(
        access_key_id="fake", secret_access_key="fake", session_token="fake"
    )
    raw = {"Result": {"Gateway": {"Id": "g-one"}}}
    client = SimpleNamespace(
        last_response=SimpleNamespace(data=json.dumps(raw).encode())
    )
    monkeypatch.setattr(volcenginesdkcore, "ApiClient", lambda config: client)
    monkeypatch.setattr(
        universal,
        "UniversalApi",
        lambda value: SimpleNamespace(do_call=lambda *a, **kw: {}),
    )
    cloud = GatewayCloud(
        SimpleNamespace(region="cn-beijing", _credentials=lambda: credentials)
    )
    assert asyncio.run(cloud.get_gateway("g-one")) == {"Id": "g-one"}
