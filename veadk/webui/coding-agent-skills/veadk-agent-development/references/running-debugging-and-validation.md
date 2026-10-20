# Running, Debugging, and Validation

Run checks in an order that produces useful evidence quickly and isolates failures.

## Establish the runtime facts

Before relying on an API or command, record actual Python and VeADK versions and inspect the installed package location. Check AgentKit CLI version and command help before cloud operations. Do not upgrade dependencies merely to match an unrelated example.

## Local verification sequence

Select the steps relevant to the project, normally in this order:

1. parse or compile changed Python;
2. import Agent definitions and construct required components;
3. run existing and new deterministic tests;
4. call function tools, state stores or retrieval backends directly;
5. run representative Agent requests with stable user and session identities;
6. launch the exact deployment command and probe the HTTP service.

A missing cloud credential does not block safe static and local checks. Report precisely which live checks remain unavailable.

## Process-level service probe

For every deployable project:

1. choose an unused test port and set `PORT`;
2. start the exact command declared for deployment;
3. wait only for a bounded interval;
4. fail if the process exits, including exit status 0;
5. confirm it listens on `0.0.0.0:${PORT:-8000}`;
6. request `/ping` and require a successful response;
7. retain bounded startup output for diagnosis and terminate the process cleanly.

Import success, an exported `app`, or a successful Runner request cannot replace this probe. `/ping` proves service liveness only; it does not prove model, tools, state or business behavior.

## Behavioral checks

Derive cases from the user's success criteria rather than using a fixed count. Include:

- a representative successful request;
- each selected deterministic tool or route;
- material invalid input and unavailable dependency behavior;
- authorization and tenant boundaries for privileged or persistent components;
- an unanswerable query for retrieval-based Agents.

Use a real model request when credentials and network permit. If that is unavailable, distinguish deterministic/structural evidence from unverified model behavior.

## Debugging by symptom

| Symptom | Inspect first | Corrective direction |
|---|---|---|
| Import or construction fails | installed version, traceback, dependency/config names | fix the smallest API, dependency or configuration mismatch |
| Tool result is wrong | direct function call, schema and validation | repair deterministic behavior before model routing |
| State or retrieval is wrong | app/user/session/index identity and direct save/search | repair scope, persistence or indexing semantics |
| Agent response is wrong | instructions, selected tools, Runner events and model output | isolate prompt, model, tool and state causes |
| Process exits before serving | entrypoint and startup logs | invoke the verified serving API and preserve the process |
| `/ping` fails | listener address, port, route and startup exception | repair HTTP configuration before cloud build |
| Cloud build fails | Artifact inventory, dependency source and bounded build output | reproduce the relevant issue locally, then rebuild |
| Runtime does not become `Ready` | status and startup logs | fix entrypoint, port, dependency, identity or platform configuration |
| Real invoke fails | invoke response and Runtime logs | distinguish protocol, auth, model, tool and application failures |

After a repair, rerun the smallest check that exposes the original failure and all directly affected regression tests. Do not repeat an unchanged failing command and expect different evidence.

Before the repaired project can regain `verified` status, rerun the complete cloud sequence
from build through temporary Runtime cleanup. Local test selection may stay risk-based; cloud
validation may not resume from only the previously failed stage because the Artifact changed.

## Evidence quality

Record exact commands, exit status and decision-relevant output without secrets. A warning is non-blocking only when the service and intended behavior still succeed and the warning does not violate a stated requirement. Authentication errors, crashes, request 5xx responses, secret exposure and invalid deployment inputs are blocking.
