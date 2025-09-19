import os
from contextlib import asynccontextmanager
from typing import Callable
from fastapi import FastAPI
from starlette.applications import Starlette
import threading
from fastapi.routing import APIRoute
from starlette.routing import Route
from google.adk.agents import BaseAgent
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from uvicorn.importer import import_from_string
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from fastmcp import FastMCP
from a2a.types import AgentProvider
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter
from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporter
from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.utils.logger import get_logger
from veadk.runner import Runner
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry import context
import asyncio
from veadk.memory.short_term_memory import ShortTermMemory


logger = get_logger(__name__)

VEFAAS_REGION = os.getenv("APP_REGION", "cn-beijing")
VEFAAS_FUNC_ID = os.getenv("_FAAS_FUNC_ID", "")

# Get entrypoint agent
entrypoint_agent_string = os.getenv("VEADK_ENTRYPOINT_AGENT", None)
entrypoint_agent = import_from_string(entrypoint_agent_string)
HOST = "0.0.0.0"
PORT = 8000

assert isinstance(entrypoint_agent, BaseAgent), (
    "The entrypoint agent must be an instance of BaseAgent."
)

# Get app_name from environment variable
app_name = os.getenv("APP_NAME", "veadk-app")


def veadk_to_a2a(
    agent: BaseAgent, *, host: str = "localhost", port: int = 8000
) -> Starlette:
    # Patch A2aAgentExecutor
    original_init = A2aAgentExecutor.__init__

    def patched_init(self, *, runner=None, config=None):
        original_init(
            self,
            runner=Runner(
                agent=agent,
                app_name="veadk_agent",
                user_id="user_123",
                short_term_memory=ShortTermMemory(),
            ),
            config=config,
        )

    A2aAgentExecutor.__init__ = patched_init
    app = to_a2a(agent=agent, host=host, port=port)
    A2aAgentExecutor.__init__ = original_init

    return app


def load_tracer(agent: BaseAgent) -> None:
    EXPORTER_REGISTRY = {
        "VEADK_TRACER_APMPLUS": APMPlusExporter,
        "VEADK_TRACER_COZELOOP": CozeloopExporter,
        "VEADK_TRACER_TLS": TLSExporter,
    }

    exporters = []
    for env_var, exporter_cls in EXPORTER_REGISTRY.items():
        if os.getenv(env_var, "").lower() == "true":
            if (
                agent.tracers
                and isinstance(agent.tracers[0], OpentelemetryTracer)
                and any(isinstance(e, exporter_cls) for e in agent.tracers[0].exporters)
            ):
                logger.warning(
                    f"Exporter {exporter_cls.__name__} is already defined in agent.tracers[0].exporters. These two exporters will be used at the same time. As a result, your data may be uploaded twice."
                )
            else:
                exporters.append(exporter_cls())

    tracer = OpentelemetryTracer(name="veadk_tracer", exporters=exporters)
    agent.tracers.extend([tracer])


def build_run_agent_func(
    agent: BaseAgent, app_name: str, short_term_memory=None
) -> Callable:
    runner = Runner(
        agent=agent,
        short_term_memory=short_term_memory,
        app_name=app_name,
        user_id="",
    )

    async def run_agent(
        user_input: str,
        user_id: str = "mcp_user",
        session_id: str = "mcp_session",
    ) -> str:
        runner.user_id = user_id
        final_output = await runner.run(
            messages=user_input,
            session_id=session_id,
        )
        return final_output

    run_agent_doc = f"""{agent.description}
    Args:
        user_input: User's input message (required).
        user_id: User identifier. Defaults to "mcp_user".
        session_id: Session identifier. Defaults to "mcp_session".
    Returns:
        Final agent response as a string."""

    run_agent.__doc__ = run_agent_doc
    return run_agent


