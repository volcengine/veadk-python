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
from fastapi import HTTPException

from veadk.integrations.mpa.agents_md_proxy import agents_md_management_headers


def test_only_admin_receives_server_owned_runtime_key():
    path = "api/v1/studio/agents-md"
    assert agents_md_management_headers(
        path, is_admin=True, api_key="Bearer fixture-key"
    ) == {"X-MPA-Studio-Key": "fixture-key"}
    for admin, key, status in [(False, "fixture-key", 403), (True, "", 503)]:
        with pytest.raises(HTTPException) as error:
            agents_md_management_headers(path, is_admin=admin, api_key=key)
        assert error.value.status_code == status
    assert (
        agents_md_management_headers(
            "api/v1/studio/agent-info", is_admin=False, api_key=""
        )
        == {}
    )


@pytest.mark.parametrize(
    "path",
    [
        "api/v1/studio/%61gents-md",
        "api/v1/studio//agents-md",
        "api/v1/studio/../studio/agents-md",
    ],
)
def test_noncanonical_paths_cannot_bypass_authorization(path):
    with pytest.raises(HTTPException) as error:
        agents_md_management_headers(path, is_admin=True, api_key="fixture-key")
    assert error.value.status_code == 400
