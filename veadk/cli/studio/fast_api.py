import json
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

from veadk.cli.studio.models import (
    GetAgentResponse,
    GetEventResponse,
    GetHistoryMessagesResponse,
    GetTracingResponse,
    Message,
    RunnerConfig,
    SpanItem,
    TextPart,
    ToolPart,
)
from veadk.cli.studio.studio_processor import StudioProcessor
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


processor = None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

NEXT_STATIC_DIR = os.path.join(os.path.dirname(__file__), "web")
NEXT_HTML_DIR = NEXT_STATIC_DIR


@app.get("/")
async def read_root():
    index_path = os.path.join(NEXT_HTML_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")


@app.get("/get_history_messages")
async def get_history_messages() -> GetHistoryMessagesResponse:
    session_service = processor.short_term_memory.session_service
    session = await session_service.get_session(
        app_name=processor.runner.app_name,
        user_id=processor.runner.user_id,
        session_id=processor.session_id,
    )

    # prevent no session created
    if session:
        messages = []
        tool_mapping = {}
        for event in session.events:
            formatted_parts = []
            for part in event.content.parts:
                if part.text:
                    formatted_part = TextPart(text=part.text)
                    formatted_parts.append(formatted_part)
                if part.function_call:
                    formatted_part = ToolPart(
                        type="tool-" + part.function_call.name,
                        state="input-available",
                        toolCallId=part.function_call.id,
                        input=part.function_call.args,
                    )
                    tool_mapping[part.function_call.id] = formatted_part
                    formatted_parts.append(formatted_part)
                if part.function_response:
                    formatted_part = tool_mapping[part.function_response.id]
                    formatted_part.output = part.function_response.response
                    formatted_part.state = "output-available"

            if formatted_parts:  # prevent only function_response in event
                session_message = Message(
                    id=event.id,
                    role=event.author if event.author == "user" else "assistant",
                    parts=formatted_parts,
                )
                messages.append(session_message)
        return GetHistoryMessagesResponse(messages=messages)
    else:
        return GetHistoryMessagesResponse(messages=[])


async def runner_run_sse(user_text: str):
    message = types.Content(role="user", parts=[types.Part(text=user_text)])

    await processor.runner.short_term_memory.create_session(
        app_name=processor.runner.app_name,
        user_id=processor.runner.user_id,
        session_id=processor.session_id,
    )

    logger.info("Begin to process user message under SSE method.")

    # message begin
    msg_id = f"msg-{str(uuid.uuid4())}"
    MESSAGE_START = {"type": "start", "messageId": msg_id}
    yield f"data: {json.dumps(MESSAGE_START)}\n\n"

    text_id = f"text-{str(uuid.uuid4())}"
    TEXT_START = {"type": "text-start", "id": text_id}
    yield f"data: {json.dumps(TEXT_START)}\n\n"

    async for event in processor.runner.runner.run_async(
        user_id=processor.runner.user_id,
        session_id=processor.session_id,
        new_message=message,
        run_config=RunConfig(streaming_mode=StreamingMode.SSE),
    ):
        for function_call in event.get_function_calls():
            TOOL_INPUT_START = {
                "type": "tool-input-start",
                "toolCallId": function_call.id,
                "toolName": function_call.name,
            }
            yield f"data: {json.dumps(TOOL_INPUT_START)}\n\n"

            TOOL_INPUT_AVAILABLE = {
                "type": "tool-input-available",
                "toolCallId": function_call.id,
                "toolName": function_call.name,
                "input": function_call.args,
            }
            yield f"data: {json.dumps(TOOL_INPUT_AVAILABLE)}\n\n"

        for function_response in event.get_function_responses():
            TOOL_OUTPUT_AVAILABLE = {
                "type": "tool-output-available",
                "toolCallId": function_response.id,
                "output": function_response.response,
            }
            yield f"data: {json.dumps(TOOL_OUTPUT_AVAILABLE)}\n\n"

        if (
            not event.is_final_response()
            and len(event.content.parts) > 0
            and event.content.parts[0].text
        ):
            TEXT_DELTA = {
                "type": "text-delta",
                "delta": event.content.parts[0].text,
                "id": text_id,
            }
            yield f"data: {json.dumps(TEXT_DELTA)}\n\n"

        if event.is_final_response():
            TEXT_END = {"type": "text-end", "id": text_id}
            yield f"data: {json.dumps(TEXT_END)}\n\n"

            TEXT_FINISH = {"type": "finish", "finishReason": "stop"}
            yield f"data: {json.dumps(TEXT_FINISH)}\n\n"

            DONE = "[DONE]"
            yield f"data: {DONE}\n\n"

    logger.info("SSE Stream Completed.")


@app.post("/run_sse")
async def run_sse(request: Request):
    data = await request.json()
    user_text = data["messages"][-1]["parts"][0]["text"]

    response = StreamingResponse(runner_run_sse(user_text=user_text))
    response.headers["x-vercel-ai-ui-message-stream"] = "v1"
    response.headers["Content-Type"] = "text/event-stream"
    return response


@app.get("/get_agent")
def get_agent() -> GetAgentResponse:
    return GetAgentResponse(
        name=processor.agent.name,
        description=processor.agent.description,
        instruction=processor.agent.instruction,
        model_name=processor.agent.model_name,
        short_term_memory_backend="",
        short_term_memory_db_url="",
        long_term_memory_backend="",
        knowledgebase_backend="",
    )


def parse_tracing_file(filepath: str):
    with open(filepath, "r") as f:
        spans = json.load(f)

    max_latency = -1
    # 1. generate span mapping
    store: dict[str, SpanItem] = {}
    for span in spans:
        event_id = ""
        # in case of root node
        if "gcp.vertex.agent.event_id" in span["attributes"]:
            event_id = str(span["attributes"]["gcp.vertex.agent.event_id"])

        latency = (span["end_time"] - span["start_time"]) / 1000000
        max_latency = max(max_latency, latency)
        span_item = SpanItem(
            name=span["name"],
            span_id=str(span["span_id"]),
            trace_id=str(span["trace_id"]),
            event_id=event_id,
            parent_span_id=str(span["parent_span_id"])
            if span["parent_span_id"]
            else "",
            latency=f"{latency:.2f}",
            latency_proportion="0",
            attributes=span["attributes"],
            childs=[],
        )
        store[str(span["span_id"])] = span_item

    # normalize latency
    for span_item in store.values():
        span_item.latency_proportion = (
            f"{float(span_item.latency) / max_latency * 100:.2f}"
        )

    # 2. build sequencial spans
    root_items = []
    for span_item in store.values():
        if span_item.parent_span_id == "":
            root_items.append(span_item)
        else:
            parent_span = store[span_item.parent_span_id]
            parent_span.childs.append(span_item)

    return root_items


@app.get("/get_tracing")
async def get_tracing() -> GetTracingResponse:
    session_service = processor.short_term_memory.session_service
    session = await session_service.get_session(
        app_name=processor.runner.app_name,
        user_id=processor.runner.user_id,
        session_id=processor.session_id,
    )
    if not session:
        return GetTracingResponse(root_spans=[])
    # ====== prevent existing file ======
    tracing_file_path = processor.tracer.dump(
        processor.runner.user_id, processor.session_id
    )
    os.remove(tracing_file_path)
    # ====== ====================== ======

    tracing_file_path = processor.tracer.dump(
        processor.runner.user_id, processor.session_id
    )
    root_spans = parse_tracing_file(filepath=tracing_file_path)
    os.remove(tracing_file_path)
    return GetTracingResponse(root_spans=root_spans)


@app.get("/get_event")
async def get_event(event_id: str) -> GetEventResponse:
    session_service = processor.short_term_memory.session_service
    session = await session_service.get_session(
        app_name=processor.runner.app_name,
        user_id=processor.runner.user_id,
        session_id=processor.session_id,
    )

    # prevent no session created
    if session:
        for event in session.events:
            if event.id == event_id:
                return GetEventResponse(
                    event=event.model_dump_json(exclude_none=True, by_alias=True)
                )
        return GetEventResponse(event=json.dumps({"info": "not an event span"}))

    return GetEventResponse(event=json.dumps({"info": "not an event span"}))


@app.get("/get_runner_config")
async def get_runner_config() -> RunnerConfig:
    return RunnerConfig(
        app_name=processor.runner.app_name,
        user_id=processor.runner.user_id,
        session_id=processor.session_id,
    )


@app.get("/set_runner_config")
async def set_runner_config(
    app_name: str, user_id: str, session_id: str
) -> RunnerConfig:
    processor.runner.app_name = app_name
    processor.runner.user_id = user_id
    processor.session_id = session_id
    return RunnerConfig(
        app_name=processor.runner.app_name,
        user_id=processor.runner.user_id,
        session_id=processor.session_id,
    )


@app.get("/set_prompt")
async def set_prompt(prompt: str):
    processor.runner.agent.instruction = prompt
    return {"result": "success"}


@app.get("/refine_prompt")
async def refine_prompt(feedback: str):
    refined_prompt = ""  # prevent error processing
    refined_prompt = processor.agent_pilot.optimize(
        agents=[processor.agent], feedback=feedback
    )
    return {"prompt": refined_prompt}


@app.get("/get_testcases")
async def get_testcases():
    test_cases = await processor.get_testcases()
    return {"test_cases": test_cases}


@app.get("/evaluate")
async def evaluate():
    test_cases = await processor.evaluate()
    return {"test_cases": test_cases}


@app.get("/save_session")
async def save_session():
    await processor.runner.save_session_to_long_term_memory(processor.session_id)
    return {"result": "success"}


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


def get_fast_api_app(agent, short_term_memory):
    global processor
    processor = StudioProcessor(
        app_name="veadk_studio",
        user_id="studio_user",
        session_id="studio_session",
        agent=agent,
        short_term_memory=short_term_memory,
    )
    return app
