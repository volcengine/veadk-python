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

import pytest

from veadk.integrations.mpa.tags import (
    merge_runtime_tag_items,
    studio_mpa_runtime_tags,
)


def test_studio_mpa_runtime_tags_require_owner_and_instance() -> None:
    with pytest.raises(ValueError, match="owner is required"):
        studio_mpa_runtime_tags(owner=" ", mpa_instance_id="mi-one")
    with pytest.raises(ValueError, match="instance id is required"):
        studio_mpa_runtime_tags(owner="owner-one", mpa_instance_id=" ")


def test_merge_runtime_tag_items_replaces_owned_and_drops_system_tags() -> None:
    updates = studio_mpa_runtime_tags(
        owner=" owner-new ",
        mpa_instance_id=" mi-new ",
    )

    merged = merge_runtime_tag_items(
        [
            {"Key": "custom:retained", "Value": "yes"},
            {"Key": "veadk:owner", "Value": "owner-old"},
            {"Key": "veadk:managed", "Value": "false"},
            {"Key": "sys:tag:createdBy", "Value": "cloud"},
        ],
        updates,
    )

    assert {item["Key"]: item["Value"] for item in merged} == {
        "custom:retained": "yes",
        "veadk:agent-type": "mpa",
        "veadk:managed": "true",
        "veadk:provisioner": "studio-mpa",
        "veadk:owner": "owner-new",
        "veadk:mpa-instance-id": "mi-new",
    }
