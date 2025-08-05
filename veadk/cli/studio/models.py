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
