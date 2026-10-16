# Skill observability

[中文版](README.zh.md)

Component: `skill-observability`; status: implemented (local verification; full regression limitations in PRD); revised 2026-10-16.
Change: [skill-observability](../../prd-spec/features/skill-observability/2026-10-16-skill-observability.md).

## Ownership and interfaces

VeADK owns Runtime package acquisition and ADK instruction-load instrumentation in `veadk/skills/` and `veadk/tracing/telemetry/telemetry.py`. `actb-mono/sandboxes/agentkit-skill` owns Python/Go Sandbox installation, tool adaptation and exporter lifecycle. The maintained wire schema below is shared; the sandbox is independently released and does not import an unpublished SDK recorder. Existing tools/signatures/results and metrics remain compatible. Discovery, resource/script execution, issue reporting and business success are not owned here.

## Contracts

- CON-1: `skill_download` is an OTEL counter, unit `count`; dimensions are exactly `skill_source`, `skill_id`, `skill_version`, `skill_space_id`, `outcome`. `outcome` is `success` or `error` (including cancellation). One acquisition completion, including cache restore, adds one. No event for mere discovery or local symlink creation.
- CON-2: `skill_load` is an OTEL counter, unit `count`; dimensions are exactly the four identity fields above. One successful instruction response adds one. ADK invocation-cache hits still count. Errors, cancellation, forwarding and resource/script access do not.
- CON-3: Download Span `skill_download` has `skill.source`, `skill.id`, `skill.version`, `skill.space_id`, `outcome`, `cache_hit`, `consumer`. Failures add `error.type` and a safe static `error.description`, with ERROR status. Successful load annotates the existing tool Span with the four dotted identity fields and `consumer`. Consumer is `runtime` or `skill_sandbox`. Span duration is total acquisition time. Never add consumer/cache/error text to metric labels.
- CON-4: Identity follows the table. Missing version/space is the empty string, never a synthesized cache hash. Remote skills without a trustworthy ID and unclassified local skills are excluded. Registry-owned metadata overrides archive metadata for telemetry identity. SkillHub installation records the slug with the installed package, not just the current desired configuration.

| skill_source | skill_id | skill_version | skill_space_id |
| --- | --- | --- | --- |
| builtin_skill | name | empty | empty |
| skillhub_skill | slug | empty | empty |
| skillhub_skill_space | s-* | sv-* when supplied | sp-* |
| agentkit_skill | s-* | vN | empty |
| agentkit_skill_space | s-* | vN when supplied or present in the legacy package path | ss-* |

Python supports all five rows. The pinned Sandbox Go SDK still rejects `sp-*`; the user approved retaining that limitation. Local SkillHub receipts are shared across Python/Go selection.

- CON-5: Record through the global OTEL provider, independently of Span sampling. Runtime load instrumentation is enabled with existing VeADK tracing hooks. No exporter is installed by the SDK recorder. Sandbox periodic OTLP metrics honor `OTEL_SDK_DISABLED`, `OTEL_METRICS_EXPORTER=none`, standard metric/base endpoint configuration and an existing provider. Trace disabling does not disable metrics. Default local collector uses OTLP/HTTP at port 4318; shutdown is bounded and failures are best effort. Metrics use `OTEL_EXPORTER_OTLP_METRICS_PROTOCOL` (or the base protocol), supporting HTTP/protobuf and grpc; interval defaults to 60000 ms. The short-lived SkillHub installer uses 200 ms exporter timeouts and flushes before exit; empty configuration and built-in disabling skip that initialization. Startup cost is recorded in the PRD.
- CON-6: Acquisition owns its observation until completion. Concurrent invocations do not share mutable observation state. Python `to_thread` cancellation does not stop an already-running acquisition: its actual result may arrive later, but no instruction-load success is recorded for the cancelled waiter. No new persistent state except the installed SkillHub provenance receipt. Existing locks, cache validation, retention and cleanup remain authoritative.
- CON-7: New telemetry excludes raw exceptions, URLs, tokens, file paths, instructions and user content. Export/recording failure must not change tool results or suppress application errors. No new credentials/configuration are required. Missing provider gives normal OTEL no-op behavior.

## Verification and evolution

CON-1/4/6 map to materializer/cache and sandbox package tests. CON-2/3 map to actual ADK tool and sandbox wrapper tests, including repeated loads, bad arguments, errors and cancellation. CON-5/7 map to in-memory OTEL and local collector tests for metrics, spans, redaction, switches, provider reuse and failures. Commands and actual evidence are maintained in the linked PRD. Adding dimensions or changing count semantics requires revisiting that design and both languages. Implementation status does not claim deployment or full-repository acceptance.
