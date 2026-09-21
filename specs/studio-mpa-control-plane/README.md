# Studio MPA Control Plane

- Component ID: `studio-mpa-control-plane`
- Status: Phase 1 implemented; Phase 2 partially implemented
- Revision: 2026-09-13
- Chinese: [README.zh.md](README.zh.md)
- PRD: [MPA Studio Turn Control and Resource Workspace](../../prd-spec/features/mpa-studio-control-plane/2026-09-13-mpa-studio-control-plane-design.md)

## Responsibility

Own the Studio-to-mpa-agent contract for Ark model discovery, immutable Turn snapshots, whole-Turn lifecycle commands/status, Session resource mounts, typed runtime topology, Studio tool discovery, and role-protected secret copy. mpa-agent is the lifecycle authority; Studio is a client and presentation layer.

## Contracts

- `CON-1`: Account model discovery is server-side, credential-free in browser payloads, compatibility-filtered, cached with freshness, and fails explicitly.
- `CON-2`: An accepted Turn freezes its model and submitted resource payload. Non-terminal Turns never observe later browser-side Session edits. A server-owned Session resource revision is not implemented yet.
- `CON-3`: Lifecycle state is durable and generation-controlled. Studio exposes idempotent pause/resume only. `paused` requires main executor and all active workers at safe points.
- `CON-4`: Pause and resume share the Composer primary button. Resume within five minutes continues the same Turn; an expired or unrecoverable resume requires the user's click and creates an incremental Turn in the same Session. Disconnect and timeout alone never start work.
- `CON-5`: Studio currently stores Session mount selections in browser local storage and submits stable Skill Space IDs and versions with the next Turn. Server-owned revisions, conflict detection, and retained invalid-resource state remain follow-up work.
- `CON-6`: Topology contains only configured/observed nodes and typed edges; absent optional resources are affordances, not active nodes.
- `CON-7`: Agent Card capabilities gate model, lifecycle, mounts, and topology behavior for backward compatibility.
- `CON-8`: Environment list responses never contain secret values. Authorized secret copy is no-store, audited without value, and never rendered or persisted by Studio.
- `CON-9`: Composer uses one footer row for attachment, Agent target, model, usage/status, and one stateful primary button. The button means send, pause, pending, or resume according to authoritative Turn state; responsive layouts cannot overlap.
- `CON-10`: Usage exposes input/output/reasoning/cache/total for current Turn and cumulative Session; replay is monotonic-delta safe.
- `CON-11`: Conversation projection preserves `reasoning` and Agent `thought` as distinct semantic kinds. Stable event identity is preferred; cross-channel text deduplication is limited to exact or cumulative-prefix transport replays within the same task/invocation and kind.
- `CON-12`: Tool activity exposes a tool-specific safe action and subject. Unknown tools expose their concrete name rather than a generic completed label.
- `CON-13`: Sanitized tool inputs/results remain completely retrievable by an explicit copy/download action. Preview rendering is bounded, truncation is disclosed, and all detail paths share the same redaction rules.
- `CON-14`: Turn model selection is searchable and keyboard accessible, and remains disabled while a non-terminal Turn owns an immutable model snapshot.
- `CON-15`: Runtime listing exposes `agentCategory` and accepts `agentCategory=general|mpa` for server-side category filtering before visible pagination. The authoritative and only MPA source is Runtime tag `veadk:agent-type=mpa`; image names and artifact URLs are not category inputs. `agentCategory=mpa` must first query the Volcano Tag service with a positive tag filter to obtain candidate Runtime IDs, then hydrate those records by Runtime ID, so sparse MPA results do not require scanning unrelated Runtime pages.

## State and data

+ Studio-visible Turn states: `queued`, `running`, `pausing`, `paused`, `resuming`, `interrupted`, `completed`, `failed`. Internal terminalization states may exist but are not user actions.
+ Turn control stores generation, idempotency, desired/observed state, participant acknowledgement, safe point, snapshot revision, and classified failure.
+ Session resources currently store browser-local deltas separately from Agent defaults. The submitted Turn payload stores resolved Skill IDs/versions and remains immutable for that Turn.
+ The current topology combines Runtime-configured Agent/Sandbox nodes with browser-selected Session resources. Dynamic worker lifecycle nodes and a server-owned Session resource snapshot remain follow-up work.

