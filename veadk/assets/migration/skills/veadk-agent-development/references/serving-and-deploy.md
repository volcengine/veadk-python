# Serving on :8000 (for deployment)


A deployed agent must be an HTTP server listening on **`0.0.0.0:8000`** (the runtime's
readiness probe). Two options from `agentkit.apps`:

**A. `AgentkitSimpleApp`** — minimal `/ping` `/health` + one entrypoint. Good for a single
request/response agent.

```python
from veadk import Agent, Runner
from agentkit.apps import AgentkitSimpleApp

app = AgentkitSimpleApp()
agent = Agent(name="assistant", instruction="You are helpful.")
runner = Runner(agent=agent, app_name="assistant")

@app.ping
def ping() -> str:
    return "ok"

@app.entrypoint
async def invoke(messages):
    return await runner.run(messages=messages, session_id="default")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
```

**B. `AgentkitAgentServerApp`** — the **full ADK API server** (`/list-apps`, `/run`,
`/run_sse`, session/artifact management, + an `/invoke` compat route). Use this if the
Volcengine console, ADK clients, or `agentkit invoke` (which prefers `/run_sse`) will call it.

```python
from veadk import Agent
from veadk.memory.short_term_memory import ShortTermMemory
from agentkit.apps import AgentkitAgentServerApp

agent = Agent(name="assistant", instruction="You are helpful.")
server = AgentkitAgentServerApp(agent=agent, short_term_memory=ShortTermMemory(backend="local"))
app = server.app          # a FastAPI app
# run: uvicorn module:app --host 0.0.0.0 --port 8000   (or server.run("0.0.0.0", 8000))
```


## Deploy with the `agentkit` CLI

```bash
agentkit init my-agent --template basic --directory ./my-agent
cd ./my-agent
# ... edit the generated Python entrypoint: instruction, tools ...
agentkit release --name my-agent    # first run may write .agentkit/agentkit.yaml for review
agentkit release                    # cloud-builds the image + creates/updates the runtime → Ready + endpoint
agentkit invoke my-agent -m "hello"    # call it (auto-detects /run_sse vs /invoke)
agentkit runtime logs my-agent         # cloud instance logs when something's off
```

Code-free path (config instead of code): `agentkit harness init` → edit `harness.yaml`
(model / tools / knowledgebase / memory) → `agentkit harness set ...` → `agentkit harness deploy`.
