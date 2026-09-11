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

"""Compact, bounded review metadata persisted by AgentKit TagResources."""

from __future__ import annotations

import base64
import json
import zlib
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

VISIBILITY_TAG = "veadk:visibility"
STATUS_TAG = "veadk:review:status"
ID_TAG = "veadk:review:id"
COUNT_TAG = "veadk:review:parts"
DATA_PREFIX = "veadk:review:data"
MAX_CHUNKS = 16
CHUNK_SIZE = 240


def runtime_tags(runtime: Any) -> dict[str, str]:
    return {
        str(tag.key): str(tag.value or "")
        for tag in getattr(runtime, "tags", None) or []
    }


def enterprise_visible(tags: dict[str, str]) -> bool:
    return (
        tags.get(VISIBILITY_TAG) == "enterprise" and tags.get(STATUS_TAG) == "approved"
    )


def encode_record(record: dict[str, Any]) -> dict[str, str]:
    content = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(zlib.compress(content)).decode()
    parts = [
        encoded[start : start + CHUNK_SIZE]
        for start in range(0, len(encoded), CHUNK_SIZE)
    ]
    if len(parts) > MAX_CHUNKS:
        raise HTTPException(422, "审批信息超过标签容量，请缩短申请说明或审批意见")
    return {
        VISIBILITY_TAG: "enterprise"
        if record["status"] == "approved" and record.get("published", True)
        else "private",
        STATUS_TAG: record["status"],
        ID_TAG: record["id"],
        COUNT_TAG: str(len(parts)),
        **{f"{DATA_PREFIX}{index}": part for index, part in enumerate(parts)},
    }


def decode_record(tags: dict[str, str]) -> dict[str, Any] | None:
    if not tags.get(ID_TAG):
        return None
    try:
        count = int(tags[COUNT_TAG])
        if not 1 <= count <= MAX_CHUNKS:
            raise ValueError("Invalid review part count")
        raw = "".join(tags[f"{DATA_PREFIX}{index}"] for index in range(count))
        if len(raw) > CHUNK_SIZE * MAX_CHUNKS:
            raise ValueError("Review payload exceeds tag limit")
        decoder = zlib.decompressobj()
        content = decoder.decompress(base64.urlsafe_b64decode(raw), 64_001)
        if len(content) > 64_000 or not decoder.eof:
            raise ValueError("Invalid review payload size")
        record = json.loads(content)
        if (
            not isinstance(record, dict)
            or record.get("id") != tags[ID_TAG]
            or record.get("status") != tags[STATUS_TAG]
        ):
            raise ValueError("Inconsistent review metadata")
        return record
    except (ValueError, KeyError, zlib.error, UnicodeError) as error:
        raise HTTPException(502, "Agent 审核标签不完整，请刷新后重试") from error


class _Tag(BaseModel):
    key: str = Field(alias="Key")
    value: str = Field(alias="Value")


class _TagResources(BaseModel):
    resource_type: Literal["runtime"] = Field(default="runtime", alias="ResourceType")
    resource_ids: list[str] = Field(alias="ResourceIds")
    tags: list[_Tag] = Field(alias="Tags")


class _Result(BaseModel):
    pass


def write_runtime_tags(client: Any, runtime_id: str, values: dict[str, str]) -> None:
    from volcengine.ApiInfo import ApiInfo

    if len(values) > 20:
        raise HTTPException(422, "审批信息超过单次标签写入上限")
    client.api_info.setdefault(
        "TagResources",
        ApiInfo(
            "POST", "/", {"Action": "TagResources", "Version": "2025-10-30"}, {}, {}
        ),
    )
    client._invoke_api(
        api_action="TagResources",
        request=_TagResources(
            ResourceIds=[runtime_id],
            Tags=[_Tag(Key=k, Value=v) for k, v in values.items()],
        ),
        response_type=_Result,
    )
