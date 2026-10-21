# Skill observability

[中文版](README.zh.md)

Component: `skill-observability`; status: implemented (local verification; full regression limitations in PRD); revised 2026-10-21.
Change: [skill-observability](../../prd-spec/features/skill-observability/2026-10-16-skill-observability.md).

## Ownership and interfaces

VeADK owns Runtime package acquisition and ADK instruction-load instrumentation in `veadk/skills/` and `veadk/tracing/telemetry/telemetry.py`. `actb-mono/sandboxes/agentkit-skill` owns Python/Go Sandbox installation, tool adaptation and exporter lifecycle. The maintained wire schema below is shared; the sandbox is independently released and does not import an unpublished SDK recorder. Existing tools/signatures/results remain compatible. Skill metrics use the new names and unit below; consumers must update queries. Old metric names are not emitted in parallel. Discovery, resource/script execution, issue reporting and business success are not owned here.

## Contracts

- CON-1: `gen_ai_skill_download_count` is an OTEL counter, unit `time`; dimensions are exactly `skill_source`, `skill_id`, `skill_name`, `skill_version`, `skill_space_id`. One acquisition completion, including cache restore and failure, adds one. No event for mere discovery or local symlink creation; outcome is recorded only on the Span.
- CON-2: `gen_ai_skill_load_count` is an OTEL counter, unit `time`; dimensions are exactly the five identity fields above. One successful instruction response adds one. ADK invocation-cache hits still count. Errors, cancellation, forwarding and resource/script access do not.
- CON-3: Download Span `download_skill {skill_name}` has `skill.source`, `skill.id`, `skill.name`, `skill.version`, `skill.space_id`, `skill.consumer`, `skill.download.outcome`, `skill.download.cache_hit`. Outcome is `success` or `error` (including cancellation); failures add `error.type` and a safe static `error.description`, with ERROR status. Successful loading renames the existing tool Span to `load_skill {skill_name}` and adds the five dotted identity fields and `skill.consumer`, without creating a duplicate Span. `skill.consumer` is `runtime` or `skill_sandbox`. Span duration covers the actual operation. Consumer/cache/outcome/error text never becomes a metric label.
- CON-4: Identity follows the table. Missing version/space is the empty string, never a synthesized cache hash. Remote skills without a trustworthy ID and unclassified local skills are excluded. Registry-owned metadata overrides archive metadata for telemetry identity. SkillHub installation records the slug with the installed package, not just the current desired configuration.

`skill_name` uses the name resolved by the current source: metadata for Runtime/skill spaces, the loaded name for local skills, and the resolved installation name for SkillHub installation. Explicit TOS acquisition first propagates the version API `Name`; when absent, successful acquisition or cache restoration reads the validated package name. Failure before a name is available uses the empty string, never an ID, slug or path as a substitute. Reading a name for telemetry must not change the acquisition result.

| skill_source | skill_id | skill_name | skill_version | skill_space_id |
| --- | --- | --- | --- | --- |
| builtin_skill | name | name | empty | empty |
| skillhub_skill | slug | resolved name or empty | empty | empty |
| skillhub_skill_space | s-* | resolved name or empty | sv-* when supplied | sp-* |
| agentkit_skill | s-* | resolved name or empty | vN | empty |
| agentkit_skill_space | s-* | resolved name or empty | vN when supplied or present in the legacy package path | ss-* |

Python supports all five rows. The pinned Sandbox Go SDK still rejects `sp-*`; the user approved retaining that limitation. Local SkillHub receipts are shared across Python/Go selection.

- CON-5: Record through the global OTEL provider, independently of Span sampling. Runtime load instrumentation is enabled with existing VeADK tracing hooks. No exporter is installed by the SDK recorder. Sandbox periodic OTLP metrics honor `OTEL_SDK_DISABLED`, `OTEL_METRICS_EXPORTER=none`, standard metric/base endpoint configuration and an existing provider. Trace disabling does not disable metrics. Default local collector uses OTLP/HTTP at port 4318; shutdown is bounded and failures are best effort. Metrics use `OTEL_EXPORTER_OTLP_METRICS_PROTOCOL` (or the base protocol), supporting HTTP/protobuf and grpc; interval defaults to 60000 ms. The short-lived SkillHub installer uses 200 ms exporter timeouts and flushes before exit; empty configuration and built-in disabling skip that initialization. Startup cost is recorded in the PRD.
- CON-6: Acquisition owns its observation until completion. Concurrent invocations do not share mutable observation state. Python `to_thread` cancellation does not stop an already-running acquisition: its actual result may arrive later, but no instruction-load success is recorded for the cancelled waiter. No new persistent state except the installed SkillHub provenance receipt. Existing locks, cache validation, retention and cleanup remain authoritative.
- CON-7: New telemetry excludes raw exceptions, URLs, tokens, file paths, instructions and user content. Export/recording failure must not change tool results or suppress application errors. No new credentials/configuration are required. Missing provider gives normal OTEL no-op behavior.

## Verification and evolution

CON-1/4/6 map to materializer/cache and sandbox package tests. CON-2/3 map to actual ADK tool and sandbox wrapper tests, including repeated loads, bad arguments, errors and cancellation. CON-5/7 map to in-memory OTEL and local collector tests for metrics, spans, redaction, switches, provider reuse and failures. Commands and actual evidence are maintained in the linked PRD. Adding dimensions or changing count semantics requires revisiting that design and both languages. Implementation status does not claim deployment or full-repository acceptance.
