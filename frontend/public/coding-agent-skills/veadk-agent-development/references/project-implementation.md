# VeADK Project Implementation

Implement the smallest coherent project that satisfies the user's intent and can run locally and on AgentKit.

## Inspect before editing

Read repository instructions, dependency files, current Agent entrypoints, tests and deployment configuration. For a defect, reproduce it at the narrowest reliable boundary before changing code. Preserve working behavior and repository conventions unless evidence requires a contract change.

Inspect the installed or locked VeADK version before choosing imports, constructor fields, model configuration, built-in tool names, memory backends or AgentKit integration helpers. Prefer implementation tests and examples matching that exact version.

## Recommended project responsibilities

The repository may combine or split these responsibilities according to its existing style:

- Agent definition and instructions;
- deterministic tools and external adapters;
- session, memory or knowledge configuration when required;
- executable AgentKit application entrypoint;
- dependency and non-secret configuration declarations;
- focused tests for deterministic and Agent behavior;
- AgentKit deployment configuration.

Do not force a template over a valid project. Every generated file should be required by runtime, testing or delivery.

Keep the deployable project beneath the assigned working root. Put `agentkit.yaml` at the
project root so the installed AgentKit CLI and later deployment resolve the same configuration.
Keep task credentials, validation evidence,
temporary archives, caches, and Runtime logs outside the deliverable project.

## AgentKit initialization

For a new empty project, inspect the installed CLI first:

```bash
ak init --help
ak init --list-templates
```

Choose the application surface independently from the internal Agent topology. A one-Agent
implementation can still require the full ADK HTTP contract; “smallest architecture” is not a
reason to fall back to a narrower application protocol.

With the reviewed CLI `0.52.1`, apply this intent-based policy after confirming the current
template keys:

| Intent | Template | Selection rule |
|---|---|---|
| General VeADK Agent, unspecified application surface, multi-turn/session use, ADK clients, or console integration | `agent_server` (`WebServer App`) | Default for a new empty VeADK project |
| Minimal stateless request/response handler with one entrypoint and no ADK session, artifact, or console contract | `basic` (`Basic App`) | Use `basic` only when the user intent explicitly permits this narrower surface |
| Lightweight streaming handler without the full ADK server contract | `basic_stream` (`Stream App`) | Use only when lightweight streaming is explicit |
| Agent-to-Agent interoperability | `a2a` (`A2A App`) | Use only when A2A is explicit |

Never run bare `ak init`, because its implicit default may not match the product intent. Pass an
explicit template key supported by the installed CLI, for example
`ak init my-agent --template agent_server`. Supply only non-secret arguments; never pass a
model API key through `ak init --model-api-key` because it can enter command traces.

Treat generated files as version-aligned scaffolding, not accepted application code. Inspect
and adapt the Agent definition, instructions, input schema, dependencies, logging, entry point,
`agentkit.yaml`, and `.dockerignore`. In particular, remove logging of complete prompts,
responses, headers, or tool payloads unless the product explicitly requires and protects it.

Do not run `ak init` over a maintained project merely to normalize its layout. When wrapping an
existing Agent with `--from-agent`, inspect the generated diff and retain existing behavior and
tests.

## Agent behavior

Turn the user's intent into observable behavior:

- accepted request forms and expected response content;
- tool or retrieval conditions;
- state scope and persistence expectations;
- external effects and authorization checks;
- relevant invalid, unavailable and timeout behavior.

Instructions should be specific enough to guide behavior without encoding deterministic business rules better implemented in code. Tool descriptions must distinguish capabilities clearly.

## Dependencies and configuration

Pin or constrain dependencies consistently with the repository. Do not add a package until its import and supported version are verified. Record required environment variable names in an existing configuration example without values.

Fail clearly when required configuration is absent. Do not read arbitrary credential files, silently choose insecure defaults or log secret-bearing configuration.

## Executable AgentKit application

A commonly supported shape is:

```python
from veadk import Agent
from veadk.integrations.agentkit import create_agentkit_app, run_agentkit_app

root_agent = Agent(name="assistant", instruction="Answer accurately.")
app = create_agentkit_app(root_agent)

if __name__ == "__main__":
    run_agentkit_app(app)
```

Verify both helpers in the target version. Exporting `root_agent` or `app` only proves an import surface. The declared startup command must actually start the HTTP service, bind `0.0.0.0:${PORT:-8000}`, keep running and expose `/ping`.

If the target version or repository uses another supported server entrypoint, keep that shape and verify the same process-level contract.

Ensure `agentkit.yaml` names the real entry point and dependencies. Verify its schema with the
installed CLI rather than copying an unrelated project. A later user instruction that changes
source, dependencies, entry point, or runtime configuration invalidates prior cloud evidence.

## Test design

Use the cheapest stable test that can expose each failure:

- pure unit tests for deterministic tools and transformations;
- direct backend tests for state, memory and retrieval;
- Agent requests for instruction, tool routing and response behavior;
- process-level probes for startup, port binding and `/ping`;
- deployed invoke and logs for AgentKit behavior.

Mock true external boundaries only. Keep representative failures visible rather than replacing them with generic success fixtures.
