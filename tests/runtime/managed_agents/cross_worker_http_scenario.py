"""Invoked by ma-infra's isolated PostgreSQL/HTTP contract test.

Two persistent Python processes have independent Worker caches. Their only
shared state is the public API. Model/tool outputs are deterministic fixtures;
this is not a live LLM or sandbox test.
"""

import asyncio
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import anthropic
import httpx2
from veadk.runtime.managed_agents.dispatcher import sessions_token

from veadk.runtime.managed_agents.loop import ManagedAgentsLoop


class SessionService:
    async def get_session(self, **_kwargs):
        return object()


class Runner:
    app_name = "contract"
    session_service = SessionService()

    def __init__(self, session_id):
        self.session_id = session_id
        self.calls = []

    async def run_async(self, *, new_message, **_kwargs):
        prompt = new_message.parts[0].text
        self.calls.append(prompt)
        call_id = f"call-{prompt}"
        await self.sdk.beta.sessions.events.send(
            self.session_id,
            events=[
                {"id": call_id, "type": "agent.tool_use", "name": "bash", "input": {}},
                {"type": "user.tool_result", "tool_use_id": call_id, "content": []},
                {"type": "agent.tool_result", "tool_use_id": call_id, "content": []},
            ],
        )
        yield SimpleNamespace(
            partial=False,
            content=SimpleNamespace(
                parts=[SimpleNamespace(text=prompt, thought=False, function_call=None)]
            ),
        )


async def worker():
    config = json.loads(sys.stdin.readline())
    runner = Runner(config["session"])
    loop = ManagedAgentsLoop(runner=runner, session_id=config["session"])
    for line in sys.stdin:
        command = json.loads(line)
        async with anthropic.AsyncAnthropic(
            base_url=config["url"], auth_token=command["secret"], max_retries=0
        ) as sdk:
            runner.sdk = sdk
            if command.get("work"):
                await sdk.beta.environments.work.ack(
                    command["work"], environment_id="env"
                )
                await sdk.beta.environments.work.heartbeat(
                    command["work"],
                    environment_id="env",
                    expected_last_heartbeat="NO_HEARTBEAT",
                    desired_ttl_seconds=90,
                )
            count = await loop.run_pending(sdk)
            if command.get("work"):
                await sdk.beta.environments.work.stop(
                    command["work"], environment_id="env"
                )
            print(json.dumps({"turns": count, "calls": runner.calls}), flush=True)


async def scenario():
    config = {
        "url": os.environ["MANAGED_AGENTS_TEST_URL"],
        "session": os.environ["MANAGED_AGENTS_TEST_SESSION"],
    }
    # Worker children explicitly receive no database/DSN configuration.
    child_env = {
        k: v
        for k, v in os.environ.items()
        if not any(
            s in k.upper()
            for s in ("POSTGRES", "DATABASE", "DSN", "MANAGED_AGENTS_TEST_TOKEN")
        )
    }
    children = [
        subprocess.Popen(
            [sys.executable, __file__, "worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env=child_env,
        )
        for _ in range(2)
    ]
    try:
        for child in children:
            child.stdin.write(json.dumps(config) + "\n")
            child.stdin.flush()
        async with anthropic.AsyncAnthropic(
            base_url=config["url"],
            auth_token=os.environ["MANAGED_AGENTS_TEST_TOKEN"],
            max_retries=0,
        ) as sdk:
            async with httpx2.AsyncClient(base_url=config["url"]) as raw:
                for path in (
                    "/v1/model-work/poll",
                    f"/v1/sessions/{config['session']}/events",
                ):
                    assert (await raw.get(path)).status_code == 401
                    assert (
                        await raw.get(path, headers={"Authorization": "Bearer invalid"})
                    ).status_code == 401
                assert (
                    await raw.get("/internal/v1/model-work/poll")
                ).status_code == 404
                assert (
                    await raw.get(
                        f"/v1/sessions/{config['session']}/events",
                        headers={
                            "Sec-Fetch-Site": "same-origin",
                            "Sec-Fetch-Mode": "cors",
                        },
                    )
                ).status_code == 200
            for index, pod in enumerate((0, 1, 0)):
                prompt = f"input-{index}"
                await sdk.beta.sessions.events.send(
                    config["session"],
                    events=[
                        {
                            "id": prompt,
                            "type": "user.message",
                            "content": [{"type": "text", "text": prompt}],
                        }
                    ],
                )
                from anthropic.types.beta.environments import BetaSelfHostedWork

                response = await sdk.get("/v1/model-work/poll", cast_to=httpx2.Response)
                assert response.status_code == 200
                claimed = BetaSelfHostedWork.model_validate(response.json())
                assert claimed is not None
                child = children[pod]
                lease = sessions_token(claimed.secret)
                assert lease
                child.stdin.write(
                    json.dumps({"work": claimed.id, "secret": lease}) + "\n"
                )
                child.stdin.flush()
                reply = json.loads(
                    await asyncio.wait_for(
                        asyncio.to_thread(child.stdout.readline), timeout=30
                    )
                )
                assert reply["turns"] == 1 and reply["calls"][-1] == prompt, reply
                empty = await sdk.get("/v1/model-work/poll", cast_to=httpx2.Response)
                assert empty is not None and empty.status_code == 204, (
                    "completed input created successor"
                )

                # Stopped lease remains fenced through the edge, never becomes app identity.
                async with httpx2.AsyncClient(base_url=config["url"]) as raw:
                    stale = await raw.get(
                        f"/v1/sessions/{config['session']}/events",
                        headers={"Authorization": f"Bearer {lease}"},
                    )
                    assert stale.status_code in (401, 412), stale.status_code
                history = [
                    e
                    async for e in sdk.beta.sessions.events.list(
                        config["session"], order="asc"
                    )
                ]
                idle = history[-1]
                assert idle.type == "session.status_idle"
                rows = [
                    row
                    async for row in sdk.beta.environments.work.list(
                        "env", session_id=config["session"]
                    )
                ]
                assert rows and all(row.state == "stopped" for row in rows)
            # Fresh Worker reconstructs completion using public history alone.
            fresh = ManagedAgentsLoop(
                runner=Runner(config["session"]), session_id=config["session"]
            )
            assert await fresh.run_pending(sdk) == 0
            print(
                "two isolated Worker processes: three inputs, three executions; terminal Work graph verified"
            )
    finally:
        for child in children:
            child.stdin.close()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            assert child.returncode == 0, child.returncode


if __name__ == "__main__":
    asyncio.run(worker() if sys.argv[1:] == ["worker"] else scenario())
