"""Turn-scoped model binding and portable Responses continuation.

Only opted-in execution enters this module. The concrete model is visible to
ADK before its processors run; the full request survives until the transport
chooses a validated continuation or a new chain.
"""

from __future__ import annotations

import copy
import hashlib
import json
from contextlib import aclosing, asynccontextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any

from google.adk.events import Event, EventActions
from google.adk.flows.llm_flows import (
    contents,
    interactions_processor,
    instructions,
    basic,
)
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from google.adk.tools import BaseTool, FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from veadk.routing.context import RouteSelection, TurnContext, _TURN, get_turn_context

_METADATA = "veadk_query_routing"
_RECORD = "veadk:query_routing:turn"


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def target_id(model: Any) -> str:
    # Only the digest leaves this function; credentials never enter metadata.
    return digest(
        (
            type(model).__module__,
            type(model).__qualname__,
            model.model,
            getattr(model, "_additional_args", {}),
            getattr(model, "fallbacks", None),
            getattr(model, "enable_responses_cache", None),
        )
    )


def _content_data(items: list[Any]) -> list[Any]:
    return [item.model_dump(exclude_none=True) for item in items]


@dataclass
class RequestState:
    contents: list[Any]
    config_hash: str = ""


_REQUEST: ContextVar[RequestState | None] = ContextVar(
    "veadk_routing_request", default=None
)


def prepare_flow(flow: Any) -> Any:
    if get_turn_context() is not None:
        # Keep contents in full, including function IDs. Continuation is chosen
        # after all processors and user callbacks, never before history replay.
        flow.request_processors = [
            p
            for p in flow.request_processors
            if p is not interactions_processor.request_processor
        ]
    return flow


def _previous_id(
    callback_context: Any, request: LlmRequest, turn: TurnContext, config_hash: str
) -> str | None:
    ctx = callback_context._invocation_context
    for event in reversed(ctx.session.events):
        if event.branch != ctx.branch or event.isolation_scope != ctx.isolation_scope:
            continue
        if not event.content or event.content.role != "model" or event.partial:
            continue
        # An intervening model/agent response invalidates the old chain.
        metadata = (event.custom_metadata or {}).get(_METADATA, {})
        size = metadata.get("prefix_size", 0)
        if (
            event.author != ctx.agent.name
            or metadata.get("target") != turn.target
            or metadata.get("config_hash") != config_hash
            or not size
        ):
            return None
        if digest(_content_data(request.contents[:size])) != metadata.get(
            "prefix_hash"
        ):
            return None
        return event.interaction_id
    return None


def _portable_contents(ctx: Any, items: list[Any], target: str) -> list[Any]:
    """Replay business content without another target's opaque reasoning state."""
    owned_parts = {
        digest(part.model_dump(exclude_none=True))
        for event in ctx.session.events
        if (event.custom_metadata or {}).get(_METADATA, {}).get("target") == target
        and event.content
        for part in event.content.parts or []
    }
    result = []
    for content in copy.deepcopy(items):
        portable = []
        for part in content.parts or []:
            if digest(part.model_dump(exclude_none=True)) not in owned_parts:
                part.thought_signature = None
                if part.thought:
                    if not (part.function_call or part.function_response):
                        continue
                    part.thought = None
            if part.model_dump(exclude_none=True):
                portable.append(part)
        if portable:
            content.parts = portable
            result.append(content)
    return result


async def bind_request(callback_context: Any, llm_request: LlmRequest) -> None:
    turn = get_turn_context()
    state = _REQUEST.get()
    if turn is None or state is None:
        return
    from veadk.routing.agent_tool import inherit_tool

    if target_id(turn.model) != turn.target:
        raise ValueError("routing model configuration changed during the turn")
    replacements = {
        id(tool): inherit_tool(tool) for tool in llm_request.tools_dict.values()
    }
    llm_request.tools_dict = {
        name: replacements[id(tool)] for name, tool in llm_request.tools_dict.items()
    }
    ctx = callback_context._invocation_context
    if ctx.canonical_tools_cache is not None:
        ctx.canonical_tools_cache = [
            replacements.get(id(tool), tool) for tool in ctx.canonical_tools_cache
        ]
    if turn.selection.route == "simple":
        runtime = turn.router.registry.get(turn.selection.model_name)
        check = turn.router.registry.check(llm_request, runtime)
        if not check.allowed:
            raise ValueError(
                f"fixed routing model cannot serve this request: {check.reason}"
            )
    llm_request.contents = _portable_contents(ctx, llm_request.contents, turn.target)
    llm_request.model = turn.model.model
    llm_request.previous_interaction_id = None
    state.contents = copy.deepcopy(llm_request.contents)
    state.config_hash = digest(llm_request.config.model_dump(exclude_none=True))
    if getattr(turn.model, "enable_responses_cache", False):
        llm_request.previous_interaction_id = _previous_id(
            callback_context, llm_request, turn, state.config_hash
        )


