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

from pydantic import BaseModel


class GetAgentResponse(BaseModel):
    name: str
    description: str
    instruction: str
    model_name: str
    short_term_memory_backend: str
    short_term_memory_db_url: str
    long_term_memory_backend: str
    knowledgebase_backend: str


class SpanItem(BaseModel):
    name: str
    span_id: str
    trace_id: str
    event_id: str
    parent_span_id: str
    latency: str
    latency_proportion: str
    attributes: dict
    childs: list["SpanItem"]


class GetTracingResponse(BaseModel):
    root_spans: list[SpanItem]


class GetEventResponse(BaseModel):
    event: str


class RunnerConfig(BaseModel):
    app_name: str
    user_id: str
    session_id: str


class TextPart(BaseModel):
    type: str = "text"
    state: str = "done"
    text: str


class ToolPart(BaseModel):
    type: str
    toolCallId: str
    state: str = ""
    input: dict = {}
    output: dict = {}


class Message(BaseModel):
    id: str
    role: str
    parts: list[TextPart | ToolPart]


class GetHistoryMessagesResponse(BaseModel):
    messages: list[Message]
