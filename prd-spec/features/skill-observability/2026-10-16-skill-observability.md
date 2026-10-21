# Skill download and instruction-load observability

[中文版](2026-10-16-skill-observability.zh.md)

- Change ID: `skill-observability`; created/revised: 2026-10-16; status: implemented; affected checks passed, full regression has existing/environment failures.
- Contract: [skill-observability](../../../specs/skill-observability/README.md).
- Source: AgentKit Skills runtime observability design, revision 2102 (2026-10-16).
- Scope approval: the user approved the proposed Runtime/Python-tool scope and explicitly included `actb-mono/sandboxes/agentkit-skill`. Implementation is local; no commit, publication or cloud operations are authorized.

## Evidence, goals and boundaries

`VeSkillRegistry.get_skill` materializes packages but drops remote identity on conversion to ADK Skill. ADK 2.7.1 caches fetched skills per invocation, so registry calls cannot count instruction loads. `SkillsTool` has a latency histogram but no counters from the design. Sandbox Python pins VeADK 1.1.14 / ADK 1.34.0; Go has its own package store and tool wrapper. Both sandbox telemetry setups currently configure traces, not metric export.

Count package acquisition and successful instruction delivery with the exact source identities and schema in the linked contract. Preserve SDK signatures, cache/install policy, existing metrics, tool results, cancellation and cleanup. Do not count discovery, resource reads, scripts, A2A forwarding, or task success as instruction loading. Do not implement issue reporting, dashboards, new dependencies or dependency upgrades. Changes to AIO protocols, daemon lifecycle and isolation are outside this change.

## Requirements and scenarios

- FR-1: A recognized remote package acquisition emits one `gen_ai_skill_download_count` observation on completion, including validated disk-cache restoration and failure. Invalid cache followed by download is one attempt, with `skill.download.cache_hit=false`.
- FR-2: A successful instruction response emits one `gen_ai_skill_load_count`. Two successful `load_skill` calls in one invocation count twice even when ADK fetches once. Unknown skills, read failures and cancellation never count as successful loads.
- FR-3: Cloud identity survives conversion/cache. Sandbox Python distinguishes built-ins, SkillHub slugs, explicit AgentKit IDs and both space kinds. Go retains its existing four-source support. Unattributable local skills are not guessed to be built-ins.
- FR-4: Use existing process-global OTEL providers; sandbox installs a periodic OTLP metric exporter only when no provider exists. Trace and metric disable switches are independent. Export failures do not affect conversations; shutdown flush is bounded.
- FR-5: New telemetry never records archive URLs, credentials, instruction bodies, paths or raw exception messages. Existing content telemetry policy remains unchanged.
- FR-6: Python and Go use the same labels and source semantics for supported sources; prefetch produces downloads only. Existing installed packages/session links are retained.

The current schema follows technical document revision 2419, read on 2026-10-21, plus the subsequent user-requested unit change to `time`: both counters use the `_count` suffix and unit `time`, with `skill_name` added to identity. Outcome is only `skill.download.outcome`, no longer a metric label. Spans are named `download_skill {skill_name}` / `load_skill {skill_name}` and use `skill.consumer` and `skill.download.cache_hit`. Name provenance and empty-value rules are in the component contract. Preserve fixed Counter instruments; fields and record methods do not need a `gen_ai` prefix.

## Design and affected consumers

Runtime: add a small `veadk/skills/telemetry.py` recorder, instrument the existing materializer, preserve cloud identity under reserved ADK frontmatter metadata, and extend the existing VeADK tool tracing callback for successful native ADK `LoadSkillTool` responses. No replacement toolset or new global cache. Runtime load telemetry follows the existing VeADK tracing-hook activation; metrics are recorded independently of span sampling once the hook is installed.

Sandbox: implement a local recorder using already-installed OTEL packages, because the sandbox's released SDK must work independently of unpublished VeADK changes. Instrument `playground_skills/packages.py`, SkillHub reconciliation, and the existing `ObservedSkillsTool`. Persist the installed SkillHub slug alongside its package so a failed replacement cannot relabel an older built-in. The Go package store records downloads; catalog metadata carries identity into the existing tracked tool wrapper. Built-ins produce no download events. Configure metric export in existing telemetry setup and flush with existing shutdown handling.