def _tag_event(event: Event, ctx: Any, turn: TurnContext) -> None:
    state = _REQUEST.get()
    if (
        state is None
        or event.author != ctx.agent.name
        or event.partial
        or not event.content
        or event.content.role != "model"
    ):
        return
    prefix = [*state.contents, event.content]
    metadata = {
        "root_turn_id": turn.selection.invocation_id,
        "route": turn.selection.route,
        "model": turn.model.model,
        "target": turn.target,
        "prefix_size": len(prefix),
        "prefix_hash": digest(_content_data(prefix)),
        "config_hash": state.config_hash,
    }
    event.custom_metadata = {**(event.custom_metadata or {}), _METADATA: metadata}


def _agents(root: Any) -> list[Any]:
    pending, found, seen = [root], [], set()
    while pending:
        agent = pending.pop()
        if id(agent) in seen:
            continue
        seen.add(id(agent))
        found.append(agent)
        pending.extend(getattr(agent, "sub_agents", ()))
        pending.extend(
            t.agent for t in getattr(agent, "tools", ()) if hasattr(t, "agent")
        )
    return found


def routing_owner(agent: Any) -> Any:
    """Find the outermost configured router, including resumed transfer targets."""
    from veadk.routing.llm import RoutingLlm

    owner = None
    while agent is not None:
        if isinstance(getattr(agent, "model", None), RoutingLlm):
            owner = agent
        agent = agent.parent_agent
    return owner


async def routing_request(agent: Any, ctx: Any) -> LlmRequest:
    request = LlmRequest()
    async for _ in contents.request_processor.run_async(ctx, request):
        pass
    async for _ in basic.request_processor.run_async(ctx, request):
        pass
    async for _ in instructions.request_processor.run_async(ctx, request):
        pass
    for member in _agents(routing_owner(agent) or agent):
        for tool in getattr(member, "tools", ()):
            name = getattr(tool, "name", None) or getattr(
                tool, "__name__", type(tool).__name__
            )
            request.tools_dict[f"{member.name}.{name}"] = tool
            if isinstance(tool, BaseToolset):
                # Tools discovered during execution cannot be classified from a
                # guessed schema; keep the strong model for this turn.
                request.config.labels = {"routing_incomplete": "dynamic_toolset"}
            else:
                concrete = tool if isinstance(tool, BaseTool) else FunctionTool(tool)
                declaration = concrete._get_declaration()
                if declaration:
                    request.config.tools = [
                        *(request.config.tools or []),
                        types.Tool(function_declarations=[declaration]),
                    ]
        if getattr(member, "output_schema", None):
            request.config.response_json_schema = (
                member.output_schema.model_json_schema()
            )
    return request


async def _select(agent: Any, ctx: Any, router: Any) -> TurnContext:
    config_hash = configuration_id(router)
    record = ctx.session.state.get(_RECORD, {})
    if record.get("invocation_id") == ctx.invocation_id:
        if record.get("config_hash") != config_hash:
            raise ValueError("routing configuration changed during a resumed turn")
        selection = RouteSelection(**record["selection"])
    else:
        request = await routing_request(agent, ctx)
        key = f"{ctx.app_name}:{ctx.user_id}:{ctx.session.id}:{ctx.invocation_id}:{config_hash}"
        selection = await router.store.get_or_create(
            key,
            lambda: router.classifier.classify(
                request,
                invocation_id=ctx.invocation_id,
                session_id=ctx.session.id,
            ),
        )
    model = router.selected_model(selection)
    return TurnContext(selection, model, router, target_id(model))


def configuration_id(router: Any) -> str:
    return digest(
        (
            router.config.model_dump(mode="json"),
            target_id(router.strong_model),
            [target_id(r.llm) for r in router.runtimes],
        )
    )


@asynccontextmanager
async def _scope(agent: Any, ctx: Any):
    inherited = get_turn_context()
    router = inherited.router if inherited else routing_owner(agent).model
    if inherited is None:
        router.active_runs += 1
    try:
        turn = inherited or await _select(agent, ctx, router)
        token = _TURN.set(turn)
        request_token = _REQUEST.set(RequestState([]))
        try:
            yield turn, inherited is None
        finally:
            _REQUEST.reset(request_token)
            _TURN.reset(token)
    finally:
        if inherited is None:
            router.active_runs -= 1
            if router.active_runs == 0:
                await router.classifier.aclose()


async def run_routed(agent: Any, ctx: Any, execute: Any):
    async with _scope(agent, ctx) as (turn, is_root):
        if is_root:
            record = {
                "invocation_id": ctx.invocation_id,
                "config_hash": configuration_id(turn.router),
                "selection": asdict(turn.selection),
            }
            yield Event(
                author=agent.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                actions=EventActions(state_delta={_RECORD: record}),
                custom_metadata={
                    _METADATA: {
                        "root_turn_id": ctx.invocation_id,
                        "route": turn.selection.route,
                        "model": turn.model.model,
                        "reason": turn.selection.reason,
                        "latency_ms": turn.selection.latency_ms,
                        "input_tokens": turn.selection.input_tokens,
                    }
                },
            )
        async with aclosing(execute(ctx)) as events:
            async for event in events:
                _tag_event(event, ctx, turn)
                yield event
