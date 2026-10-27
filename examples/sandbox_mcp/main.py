"""VeADK agent with standard MCP tools and SDK-managed sandbox lifecycle."""

import argparse
import asyncio
import os
from contextlib import aclosing
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types

from veadk.sandbox import SandboxManager, SessionKey


def create_runner(*, manager, session_service, app_name="sandbox_mcp_example"):
    """Create once at application startup; reuse for every user/session/turn."""
    from veadk import Agent

    agent = Agent(
        name="sandbox_mcp_agent",
        instruction=(
            "Perform external operations only through the supplied MCP tools. "
            "Follow their schemas and report actual tool results."
        ),
        tools=[],
        sandbox=manager,
    )
    return Runner(
        agent=agent,
        app_name=app_name,
        session_service=session_service,
        auto_create_session=True,
    )


async def run_turn(*, runner, prompt, key):
    """Send one message through the existing Runner."""
    output = ""
    async with aclosing(
        runner.run_async(
            user_id=key.user_id,
            session_id=key.session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
            run_config=RunConfig(max_llm_calls=8),
        )
    ) as stream:
        async for event in stream:
            for part in event.content.parts if event.content else []:
                if part.text and not part.thought:
                    output = part.text
    return output


async def main():
    load_dotenv(Path(__file__).with_name(".env"))
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    if not os.getenv("MODEL_AGENT_API_KEY") and os.getenv("ARK_API_KEY"):
        os.environ["MODEL_AGENT_API_KEY"] = os.environ["ARK_API_KEY"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Run Python print('VEADK_MCP_OK', 1 + 1) in the sandbox.",
    )
    parser.add_argument("--session-id", default="demo")
    parser.add_argument("--user-id", default="local_user")
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument(
        "--follow-up",
        action="append",
        default=[],
        help="Another turn using the same Agent/Runner; repeatable",
    )
    parser.add_argument(
        "--state-dir", type=Path, default=Path(__file__).with_name(".state")
    )
    parser.add_argument(
        "--action",
        choices=["run", "ensure", "status", "pause", "resume", "delete"],
        default="run",
    )
    args = parser.parse_args()
    tool_id = os.getenv("SANDBOX_TOOL_ID") or os.getenv("AGENTKIT_TOOL_ID")
    if not tool_id:
        parser.error("Set SANDBOX_TOOL_ID or AGENTKIT_TOOL_ID")
    manager = SandboxManager(
        tool_id=tool_id,
        state_dir=args.state_dir / "bindings",
        region=os.getenv("SANDBOX_REGION", "cn-beijing"),
        ttl=int(os.getenv("SANDBOX_TTL", "1800")),
    )
    key = SessionKey("sandbox_mcp_example", args.user_id, args.session_id)
    if args.action in {"pause", "resume", "delete"}:
        await getattr(manager, args.action)(key)
        print(await manager.status(key))
    elif args.action == "status":
        print(await manager.status(key))
    elif args.action == "ensure" or args.list_tools:
        async with manager.acquire(key) as lease:
            print(f"SANDBOX_READY session_id={lease.session_id}", flush=True)
            if args.list_tools:
                toolset = McpToolset(
                    connection_params=StreamableHTTPConnectionParams(url=lease.mcp_url)
                )
                try:
                    print(
                        "MCP tools:",
                        ", ".join(tool.name for tool in await toolset.get_tools()),
                    )
                finally:
                    await toolset.close()
    else:
        async with DatabaseSessionService(
            db_url=f"sqlite+aiosqlite:///{args.state_dir.resolve() / 'chats.db'}"
        ) as service:
            runner = create_runner(
                manager=manager, session_service=service, app_name=key.app_name
            )
            try:
                for prompt in [args.prompt, *args.follow_up]:
                    print(await run_turn(runner=runner, prompt=prompt, key=key))
            finally:
                # Application shutdown, not a per-turn operation.
                await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
