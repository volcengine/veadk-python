# VeADK Architecture and Components

Choose components from observable user requirements, then verify exact APIs against the target VeADK version. Patterns below guide design but do not override an existing valid project structure.

## Minimal architecture

A minimal local Agent commonly has an `Agent`, a `Runner`, and a stable application identity:

```python
import asyncio

from veadk import Agent, Runner

root_agent = Agent(
    name="assistant",
    instruction="Answer accurately and state uncertainty.",
)
runner = Runner(agent=root_agent, app_name="assistant")

result = asyncio.run(
    runner.run(
        messages="Hello",
        user_id="local_user",
        session_id="local_session",
    )
)
print(result)
```

Verify constructor fields and `Runner.run` semantics against the installed version before use.

## Topology selection

| Requirement | Likely shape | Required contract |
|---|---|---|
| One reasoning context and a small tool set | one `Agent` | instruction, tool schemas, final output |
| Fixed ordered stages | `SequentialAgent` | stage inputs/outputs and failure policy |
| Independent branches | `ParallelAgent` | branch isolation, aggregation, partial-failure policy |
| Measurable bounded repetition | `LoopAgent` | exit criterion and maximum iterations |
| Dynamic specialist transfer | root Agent with `sub_agents` | distinct descriptions, transfer and permission boundaries |

Prefer one Agent unless another shape solves a real control-flow requirement. Do not split a simple prompt into cosmetic roles. Parallel branches must not mutate shared resources without coordination, and loops must have a measurable bound.

For deterministic workflows, define producer, consumer, key/schema, missing-data behavior, retry safety and aggregation rules. Verify session-state and `output_key` APIs in the target version.

## Function tools

Use a typed function for deterministic local behavior:

```python
def get_city_weather(city: str) -> dict[str, str]:
    """Return the current weather summary for a city."""
    return {"result": f"Sunny in {city}"}
```

The signature and docstring are model-facing contracts. Validate untrusted inputs and test the function directly before testing model tool selection.

`veadk.tools.get_builtin_tool(name)` accepts only registered names. Inspect `list_builtin_tools()` or the target version's registry before using a string name. A module's presence alone does not prove registry support.

Use MCP only when a capability already has that contract or requires independent discovery. Verify endpoint, authentication, network reachability, tool listing, timeout and failure behavior; expose only necessary actions.

## State and knowledge

| Need | VeADK concept | Verification focus |
|---|---|---|
| Continue one conversation | `ShortTermMemory` / session service | app, user and session identity; restart behavior |
| Recall approved cross-session facts | `LongTermMemory` | save timing, consent, retention, deletion and tenant isolation |
| Search stable domain material | `KnowledgeBase` | ingestion, retrieval relevance, citations and tenant isolation |
| Pass workflow data | session state / explicit output contract | schema, missing values and retry behavior |

Attaching retrieval does not prove writes or indexing work. Test save and retrieval directly, then run an Agent-level request. For knowledge retrieval, include one answerable and one unanswerable query and verify source handling.

## Models and structured output

Verify model names, providers, endpoint fields, structured-output support, fallback behavior and credentials in the target version. Never copy fields from an unpinned newer example into an older dependency.

When output is machine-consumed, validate it against the declared schema and define behavior for invalid model output. Remote model and tool calls need timeouts, an explicit failure policy and logs that do not reveal secret or unnecessary user content.

## Component evidence

For each nontrivial component, identify:

1. target-version import and constructor;
2. non-secret configuration names;
3. automatic or explicit Agent exposure;
4. external effects and permission boundary;
5. smallest direct test;
6. Agent-level integration test;
7. timeout, failure and observability behavior.
