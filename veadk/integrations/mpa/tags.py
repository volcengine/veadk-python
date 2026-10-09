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

"""Internal Runtime-tag contract shared by Studio MPA provisioning and discovery."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

MPA_AGENT_TYPE_TAG = "veadk:agent-type"
MPA_AGENT_TYPE_VALUE = "mpa"
MPA_MANAGED_TAG = "veadk:managed"
MPA_MANAGED_VALUE = "true"
MPA_PROVISIONER_TAG = "veadk:provisioner"
MPA_STUDIO_PROVISIONER = "studio-mpa"
MPA_OWNER_TAG = "veadk:owner"
MPA_INSTANCE_ID_TAG = "veadk:mpa-instance-id"


def studio_mpa_runtime_tags(*, owner: str, mpa_instance_id: str) -> dict[str, str]:
    """Return the complete Studio-owned MPA Runtime provenance tags."""

    normalized_owner = owner.strip()
    normalized_instance_id = mpa_instance_id.strip()
    if not normalized_owner:
        raise ValueError("Studio MPA Runtime owner is required")
    if not normalized_instance_id:
        raise ValueError("Studio MPA instance id is required")
    return {
        MPA_AGENT_TYPE_TAG: MPA_AGENT_TYPE_VALUE,
        MPA_MANAGED_TAG: MPA_MANAGED_VALUE,
        MPA_PROVISIONER_TAG: MPA_STUDIO_PROVISIONER,
        MPA_OWNER_TAG: normalized_owner,
        MPA_INSTANCE_ID_TAG: normalized_instance_id,
    }


def merge_runtime_tag_items(
    current: Iterable[Mapping[str, Any]] | None,
    updates: Mapping[str, str],
) -> list[dict[str, str]]:
    """Replace owned tags, retain unrelated tags, and omit platform ``sys:*`` tags."""

    merged: dict[str, str] = {}
    for item in current or ():
        key = str(item.get("Key") or item.get("key") or "").strip()
        if not key or key.startswith("sys:") or key in updates:
            continue
        merged[key] = str(item.get("Value") or item.get("value") or "")
    merged.update(updates)
    return [{"Key": key, "Value": value} for key, value in merged.items()]
