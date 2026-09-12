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

"""Explicit review fields persisted by AgentKit TagResources."""

from __future__ import annotations

import base64
import binascii
import json
import unicodedata
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
TAG_VALUE_LIMIT = 256
APPLICATION_MESSAGE_LIMIT = 20
REVIEW_TEXT_LIMIT = 256
SCHEMA_TAG = "veadk:review:schema"
TEXT_PREFIX = "b64v1:"
FIELDS = {
    "submittedAt": "veadk:review:submitted_at",
    "message": "veadk:review:message",
    "fingerprint": "veadk:review:fingerprint",
    "reviewedAt": "veadk:review:reviewed_at",
    "reason": "veadk:review:reason",
    "comment": "veadk:review:comment",
    "withdrawnAt": "veadk:review:withdrawn_at",
    "unpublishedAt": "veadk:review:unpublished_at",
}
PERSON_FIELDS = {
    "reviewer": {
        "id": "veadk:review:reviewer_id",
        "identityUid": "veadk:review:reviewer_uid",
        "name": "veadk:review:reviewer_name",
    },
    "withdrawnBy": {"id": "veadk:review:withdrawn_by"},
    "unpublishedBy": {"id": "veadk:review:unpublished_by"},
}
DIRECT_TAG = "veadk:review:direct"


def validate_text(value: str, limit: int, label: str) -> str:
    if len(value) > limit:
        raise HTTPException(422, f"{label}不能超过 {limit} 个字")
    return value.strip()


def _encode_text(key: str, value: str) -> dict[str, str]:
    # Keep cloud-supported text readable; encode punctuation/newlines losslessly
    if len(value) > TAG_VALUE_LIMIT:
        raise HTTPException(422, "审批字段超过标签长度上限")
    if (
        len(value.encode()) <= TAG_VALUE_LIMIT
        and not value.startswith(TEXT_PREFIX)
        and all(
            unicodedata.category(char)[0] in {"L", "N", "M"} or char in " _.:/=+-@"
            for char in value
        )
    ):
        return {key: value}
    raw = base64.urlsafe_b64encode(value.encode()).decode()
    parts = [
        raw[start : start + CHUNK_SIZE] for start in range(0, len(raw), CHUNK_SIZE)
    ]
    return {
        key: f"{TEXT_PREFIX}{len(parts)}:{parts[0]}",
        **{f"{key}.{index}": part for index, part in enumerate(parts[1:], 1)},
    }


def _decode_text(tags: dict[str, str], key: str) -> str:
    value = tags.get(key, "")
    if not value.startswith(TEXT_PREFIX):
        return value
    _, size, first = value.split(":", 2)
    count = int(size)
    if not 1 <= count <= 6:
        raise ValueError("Invalid review text part count")
    content = first + "".join(tags[f"{key}.{i}"] for i in range(1, count))
    if len(content) > CHUNK_SIZE * 6:
        raise ValueError("Review text exceeds tag limit")
    return base64.b64decode(content, altchars=b"-_", validate=True).decode()


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
    values = {
        VISIBILITY_TAG: "enterprise"
        if record["status"] == "approved" and record.get("published", True)
        else "private",
        STATUS_TAG: record["status"],
        ID_TAG: record["id"],
        SCHEMA_TAG: "2",
        DIRECT_TAG: "true" if record.get("direct") else "false",
    }
    for field, key in FIELDS.items():
        values.update(_encode_text(key, str(record.get(field) or "")))
    for field, keys in PERSON_FIELDS.items():
        person = record.get(field) or {}
        for attr, key in keys.items():
            values.update(_encode_text(key, str(person.get(attr) or "")))
    return values


def decode_record(tags: dict[str, str]) -> dict[str, Any] | None:
    if not tags.get(ID_TAG):
        return None
    try:
        if tags.get(SCHEMA_TAG) == "2":
            record = {
                "id": tags[ID_TAG],
                "status": tags[STATUS_TAG],
                "published": enterprise_visible(tags),
                "direct": tags.get(DIRECT_TAG) == "true",
                **{field: _decode_text(tags, key) for field, key in FIELDS.items()},
            }
            for field, keys in PERSON_FIELDS.items():
                person = {attr: _decode_text(tags, key) for attr, key in keys.items()}
                record[field] = (
                    {"name": person["id"], "email": "", "avatarUrl": "", **person}
                    if person["id"]
                    else None
                )
            return record
        # Read existing applications without writing the old packed format again
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
    except (ValueError, KeyError, binascii.Error, zlib.error, UnicodeError) as error:
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

    if any(len(value) > TAG_VALUE_LIMIT for value in values.values()):
        raise HTTPException(422, "审批字段超过标签长度上限")
    client.api_info.setdefault(
        "TagResources",
        ApiInfo(
            "POST", "/", {"Action": "TagResources", "Version": "2025-10-30"}, {}, {}
        ),
    )
    # Write continuations first, then all field heads and visibility in one call
    heads = {
        key: value
        for key, value in values.items()
        if not key.rsplit(".", 1)[-1].isdigit()
    }
    parts = [(key, value) for key, value in values.items() if key not in heads]
    if len(heads) > 20:
        raise HTTPException(422, "审批信息超过单次标签写入上限")
    batches = [parts[start : start + 20] for start in range(0, len(parts), 20)]
    batches.append(list(heads.items()))
    for batch in batches:
        client._invoke_api(
            api_action="TagResources",
            request=_TagResources(
                ResourceIds=[runtime_id],
                Tags=[_Tag(Key=k, Value=v) for k, v in batch],
            ),
            response_type=_Result,
        )