Counters count acquisition attempts after identity resolution. Metadata-list failures without a resolved skill ID cannot produce a per-skill download. Successful acquisition means a validated usable package, not just HTTP success. Python worker-thread downloads may finish after awaiting-task cancellation; count their actual acquisition result, never a cancelled load. Go context cancellation is an error outcome. Metrics contain only contract dimensions; `skill.consumer`, `skill.download.cache_hit` and errors are span attributes. Span duration covers acquisition, including validation/installation. Cache hit rates derived from spans are subject to trace sampling.

## Tasks, tests and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1, FR-3 | T-1: Runtime materializer, registry and recorder | AC-1: exact identity/counts for network, cache, invalid package and unknown source | `uv run --extra dev pytest tests/skills/` |
| FR-2, FR-5 | T-2: native ADK load hook and regression tests | AC-2: repeated cached loads count; failure/resource/script calls do not; no secrets | `uv run --extra dev pytest tests/test_portal_metrics.py tests/test_tracing_content.py tests/skills/` |
| FR-1, FR-2, FR-3, FR-6 | T-3: Sandbox Python packages, reconciliation and tool adapter | AC-3: all five sources, install failure/cache, preserved slug, no duplicate load | Sandbox Python targeted/full tests with isolated state |
| FR-1, FR-2, FR-3, FR-6 | T-4: Sandbox Go packages, catalog and tracked tool | AC-4: matching Go counts and cancellation/cleanup | `go run ./cmd/skill-go test ./...` in sandbox `go/` |
| FR-4, FR-5 | T-5: sandbox OTLP metrics and exporter tests | AC-5: local HTTP collector receives counters; switches/provider reuse/shutdown work | Python local collector tests; Go metric exporter tests |
| All | T-6: reconcile bilingual docs, examples and verification | AC-6: paired contracts and actual check evidence | SDK regression; sandbox `make verify`; `git diff --check` |

SDK final regression: `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` (two workers). No real cloud/provider tests. Before any later authorized commit, synchronize intended base and run repository pre-commit gates. Frontend/browser gates are not applicable: no Studio code or API changes.

## Review, risks and delivery record

Direct design review (review-spec unavailable), 2026-10-16: checked source ownership, cache/load separation, metric-label parity, API compatibility, error redaction, cancellation, provider ownership and bilingual equivalence. Resolved double counting by keeping Runtime forwarding uninstrumented and Sandbox counters in its adapter; resolved unpublished dependency coupling with independent sandbox instrumentation. The user confirmed sandbox business-code scope after source-access clarification. The user also explicitly approved keeping Go without `sp-*` support: this change adds observations only, with no SDK upgrade or source-support expansion. No AIO protocol claim is made.

Risks: native ADK response metadata is a version-sensitive integration covered by real installed ADK tests; inventory joins are still required for never-used skills. New sandbox exporters add periodic background work, not synchronous network calls during tool execution. Existing span sampling limits trace-derived cache statistics. Tested bases: VeADK `d55fe8fa`; ACTB `7354ed5`. Execution date: 2026-10-16.


### Implementation review

T-1 through T-6 are implemented. The actual ADK load response retains registry-owned identity across invocation-cache hits. Sandbox records installation independently of instruction delivery; Go reads the same installed SkillHub provenance receipt as Python. Archives cannot override the installer-written receipt. Source resolution failures do not invent labels. Existing public signatures, install/rollback rules and tool results remain unchanged. Go metric imports promote already-locked indirect modules to direct dependencies; versions and `go.sum` are unchanged.

Direct implementation review checked cancellation, failed installations, cache reuse, failed provider recording, successful-instruction boundaries, source parity, endpoint configuration and provider ownership. Regression tests failed before implementation (missing recorder functions), and the implementation-switch provenance test reproduced a built-in misclassification before the fix. No blocking finding remains in the affected scope. No deployment/readiness claim is made.

