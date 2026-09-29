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

"""Runtime-owned evaluation collections and samples"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    id: str
    created_at: str = Field(default_factory=now, alias="createdAt")
    updated_at: str = Field(default_factory=now, alias="updatedAt")
    deleted_at: str | None = Field(default=None, alias="deletedAt")
    revision: str = Field(default="", exclude=True)


class EvaluationSet(Record):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=4000)
    default_kind: Literal["good", "bad"] | None = Field(
        default=None, alias="defaultKind"
    )
    created_by: str = Field(default="", alias="createdBy")


class Sample(Record):
    evaluation_set_id: str = Field(alias="evaluationSetId", min_length=1)
    source: Literal["user", "auto"]
    kind: Literal["good", "bad"] | None = None
    input: str = Field(max_length=200_000)
    output: str = Field(max_length=200_000)
    reference_output: str = Field(
        default="", alias="referenceOutput", max_length=200_000
    )
    comment: str = Field(default="", max_length=20_000)
    user_id: str = Field(default="", alias="userId")
    session_id: str = Field(default="", alias="sessionId")
    message_id: str = Field(default="", alias="messageId")
    invocation_id: str = Field(default="", alias="invocationId")
    score: float | None = Field(default=None, ge=0, le=1)
    reason: str = Field(default="", max_length=20_000)
    evaluator_version: str = Field(default="", alias="evaluatorVersion")


def public_record(record: Record) -> dict:
    return {
        **record.model_dump(mode="json", by_alias=True),
        "revision": record.revision,
    }
