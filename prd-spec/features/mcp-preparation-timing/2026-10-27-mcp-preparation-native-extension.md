# Preparation timing for Agent-owned native MCP toolsets

[中文版](2026-10-27-mcp-preparation-native-extension.zh.md)

Change ID: `mcp-preparation-native-extension`; date: 2026-10-27; status: approved within the active phase-1 implementation authority, not released. Predecessor: [Trusted preparation timing](2026-10-27-mcp-preparation-timing.md). Contract: [MCP session dispatch](../../../specs/mcp-session-dispatch/README.md).

## Evidence and intended outcome

V25 accepted Trusted preparation/acquisition spans in APMPlus. Bundled mcp_router, lark, las, vod and supabase toolsets instantiate native ADK McpToolset instead. VeIdentity uses another toolset with a native manager. The earlier wrapper therefore does not cover these Agent-owned paths.

## Requirements, design and boundaries

- `FR-1`: Instrument known native and VeIdentity toolsets when assembled by VeADK Agent. Trusted toolsets retain their existing instrumentation without duplicate spans. Unknown tools and native ADK classes outside VeADK-owned instances are unchanged.
- `FR-2`: A dedicated adapter binds wrappers to existing toolset/manager instances. Preserve their constructors, callback fields, credentials, locks, caches, lifetime, filtering, retry and cancellation. Do not replace managers or globally monkeypatch third-party classes.
- `FR-3`: Reuse fixed-metadata preparation_span for get_tools and create_session. Preserve arguments, return identity, original exception identity, caller context, and exactly-once native delegation. Never capture auth/header/URL/content/error messages in added telemetry.
- `FR-4`: Installation is idempotent. Copied bound methods must bind to the copied owner: capture unbound functions, never an original bound owner. Shared instances across Agents must not be double-wrapped. Unknown nonstandard methods are left unchanged.
- `FR-5`: Add only a small Agent integration call; keep adapter logic in a new module. Existing tool execution propagation, dynamic identity credentials, provider/exporter configuration, cloud resources and dependencies are outside this extension. Offline identity fixtures do not prove real provider authorization.

## Tasks and acceptance

`T-1` / `AC-1`: Write failing native/identity preparation tests before code; cover instance identity, separate managers, arguments, exact errors/cancellation, concurrency, idempotence, deepcopy binding, Trusted no-duplication, unknown tools and actual Agent assembly.

`T-2` / `AC-2`: Implement the adapter and Agent hook, preserving existing retry/cache/auth callbacks. Run related MCP, identity and Agent regressions plus required full regression/pre-commit. Extend maintained bilingual contract and user MDX.

`T-3` / `AC-3`: Validate an actual native HTTP toolset with the existing isolated fixture and APMPlus lookup under the existing image-only authority; unchanged dependencies/29 fields. Real identity credential acceptance requires an authorized configured provider and remains separately reported. No new endpoint, role or credential authority is inferred.

## Review and authority

Direct review replaces unavailable review-spec. The user explicitly requested all feasible phase-1 implementations and verification and continued autonomous exploration; that existing authority covers this missing collection path. No new human review or deployment permission is claimed. Reviewed risks: manager replacement would lose callbacks; class patching would affect unrelated consumers; bound-owner closures would break deepcopy; duplicate wrappers would miscount. The selected instance adapter addresses these risks. Requirements and both language versions were checked before production/test edits.

## Verification record

- `pass`: no-op adapter reproduced six missing-observation failures and three unchanged-behavior passes before implementation.
- `pass`: 130 related MCP/identity/Agent/generated-client regressions; native and Trusted cache/retry tests both pass. An additional ten-test adapter run covers request-header provider and sampling/elicitation callback identity as well as the original scenarios.
- `pass`: local real HTTP fixture and archive checks: 12 passed, covering Trusted and native preparation, three acquisitions, two calls, parent restoration and close. This does not prove native cloud deployment or APMPlus ingestion.
- `pass`: all-files pre-commit after formatting; documentation production build.
- `fail`: standalone documentation types:check generates an empty `.source/server.ts` and reports TS2306. The same command with both MDX pages restored to unchanged HEAD reproduces the identical failure; working edits were restored in finally. The earlier Trusted record's type pass does not establish a repeatable fresh type gate.
- `pass`: full Python regression: 7,958 passed, 50 skipped, 4 xfailed, 88 warnings in 512.83 seconds; Python diff fingerprint remained unchanged. Full Agent automatic-hook cloud deployment and real VeIdentity authorization remain outside the synthetic fixture's evidence.
- `pass`: existing isolated Runtime V26 native HTTP fixture and APMPlus lookup: one preparation, three acquisitions and two successful inner tools, exact Trace/parent ancestry, closed sessions, unchanged 29 fields and dependency versions matching V25. The cloud fixture calls the same instance adapter directly; the automatic Agent assembly hook is verified offline, not as a full cloud Agent deployment. Real VeIdentity provider authorization and request-meta propagation remain separate scope.