## Failure and security

Invalid model/resource inputs fail before side effects. Transitional control failure is never displayed as paused. Conflicts return authoritative generation/state. Secret values are excluded from normal APIs, DOM, state, storage, logs, telemetry, screenshots, and error details. Clipboard copy is a deliberate authorized disclosure and must be audited.

## Compatibility

Old agents keep one default model and their existing non-MPA stop behavior, hide unsupported pause/resume controls, and render verified data only. Native ArkClaw and non-MPA Studio contracts remain unchanged.

## Verification

Contract tests cover state transitions, idempotency, races, model snapshots, submitted mounts, topology, authorization, redaction, and Runtime category filtering. Browser tests cover responsive layout, the single dynamic primary button, model filtering, MPA category selection, Skill Space discovery, and terminal control cleanup. Live Runtime tests prove the model catalog, immutable request model, lifecycle status/control path, configured Agent-to-Sandbox topology, and real Skill Space discovery. Main/worker Skill propagation is covered by targeted contract tests. Full live worker pause/resume, five-minute incremental continuation, refresh recovery, and invalid-resource execution gates remain follow-up verification.
Conversation projection tests additionally cover status/artifact replay, legitimate repeated prose, semantic reasoning/thought separation, nested tool payloads, large sanitized values, specific and unknown tool labels, and searchable model keyboard behavior.

## MPA information rail (implemented 2026-09-18)

- CON-16: The conversation rail is visible only for server-classified MPA Runtimes. AGENTS.md comes from the current Runtime’s authenticated `/api/v1/studio/agent-info` `agentsMd`, with explicit empty, unsupported, denied and failed states. Generic instructions are not a substitute.
- CON-17: Bound skills come from configured Skill Space nodes in the Agent Card and the authorized paginated SkillSpace API in the Runtime region. Temporary Session skill mounting is removed; previously stored temporary selections are not sent to MPA. Refresh/cancellation cannot mix Runtime identities or turn a failed listing into empty success.

Design: [MPA information rail](../../prd-spec/features/mpa-agent-info-rail/2026-09-18-mpa-agent-info-rail.md).

The Runtime proxy handles `GET /web/agent-info/{app}` for a Runtime tagged `veadk:agent-type=mpa`, including native app IDs and `a2a-default`. Its additive `AgentInfo.agentCategory` is `mpa`; generic synthesized A2A responses use `general`. Other existing responses may omit the field, which hides the rail.

`AgentInfo.mpa` contains `agentsMd: string | null`, `agentsMdStatus`, `skillSpacesStatus`, and `skillSpaces: {id: string, region: string}[]`. Status values are `ready`, `unsupported`, `forbidden`, and `error`. A document read has a 10-second network timeout with a 4-second connect timeout; 401/403 are forbidden and 404/405/501 unsupported. Studio calls the new read-only metadata endpoint with a dedicated `X-MPA-Studio-Key` from its server-resolved Runtime key. On 404/405 it can try the legacy `/api/v1/agents` JWT route without that dedicated header; authorization failure there means the Runtime needs an upgrade. No API key is substituted for a JWT. Invalid payloads and transport failures are errors. Only document/name/description/model strings are allowed through from the upstream details response. Space discovery remains independent from document read failures.

Space IDs come from configured `skill-space` nodes connected to an `agent` node by a `mounts` edge in `urn:veadk:mpa:resource-topology:v1`. Missing topology is unsupported, not an empty-success binding. Space listings use the existing authorized `/web/skill-spaces/{id}/skills` route, request 100 items per page, and reject no-progress or over-100-page traversal as incomplete errors. Each request retains the existing 30-second client timeout and supports cancellation. Counts are shown only for complete listings; degraded results and partial failures retain readable items with a warning, while denied access clears prior skills. No changes are made to Runtime credentials, bindings, or deployment. Bound skill names open the permission-aware [Skill document editor](../studio-skill-document/README.md).

## Managed creation boundary

Studio MPA creation and `veadk mpa provision` are owned by [Studio MPA creation](../studio-mpa-creation/README.md). That path prepares account resources and uses real Runtime metadata bootstrap. The existing responsibilities and legacy entry points described here remain unchanged.