Startup tradeoff: SkillHub reconciliation is a short-lived process, so its observations must flush before exit. Only actual SkillHub configuration initializes this exporter; empty configuration and built-in disabling add no telemetry initialization. Startup exporters have 200 ms timeouts; regular Python metric export uses 3 s, and Go shutdown shares a 5 s context. A local slow-collector experiment measured 575 ms import/setup plus 533 ms shutdown with both signals timing out. These are local samples, not image startup guarantees; this overhead applies only to the Python startup installer, not each tool call. The local collector tests also verify metric delivery and provider reuse from that startup setup.

### Verification record (2026-10-16)

Tested scope is the uncommitted diff over VeADK `d55fe8fa` and ACTB `7354ed5`. SDK uses Python 3.12.15 / ADK 2.7.1; Sandbox uses its own Python environment / ADK 1.34.0 and the existing pinned Go SDK.

| Check | Status | Actual result |
| --- | --- | --- |
| `uv run --extra dev pytest tests/skills tests/test_portal_metrics.py tests/test_tracing_content.py -q` | pass | 120 tests; actual ADK repeated loads, cache/error/cancellation, identity, redaction and fail-open recorder coverage. |
| `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | fail | 6971 passed, 16 failed, 59 skipped, 4 xfailed, 2 collection errors. Failures require unavailable optional `llama_index`, `openai_codex` and `anthropic` packages; unrelated dependency installation was not folded into this feature. Two workers were used. |
| Sandbox targeted Python: `TMPDIR=/private/tmp PYTHONPATH=src MODEL_AGENT_API_KEY=local-test-placeholder OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none .venv/bin/python -m pytest tests/test_skill_observability.py tests/test_skill_reconciler.py tests/test_playground_skills.py tests/test_sandbox_agent.py tests/test_a2a_telemetry.py -q` | pass | 42 tests, 7 subtests. Collector tests launch clean child processes with metrics explicitly enabled. |
| Sandbox full Python: same environment, `.venv/bin/python -m pytest tests -q` | fail | 182 passed, 9 failed, 20 skipped, 13 subtests. All nine remaining cleanup/migration-contract failures reproduce against copied, tracked source from ACTB `7354ed5`; no new observability test fails. |
| `TMPDIR=/private/tmp go run ./cmd/skill-go test ./...` (Sandbox `go/`) | pass | All Go packages; canonical macOS temporary directory avoids pre-existing path-alias cleanup assertions. |
| `TMPDIR=/private/tmp go run ./cmd/skill-go test -race -run 'TestSkill|TestInstalledSkillHub' .` | pass | Affected Go acquisition/load/provenance and exporter tests, with race detection. |
| `make verify PYTHON=/Users/bytedance/actb-mono/sandboxes/agentkit-skill/.venv/bin/python` | pass | 28 root smoke tests, shell syntax and diff checks; does not establish container readiness. |
| Ruff 0.11.12 on changed Python files | pass | Used isolated `uvx --from ruff==0.11.12 ruff check <changed-files>`; the repository environment has no Ruff executable. |
| Bilingual pairs, schema identifiers, relative links and `git diff --check` | pass | PRD/spec pairs synchronized; Sandbox README and Unreleased changelog updated. |
| Real cloud/image readiness, deployed collector and grpc transport | not_run | No cloud/image operation authorized; local collector delivery uses HTTP/protobuf. |
| Repository pre-commit and remote synchronization | not_run | No commit requested; these remain mandatory before a later authorized commit. |
| Studio/browser gates | not_applicable | No frontend/backend Studio contract changed. |

Initial Sandbox full collection required a dummy model API value; the final command uses a placeholder, disables external exporters and supplies `PYTHONPATH=src` for child processes. Tests that create an in-memory SDK provider explicitly remove `OTEL_SDK_DISABLED` locally. No real credentials, real model requests or machine-global configuration were used. The user approved recording these environment/tooling limitations here. Temporary baseline copies are removed after comparison. Affected checks establish local implementation behavior; full-repository acceptance is not green.