def _to_a2a(agent: BaseAgent) -> FastAPI:
    # Use to_a2a to create Starlette app, then convert to FastAPI
    starlette_app = veadk_to_a2a(agent=agent, host=HOST, port=PORT)

    # Create FastAPI app and import Starlette routes
    fastapi_app = FastAPI()

    # Import A2A routes to FastAPI app
    # Execute startup event to generate routes

    # async def trigger_startup():
    #     for handler in starlette_app.router.on_startup:
    #         await handler() if asyncio.iscoroutinefunction(handler) else handler()
    # asyncio.run(trigger_startup())

    def run_async_startup():
        """Run startup handlers in a new event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def trigger_startup():
            for handler in starlette_app.router.on_startup:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()

        loop.run_until_complete(trigger_startup())
        loop.close()

    try:
        asyncio.get_running_loop()
        # if in event loop, run in another thread
        thread = threading.Thread(target=run_async_startup)
        thread.start()
        thread.join()
    except RuntimeError:
        # if not in event loop, run in current thread
        run_async_startup()

    # Copy routes to FastAPI
    fastapi_app.router.routes.extend(starlette_app.routes)
    return fastapi_app


def _to_mcp(a2a_app: FastAPI, app_name: str):
    # Build mcp server
    mcp = FastMCP.from_fastapi(app=a2a_app, name=app_name, include_tags={"mcp"})

    # Create MCP ASGI app
    mcp_app = mcp.http_app(path="/", transport="streamable-http")

    return mcp_app


def _custom_routes(a2a_app: FastAPI, agent: BaseAgent, run_agent_func: Callable):
    agent_card_builder = AgentCardBuilder(
        agent=agent,
        provider=AgentProvider(
            organization="Volcengine Agent Development Kit (VeADK)",
            url=f"https://console.volcengine.com/vefaas/region:vefaas+{VEFAAS_REGION}/function/detail/{VEFAAS_FUNC_ID}",
        ),
    )

    async def agent_card() -> dict:
        agent_card = await agent_card_builder.build()
        return agent_card.model_dump()

    async def get_cozeloop_space_id() -> dict:
        return {
            "space_id": os.getenv(
                "OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME", default=""
            )
        }

    a2a_app.post("/run_agent", operation_id="run_agent", tags=["mcp"])(run_agent_func)
    a2a_app.get("/agent_card", operation_id="agent_card", tags=["mcp"])(agent_card)
    a2a_app.get(
        "/get_cozeloop_space_id", operation_id="get_cozeloop_space_id", tags=["mcp"]
    )(get_cozeloop_space_id)


def agent_to_server(agent: BaseAgent, app_name: str) -> FastAPI:
    load_tracer(agent)

    # Build a run_agent function for building MCP server
    run_agent_func = build_run_agent_func(agent, app_name, short_term_memory=None)

    # a2a_app
    a2a_app = _to_a2a(agent)

    # Add custom routes to a2a_app
    _custom_routes(a2a_app, agent, run_agent_func)

    # Build mcp server
    mcp_app = _to_mcp(a2a_app, app_name)

    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        async with mcp_app.lifespan(app):
            yield

    # Create main FastAPI app with combined lifespan
    app = FastAPI(
        title=a2a_app.title,
        version=a2a_app.version,
        lifespan=combined_lifespan,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    # Add otel context middleware
    @app.middleware("http")
    async def otel_context_middleware(request, call_next):
        carrier = {
            "traceparent": request.headers.get("Traceparent"),
            "tracestate": request.headers.get("Tracestate"),
        }
        logger.debug(f"carrier: {carrier}")
        if carrier["traceparent"] is None:
            return await call_next(request)
        else:
            ctx = TraceContextTextMapPropagator().extract(carrier=carrier)
            logger.debug(f"ctx: {ctx}")
            token = context.attach(ctx)
            try:
                response = await call_next(request)
            finally:
                context.detach(token)
        return response

    # Mount A2A routes to app
    for route in a2a_app.routes:
        app.routes.append(route)

    # Mount MCP server at /mcp endpoint of app
    app.mount("/mcp", mcp_app)

    # Remove openapi routes
    paths = ["/openapi.json", "/docs", "/redoc"]
    new_routes = []
    for route in app.router.routes:
        if isinstance(route, (APIRoute, Route)) and route.path in paths:
            continue
        new_routes.append(route)
    app.router.routes = new_routes

    return app


app = agent_to_server(agent=entrypoint_agent, app_name=app_name)
