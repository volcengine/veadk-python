# Studio source-preserving updates

Component: `studio-source-preserving-updates`. Status: active. Revision: 2026-10-14.
[Chinese](README.zh.md)
[Change design](../../prd-spec/bugfixes/2026-10-13-source-preserving-domain-updates.md)

## Ownership and entry points

Owns Skill/MCP editing for applications whose source cannot be regenerated:
`veadk/cli/legacy_runtime_recovery.py`, `runtime_update_recovery.py`, the related
`cli_frontend.py` routes, `veadk/integrations/agentkit/source_overlay.py` and
`app.py` introspection, plus CustomCreate, ProjectPreview and agentDraftStorage.
The existing `/web/runtime-update-capability` and deployment APIs retain their
authentication/authorization rules. `/web/agent-info/{app_name}` exposes validated
metadata. Domain tool factories retain ownership of tool policy and execution.
This component does not own models, SQL policy, MPA profiles or Runtime scaling.

## Contracts

| ID | Contract |
| --- | --- |
| CON-1 | Source-preserving edits permit only Skill/MCP changes. Preserve the pinned base image, application entrypoint, identity and import paths; ordinary creation/regeneration keeps its current validation/lifecycle. |
| CON-2 | A callable `_veadk_studio_mcp_overlay_handler` validates application-owned MCP without generic replacement. Handler failure is terminal. Supported single-root HTTP bootstrap compares exact `MCP_SERVERS_JSON`; mismatched ownership/configuration fails closed. |
| CON-3 | `managed.json`, `selected.json`, `final.json` express previous, packaged and final Skills. Final selection is authoritative; missing required Skills fail rather than silently disappear. Revision directories are content-addressed and non-root readable. Recovery honors active layout and OCI whiteouts, rejecting links, malformed manifests and bounded-size violations. |
| CON-4 | `sourceOverlay` schema version 1 contains only `mcp: {agentName: [{name, transport, url, authTokenEnv}]}`. Transport is `http`; URLs cannot contain userinfo/query/fragment. Limits: 128 agents, 256 MCP entries, 1 MiB file, 4096 URL characters. Invalid metadata becomes `{schemaVersion: 1, status: "unavailable"}` and blocks editing, including when an ordinary draft is also present. |
| CON-5 | MCP credential values never enter public metadata, build context or browser storage. Existing configured references survive refresh; explicit deletion/replacement is respected. Secrets are resolved only for the exact approved endpoint and emitted only to the authorized deployment environment. |
| CON-6 | Source-preserving publishing skips MPA Profile lifecycle. Asynchronous failures remain failures; a successful build alone cannot mark a Runtime release or real tool invocation successful. |

## State, configuration and compatibility

Recovery transitions to editable source-preserving state only with complete public
metadata and source digest; ambiguous recovery is blocked. Build, Runtime update,
release and actual invocation are distinct stages. Reopening reads the currently
published revision. Existing concurrency/revision checks and cancellation behavior
remain owned by deployment APIs; this change adds no automatic cloud retry.

`VEADK_STUDIO_SKILL_OVERLAY` and `PYTHONPATH` explicitly select the active bootstrap.
MCP credentials are Runtime environment values; image files contain references.
The generated hook delays ADK import until application initialization. Existing
images without overlays keep their existing recovery path. Missing new metadata
after an overlay cannot silently enable source regeneration.

## Verification and change record

CON-1/2: CLI deployment tests and generated hook tests; real domain-factory wrapper
checks. CON-3: Skill, startup and OCI recovery regressions. CON-4/5: introspection,
reopen and credential-storage tests. CON-6: frontend lifecycle tests with normal
creation/regeneration controls. Required workflows must include these tests.

Run repository Python/frontend gates and actual Studio edit/publish/reopen plus
real Skill/MCP invocation against the explicitly authorized target. Offline and
live results are recorded separately in the bilingual PRD. Implementation, two
actual page publications, real Skill/MCP execution and reopening are reconciled.
This does not imply an official Studio release or a mainline merge.

CON-1 Runtime request boundary: omit `Description` and `ApmplusEnable` to retain existing resource descriptions and monitoring settings. Ordinary updates are unaffected.

CON-1 environment boundary: retain existing application environment and metadata.
Do not inherit Studio host settings, create MPA identities/tags, reset environment
selection, or automatically resolve replacement model credentials. The existing
strict disabled-Sidecar filtering contract remains separate.

When an authorized editor cannot pull Skill files, an opaque Skill already selected
by the source image's active overlay must be preserved during the next build. A
digest-pinned preparation stage merges only still-selected previous Skill files
with explicit new inputs; uploaded replacements win and removed Skills stay absent.
The merged selection must respect the same file/byte limits, reject links/special
files and incomplete manifests, and remain readable under the original non-root
user. Bind the new revision to source digest and input files. No live-instance
commands, credential embedding, or registry permission changes are required.
