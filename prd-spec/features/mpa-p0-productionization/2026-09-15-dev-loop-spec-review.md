# MPA AgentKit P0 Dev Loop Spec Review

- Change ID: `mpa-p0-productionization`
- Date: 2026-09-15
- Chinese: [2026-09-15-dev-loop-spec-review.zh.md](2026-09-15-dev-loop-spec-review.zh.md)
- Reviewed PRD: [MPA AgentKit P0 Functional Migration](2026-09-15-mpa-p0-productionization-design.md)

## 1. Overall conclusion

- Feasibility: medium-high after remediation; delivery is XL across VeADK, agentkit-mpa-agent, AgentKit OpenTOP/Runtime, and the worker protocol.
- Largest risks: identity and live writes, cross-system idempotency, PostgreSQL concurrency/recovery, and refresh-safe creation operations.
- Direction: deliver M0 and S1 through S5 as serial vertical slices, each independently verified, landed, and reversible; do not force the scope into one PR.
- Gate: every P0/P1 below is reflected in the PRD/contracts. Local M0 contracts gate S1; deployed-only identity/Profile checks remain mandatory before release.

## 2. Findings and remediation

| Original severity | Finding | Remediation | Status |
| --- | --- | --- | --- |
| P0 | First Profile apply simultaneously required `If-Match` and `If-None-Match` | Made preconditions mutually exclusive; added `400/428` and strong ETag | resolved |
| P0 | Async apply/run/continue had no durable idempotency/status model | Added minimal `runtime_operations`; pending Profile never becomes current | resolved |
| P0 | Continuation promised impossible ACID across external A2A TaskStore | Replaced with Runtime transaction, dispatch outbox, idempotent dispatcher | resolved |
| P0 | REST JWT and A2A TIP identity semantics diverged | Defined one `RuntimePrincipal v1`, issuer/JWKS mapping, and migration matrix | resolved; M0 live gate |
| P0 | Earlier design incorrectly depended on Managed Agent CRUD/version | Removed that product from P0; Studio AgentDraft is normalized directly into an MPA Profile and applied to Runtime | resolved by scope decision |
| P0 | Explicit Session upgrade had no API | Added `profile-upgrade` with ETag, idempotency, active-Turn, downgrade, and unapplied-target semantics | resolved |
| P0 | Creation state lived only in browser memory | Added TOS-CAS creation operation and reconcile/retry API | resolved |
| P0 | AgentKit Session and Runtime Session were dual authorities | P0 uses only mpa-agent business Session/Turn; Managed Agent Session is outside the path | resolved |
| P0 | Cloud E2E and PostgreSQL semantics were not executable | Added live environment manifest, PostgreSQL two-connection lane, fault injection, and cross-repo manifest | resolved; execution hard gate |
| P1 | A2A execution version had no wire contract | Defined `urn:veadk:mpa:execution:v1`, metadata/hash, and legacy behavior | resolved |
| P1 | Unknown SSE cursor silently replayed everything | Selected persistent ADK events plus inbox fence; unknown cursor returns `410` | resolved |
| P1 | Plaintext secrets conflicted with reference-only policy | AgentKit mode rejects new plaintext writes and defines conversion/clear/removal window | resolved |
| P1 | Performance targets lacked measurement method | Added warm-up, sample, concurrency, data-size, and timing boundaries | resolved |
| P1 | Page reuse boundary was abstract | Added MPA intent/view-model and prohibited GitHub-version/generic-draft/evaluation reuse | resolved |
| P1 | Runtime gates and cross-repo compatibility were unspecified | Fixed `make test/coverage`, cross-repo manifest, and compatibility matrix | resolved |
| P1 | Runtime-operation scope/status lookup was incomplete | Limited ledger to Profile/run/upgrade/continue, added common operation GET, and kept config/control in their own CAS stores | resolved |
| P1 | Lost first response and update recovery were incomplete | Unified create/update on `202 + operationId`, client idempotency, active listing, reconciliation, and retry | resolved |
| P1 | Session upgrade did not define override recomputation | Target Profile becomes base, override/clear remains, inherit follows new defaults, invalid resources reject atomically | resolved |
| P1 | MPA detail had no implementable data contract | Added `MpaAgentView` and 0/1/N Runtime-binding/orphan semantics | resolved |
| P1 | Runtime A2A capability was confused with Worker protocol | Split compatibility columns and fixed current Worker REST baseline | resolved |
| P1 | Smoke depended on model tool choice | Split into a tool-disabled model probe and direct existing CodexWorkerClient probe | resolved |

## 3. Sixteen-dimension conclusion

Context, scope, terminology, model interpretation, SDD/TDD fitness, minimal implementation, compatibility, existing-data impact, runtime risk, feasibility, extensibility, over-design, minimum change, code boundaries, architecture consistency, and testability were reviewed. Key convergence: no ArkClaw migration; no template/expert/version product; only necessary Runtime persistence; one Session authority; adapters/outbox/reconciliation across external systems rather than distributed-transaction claims.

## 4. Delivery order

1. M0: Profile client contract, principal foundation, PostgreSQL, fault injection, and cross-repo manifest; deployed-only identity/Profile proof moves to S5.
2. S1: creation, durable operation, Profile, deterministic smoke, first chat.
3. S2: Session execution config and explicit version upgrade.
4. S3: run idempotency, outbox, persistent event replay.
5. S4: multi-worker pause/resume/continuation.
6. S5: detail/version, Runtime lifecycle, Debug/Trace, CLI, compatibility closure.

## 5. Gate

The corrected scope review passes with no P0/P1. Local M0 contracts and PostgreSQL foundation are green, so S1 implementation may proceed; deployed-only identity/Profile verification remains a release gate.
