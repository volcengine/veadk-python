# Security and Troubleshooting

Protect credentials and user data throughout implementation, testing, deployment and handoff.

## Credentials

- Use the task's documented credential launcher or private credential file; do not
  discover or select other cloud profiles.
- Read configuration names from a safe example; do not open arbitrary `.env` files.
- Never hardcode or print access keys, secret keys, tokens, passwords or private endpoints.
- Pass credentials only to the process that requires them and keep them out of command history, source, tests and captured output.
- Redact secret-bearing headers, URLs and payload fields before preserving logs.
- If a credential appears in source, Artifact or logs, stop delivery, remove the exposure and report that rotation may be required.

## Artifact safety

Inspect the recursive file inventory before build and delivery. Exclude:

- `.env` and credential files;
- private keys, certificates and cloud profiles;
- VCS metadata;
- Python caches, test caches and coverage output;
- virtual environments and downloaded dependencies;
- local databases, generated user data and transient logs.

An ignore file reduces risk but is not evidence that the produced Artifact is clean.

## Tool and data boundaries

Validate all externally supplied tool inputs. Parameterize database operations, authorize privileged actions at the boundary and request confirmation for destructive or costly effects. Retried write operations need an idempotency strategy.

Define user/session/tenant identity for persistent memory and knowledge. Test isolation explicitly and document retention or deletion behavior when personal data is stored.

Remote calls need an explicit timeout and failure behavior. Do not silently replace failures with plausible Agent answers.

## Logging

Log state transitions and failures with correlation identifiers where the project supports them. Avoid full prompts, model outputs, retrieved documents and tool payloads unless required and approved. Bound cloud log collection by time or count before including excerpts in a report.

## Common delivery failures

| Failure | Required response |
|---|---|
| Unsupported VeADK field or import | inspect installed source/tests and adapt to the target version |
| Required configuration absent | fail with a clear non-secret message and document the variable name |
| Startup process exits successfully | treat as failure; add or select a verified serving entrypoint |
| Service binds only to loopback | bind the deployment service to `0.0.0.0` and rerun the process probe |
| `/ping` works but invoke fails | inspect invoke response and Runtime logs; health is not business behavior |
| Runtime remains non-ready | inspect startup logs, entrypoint, port, dependency and identity configuration |
| Invoke succeeds but logs warn | determine whether the warning affects the stated behavior or safety; report it either way |
| Artifact includes secret or local state | reject it, remove unsafe files, rebuild and rescan |
| Cloud access unavailable | complete local evidence and report build/deploy/Runtime/invoke/logs as unverified |
| Deploy result is unknown | reconcile by the unique validation Runtime name; do not blindly repeat the write |
| User changes source after validation | invalidate the old result and run a fresh full cloud validation |
| Second cloud attempt fails | stop; report evidence-backed `failed`, `blocked`, or `indeterminate` without a third attempt |

## Handoff safety

Report configuration variable names, not values. Include only bounded and sanitized error evidence. Clearly separate successful checks, failed checks and checks not run so a recipient does not deploy on a false assurance.
