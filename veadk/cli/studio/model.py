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


class GetAgentsResponse(BaseModel):
    agents_dir: str
    agents: list[str]


class SetAgentRequest(BaseModel):
    agent_name: str


class SetAgentResponse(BaseModel):
    name: str
    description: str
    model_name: str
    instruction: str
    long_term_memory_backend: str = ""
    knowledgebase_backend: str = ""


class SetRunnerRequest(BaseModel):
    app_name: str
    user_id: str
    session_id: str
    short_term_memory_backend: str
    short_term_memory_db_url: str


class GetMemoryResponse(BaseModel):
    short_term_memory_backend: str
    # short_term_memory_session_number: str
    long_term_memory_backend: str
    # long_term_memory_session_number: str


class GetAgentResponse(BaseModel):
    name: str
    description: str
    model_name: str
    instruction: str


class GetHistorySessionsResponse(BaseModel):
    events: list[str]


class OptimizePromptRequest(BaseModel):
    prompt: str
    feedback: str


class OptimizePromptResponse(BaseModel):
    prompt: str


class ReplacePromptRequest(BaseModel):
    prompt: str


class RunAgentRequest(BaseModel):
    session_id: str
    message: str


class RunAgentResponse(BaseModel):
    event: str


class TraceAgentResponse(BaseModel):
    content: str


class EvaluateAgentResponse(BaseModel):
    content: str


class GetEventResponse(BaseModel):
    event: str


# ========== messages ==========
# class BotMessage(BaseModel):
#     type: str = "bot"
#     event_id: str
#     invocation_id: str
#     timestamp: any
#     content: str
#     prompt_tokens: str
#     candidate_tokens: str


# class ToolMessage(BaseModel):
#     type: str = "tool"
#     event_id: str
#     invocation_id: str
#     function_call_id: str
#     tool_name: str
#     tool_args: dict
#     tool_response: str
#     timestamp: any
#     finish: bool
