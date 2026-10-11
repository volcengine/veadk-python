# Studio trace pagination

## Evidence and approved scope
The user authorized fixing and redeploying local Studio only. Runtime already exports session-tagged HTTP and business roots. Studio discards candidate roots, expands only 200 child spans, and misses roots in its bounded broad scan.

## Design and requirements
Use exact mpa.session.id then gen_ai.session.id lookup before existing compatibility fallbacks. Validate session/runtime/invocation tags, prefer mpa.agent.turn, select the nearest trace, retain the located root, and page children by trace ID. Deduplicate span IDs and exclude foreign trace rows. Limit expansion to 50 pages; fail explicitly instead of claiming a complete truncated trace. Preserve permission errors and retries. No MPA, API signature, credentials, or file-download behavior changes.

## Review and acceptance
Self-review: existing endpoint and authorization contracts are unchanged; no component contract change. User approval: “改下前端然后重新部署一下 mpa不要改”. Regression tests cover 201 spans, root retention, duplicate roots, foreign Runtime/trace exclusion, tag aliases, invocation filtering and the page limit. Verify the affected live session through the local endpoint after restart. Source changes are confined to the Studio service and tests; no browser asset rebuild is required.

## Verification (2026-09-17)
Pass: 16 targeted Python tests; incremental executable-line coverage 24/24 (100%); repository pre-commit including Ruff check/format and secrets scan; live local endpoint HTTP 200 with 778 spans; browser flame graph displays mpa.agent.turn and matching session ID. Browser assets unchanged, frontend build not applicable. Pyright reports the pre-existing SDK Configuration.host assignment typing error; not introduced by this diff. Runtime image unchanged.
