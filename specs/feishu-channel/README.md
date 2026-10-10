# Feishu Channel Streaming

[中文版](README.zh.md)

Component: `feishu-channel`. Revised: 2026-10-10. Status: implemented, locally verified.
Change: [non-UI migration PRD](../../prd-spec/features/managed-agents-upstream/2026-10-10-non-ui-migration.md), `FR-5` / `AC-3`.

## Scope
Port non-UI Feishu channel improvements onto official VeADK while preserving upstream graceful shutdown and app-loop task tracking.
The extension owns presentation of Runner events and channel lifecycle. Runner owns execution; the Lark SDK owns message/card delivery. No Studio UI or backend wiring is included.

## Contract
- `CON-FEISHU-1`: Default replies remain answer-only. Thinking, tool inputs, and tool results are opt-in constructor/environment options. Provider thought text is whitespace-normalized before display; hidden model reasoning is unavailable.
- `CON-FEISHU-2`: Separate thinking and per-call tool cards can reply in an existing or newly requested topic. Existing call IDs correlate out-of-order results; a result without a known call gets a standalone card. Missing stages produce no content cards.
- `CON-FEISHU-3`: Repeated completed provider events do not duplicate thinking or accumulated answer text. Tool records are deduplicated by nonempty call/result ID; events without IDs cannot provide the same correlation guarantee.
- `CON-FEISHU-4`: Displayed structured tool fields are recursively redacted by sensitive field names, bounded in length, and Markdown-fence escaped. Serialization fallback must use the redacted copy. Redaction does not inspect secrets embedded in arbitrary strings.
- `CON-FEISHU-5`: Streaming tasks settle on successful completion and on failures. Card errors propagate unless a Runner error/cancellation is already propagating; cleanup preserves that original failure. Upstream shutdown closes the socket then drains accepted messages on the application loop, cancelling unfinished messages after its timeout.

## Interface and configuration

Public entry point: `veadk.extensions.FeishuChannelExtension(runner=..., streaming=True, show_tool_calls=True)`. Streaming controls affect `channel.stream` only; ordinary handlers and non-streaming Runner replies retain their text formatter.

| Constructor option | Environment variable | Default |
| --- | --- | --- |
| `show_thinking` | `TOOL_FEISHU_CHANNEL_SHOW_THINKING` | `False` |
| `show_tool_calls` | `TOOL_FEISHU_CHANNEL_SHOW_TOOL_CALLS` | `False` |
| `show_tool_results` | `TOOL_FEISHU_CHANNEL_SHOW_TOOL_RESULTS` | `False` |
| `separate_tool_call_cards` | `TOOL_FEISHU_CHANNEL_SEPARATE_TOOL_CALL_CARDS` | `False` |
| `separate_thinking_card` | `TOOL_FEISHU_CHANNEL_SEPARATE_THINKING_CARD` | `False` |
| `create_topic` | `TOOL_FEISHU_CHANNEL_CREATE_TOPIC` | `False` |
| `tool_detail_max_length` | none | `4000`, minimum `100` |

Boolean options combine constructor true with environment values `1`, `true`, `yes`, `on` (case insensitive); explicit false does not override an enabled environment variable. Topic creation requires `reply_in_thread=True` and an inbound message ID, and sends `reply_to` plus `reply_in_thread=True` to Lark. Existing topic IDs also enable threaded replies. No payload or credentials are persisted by the formatter.

## Compatibility and failures

Preserve upstream lifecycle, identity mapping, parent/history retrieval, reconnect behavior, and dependency fallbacks. Tool failure icons recognize a truthy `error`, statuses `error`/`failed`/`failure`, and nonzero `exit_code`; they do not change execution status. Sensitive markers are `api_key`, `apikey`, `access_key`, `authorization`, `cookie`, `credential`, `password`, `secret`, `token` after lowercase and hyphen-to-underscore normalization. Card delivery is not guaranteed by a local test. Shutdown's default timeout remains the upstream `TOOL_FEISHU_CHANNEL_DRAIN_TIMEOUT` value, 300 seconds.

## Verification
Run existing Feishu extension tests plus source regressions for ordered stream sections, deduplication, separate cards, failed results, topic options, and redacted bounded payloads. Live Feishu delivery requires credentials and is outside local validation.

Command: `.venv/bin/python -m pytest tests/test_feishu_channel_extension.py -q`.
`CON-FEISHU-1..3` map to detailed streaming, separate-card, topic, and missing-stage tests; `CON-FEISHU-4` maps to truncation and serialization-fallback tests; `CON-FEISHU-5` maps to graceful shutdown, Runner-failure settlement, and card-cleanup failure propagation tests.

## Change record

2026-10-10: Ported source channel controls onto official `171d8d86`, preserving its lifecycle changes; fixed redaction fallback and background-card cleanup error propagation. Existing upstream baseline: 8 tests passed. Source regressions fail before the new helper is installed, then pass after migration. Added negative-path regressions expose both formatter fallback leakage and swallowed card errors before their fixes. Local validation is recorded by the parent migration PRD; live delivery is not_run.
