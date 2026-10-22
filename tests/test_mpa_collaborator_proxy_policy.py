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

from veadk.integrations.mpa.collaborator_proxy import collaborator_management_headers


@pytest.mark.parametrize(
    "path",
    [
        "api/v1/studio/collaborators",
        "api/v1/studio/collaborators/registry/spaces",
        "api/v1/studio/collaborators/registry/binding",
    ],
)
def test_collaborator_management_is_admin_only_and_server_key_only(path):
    with pytest.raises(HTTPException) as denied:
        collaborator_management_headers(path, is_admin=False, api_key="runtime-key")
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as missing:
        collaborator_management_headers(path, is_admin=True, api_key="")
    assert missing.value.status_code == 503
    assert collaborator_management_headers(
        path, is_admin=True, api_key="Bearer runtime-key"
    ) == {"X-MPA-Studio-Key": "runtime-key"}
    assert (
        collaborator_management_headers("api/v1/channels", is_admin=False, api_key="")
        == {}
    )


@pytest.mark.parametrize(
    "path",
    [
        "api/v1/studio/%63ollaborators",
        "api/v1/studio//collaborators",
        "api/v1/studio/../studio/collaborators",
    ],
)
def test_aliases_rejected(path):
    with pytest.raises(HTTPException):
        collaborator_management_headers(path, is_admin=True, api_key="key")


def test_unrelated_proxy_paths_are_unchanged():
    assert (
        collaborator_management_headers("api/files/a%20b", is_admin=False, api_key="")
        == {}
    )
