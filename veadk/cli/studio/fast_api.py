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
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from veadk.cli.studio.agent_processor import AgentProcessor
from veadk.cli.studio.model import (
    GetAgentResponse,
    GetAgentsResponse,
    GetEventResponse,
    GetHistorySessionsResponse,
    GetMemoryResponse,
    OptimizePromptRequest,
    OptimizePromptResponse,
    ReplacePromptRequest,
    RunAgentRequest,
    RunAgentResponse,
    SetAgentRequest,
    SetAgentResponse,
    SetRunnerRequest,
    TraceAgentResponse,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=None,
    expose_headers=[],
    max_age=600,
)

NEXT_STATIC_DIR = os.path.join(os.path.dirname(__file__), "web")
NEXT_HTML_DIR = NEXT_STATIC_DIR


@app.get("/")
async def read_root():
    index_path = os.path.join(NEXT_HTML_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")


agent_processor = AgentProcessor()


# health check
@app.get("/ping")
async def root():
    return {"message": "pong"}


# get all agents
@app.get("/agents")
async def get_agents() -> GetAgentsResponse:
    agents_dir = agent_processor.agents_dir
    agents = agent_processor.get_agent_names()
    return GetAgentsResponse(agents_dir=agents_dir, agents=agents)


# set current agent
@app.post("/set_agent")
async def set_agent(request: SetAgentRequest) -> SetAgentResponse:
    agent_processor.set_agent(
        agent_name=request.agent_name,
    )
    return SetAgentResponse(
        name=agent_processor.agent.name,
        description=agent_processor.agent.description,
        model_name=agent_processor.agent.model_name,
        instruction=agent_processor.agent.instruction,
        long_term_memory_backend=agent_processor.agent.long_term_memory.backend
        if agent_processor.agent.long_term_memory
        else "",
        knowledgebase_backend=agent_processor.agent.knowledgebase.backend
        if agent_processor.agent.knowledgebase
        else "",
    )


@app.post("/set_runner")
async def set_runner(request: SetRunnerRequest):
    await agent_processor.set_runner(
        app_name=request.app_name,
        user_id=request.user_id,
        session_id=request.session_id,
        short_term_memory_backend=request.short_term_memory_backend,
        short_term_memory_db_url=request.short_term_memory_db_url,
    )
    # TODO: return long & short term memory state
    return {"message": f"Runner set to {request.app_name}"}


@app.get("/memory")
async def get_memory() -> GetMemoryResponse:
    memory_status = agent_processor.get_memory_status()
    return GetMemoryResponse(
        **memory_status,
    )


# get current agent
@app.get("/agent")
async def get_agent() -> GetAgentResponse:
    return GetAgentResponse(
        name=agent_processor.agent.name,
        description=agent_processor.agent.description,
        model_name=agent_processor.agent.model_name,
        instruction=agent_processor.agent.instruction,
    )


@app.post("/optimize_prompt")
async def optimize_prompt(request: OptimizePromptRequest) -> OptimizePromptResponse:
    current_prompt = request.prompt
    feedback = request.feedback
    prompt = agent_processor.optimize_prompt(current_prompt, feedback)
    return OptimizePromptResponse(prompt=prompt)


@app.post("/replace_prompt")
async def replace_prompt(request: ReplacePromptRequest):
    agent_processor.agent.instruction = request.prompt
    return {"message": "Prompt replaced"}


@app.get("/save_session")
async def save_session(session_id: str):
    """Save session to long term memory"""
    await agent_processor.save_session_to_long_term_memory(session_id)
    return {"message": "Session saved"}


@app.post("/update_prompt")
async def update_prompt(request: ReplacePromptRequest):
    agent_processor.agent.instruction = request.prompt
    return {"message": "Prompt replaced"}


@app.get("/history_sessions")
async def get_history_sessions(session_id: str) -> GetHistorySessionsResponse:
    events = await agent_processor.get_history_sessions(session_id)
    return GetHistorySessionsResponse(events=events)


# run agent with user ID
@app.post("/run")
async def run(request: RunAgentRequest) -> RunAgentResponse:
    agent_processor.agent.model._additional_args["stream"] = False
    agent_processor.agent.model._additional_args["stream_options"] = {}

    session_id = request.session_id
    message = request.message
    response = await agent_processor.runner.run_with_final_event(
        messages=message,
        session_id=session_id,
    )
    return RunAgentResponse(event=response)


@app.get("/testcases")
async def get_testcases(session_id: str):
    testcases = await agent_processor.get_testcases(session_id)
    return {"data": testcases}


@app.post("/evaluate")
async def evaluate():
    agent_processor.agent.model._additional_args["stream"] = False
    agent_processor.agent.model._additional_args["stream_options"] = {}

    test_cases = await agent_processor.evaluate()
    return {"data": test_cases}


@app.get("/run_sse")
async def run_sse(session_id: str, message: str):
    return StreamingResponse(
        agent_processor.run_sse(session_id, message),
        media_type="text/event-stream",
    )


@app.get("/trace")
def trace(session_id: str) -> TraceAgentResponse:
    content = agent_processor.trace(
        session_id=session_id,
    )
    return TraceAgentResponse(content=content)


@app.get("/get/event")
async def get_event(session_id: str, invocation_id: str) -> GetEventResponse:
    event_str = await agent_processor.get_event(session_id, invocation_id)
    return GetEventResponse(event=event_str)


app.mount(
    "/_next",
    StaticFiles(directory=os.path.join(NEXT_STATIC_DIR, "_next")),
    name="next_static",
)

app.mount(
    "/",
    StaticFiles(directory=NEXT_STATIC_DIR, html=True),
    name="static",
)


def get_fast_api_app(agents_dir: str) -> FastAPI:
    agent_processor.agents_dir = agents_dir
    return app
