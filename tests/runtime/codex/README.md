# Codex runtime tests

## What runs where

| File | Needs `openai-codex`? | Runs locally by default |
| --- | --- | --- |
| `test_codex_runtime.py` | no | yes |
| `test_codex_shim_rounds.py` | no | yes |
| `test_codex_tracing.py` | no (a stub SDK is installed) | yes |
| `../differential/` | no (a stub SDK is installed) | yes |
| `test_codex_runtime_sdk.py` | **yes** (`pytest.importorskip`) | **no — silently skipped** |
| `test_codex_sdk_protocol.py` | **yes** (`pytest.importorskip`) | **no — silently skipped** |
| `test_codex_runtime_smoke.py` | yes | no — opt in with `CODEX_RUN_SMOKE=1` |
| `test_codex_real_model_probe.py` | yes | no — opt in with `CODEX_RUN_PROBE=1`, spends real tokens |

The last two are the only tests that touch the real SDK types, and they are the
ones a developer machine is most likely to skip without noticing. `openai-codex`
is an optional extra; CI installs it (`uv sync --all-extras` in
`.github/workflows/unit-tests.yaml`), a checkout usually does not. A green local
run therefore does **not** mean the SDK contract holds.

To run them locally:

```bash
uv sync --all-extras     # or: pip install 'openai-codex==0.159.2'
PYTHONPYCACHEPREFIX=/private/tmp/veadk-pycache \
  .venv/bin/python -m pytest tests/runtime/codex/test_codex_sdk_protocol.py -v
```

Confirm they are not skipping:

```bash
.venv/bin/python -m pytest tests/runtime/codex -q -rs   # -rs lists skip reasons
```

## Why the differential suite still runs without the SDK

`veadk/runtime/codex/runtime.py` imports `openai_codex` at module scope, so
`Agent(runtime="codex")` is unimportable without the extra. The differential
harness installs a minimal stub into `sys.modules`
(`tests/runtime/differential/fake_codex_sdk.py::install_openai_codex_stub`) from
a *fixture*, never at import time — pytest finishes collection, and therefore
evaluates every `importorskip("openai_codex")`, before the first test runs, so
the stub cannot turn a legitimate skip into a spurious pass.

The stub only replaces the names the runtime imports. `AsyncCodex` is always
replaced by `ShimDrivingCodex`, which POSTs a real `stream: True`
`/v1/responses` request at the real `ResponsesShim` over `httpx.ASGITransport`
(in-process, no socket, no Codex binary, xdist-safe) and reads its endpoint out
of the `config.toml` that `_prepare_codex_home` generated.

## No network, no ports, no binary

Apart from the two opt-in files above (`test_codex_runtime_smoke.py`,
`test_codex_real_model_probe.py`), nothing in this directory or in
`../differential/` binds a port, spawns the Codex CLI, or reaches the network —
with one exception:
`test_codex_runtime.py::test_tool_executor_supports_stdio_mcp_toolset` spawns a
real Python subprocess from `examples/`. It is bounded by an explicit timeout so
it cannot hang a `pytest -n 16` run.

`test_codex_shim_rounds.py` constructs `ResponsesShim` directly rather than
calling `get_shim`, so the process-global `_SHIMS` cache (and its uvicorn
servers) is never populated; an autouse fixture asserts that. The one test that
must exercise `get_shim` — the cache is what it tests — swaps `_SHIMS`/`_RETIRED`
for empty ones, restores them in a `finally` before that fixture runs, and stubs
`start()` so nothing binds a port.

## Real-model probe (`test_codex_real_model_probe.py`)

A tiny, fixed canary against a **real model**, to run **once per Codex PR
before merge** instead of a large example (`examples/codex_ops_assistant`
spends ~2M tokens a run). It is marked `codex_probe` and skipped unless opted
in; it **must not run in CI** — it spends real tokens and depends on model
behaviour.

Scenario: two turns in one session, `RunConfig(max_llm_calls=15)`. Turn 1 calls
the ADK tool `fetch_latency_samples` (a six-row CSV), then three shell steps —
save `latency.csv`, average p99, max p99. Turn 2 computes the min from the same
file.

What it catches (each one a regression we have hit):

| Failure | How it shows up |
| --- | --- |
| Ark rejects a forwarded request field (e.g. `reasoning.summary`) | a turn errors instead of completing |
| replayed tool history out of order (ADK results at the tail) | `LlmCallsLimitExceededError`, or a command issued more than twice |
| model copies Codex's shell wrapper (`/bin/zsh -lc '/bin/zsh -lc ...'`) | a recorded command still starts with `<path>/sh\|bash\|zsh -c\|-lc` |
| ADK tool executed more than once | fetch counter is not exactly 1 |
| multi-turn context lost | turn 2 does not report min 120 |
| cost regression | summed token usage over `CODEX_PROBE_MAX_TOKENS` |

Answers must contain average 322.83 (or 322.8), max 980 and min 120.

Cost: ~75K tokens total (one run with `deepseek-v4-flash` used ~52K + ~23K,
about 40 s of model time). Token usage is read from the `usage_metadata` the
runtime attaches once per invocation (the Codex thread's cumulative total,
which already includes the shim's ADK-tool rounds). The cap defaults to
150000; override with `CODEX_PROBE_MAX_TOKENS`.

Run it (sequentially, never under `pytest -n`):

```bash
export CODEX_RUN_PROBE=1
export MODEL_AGENT_API_KEY=...       # Ark API key
export MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
export MODEL_AGENT_NAME=...          # model/endpoint id
PYTHONPYCACHEPREFIX=/private/tmp/veadk-pycache \
  .venv/bin/python -m pytest tests/runtime/codex/test_codex_real_model_probe.py \
  -p no:xdist -s -rs
```

`-s` prints each turn's commands, final answer and token count, which is the
first thing to read when it fails. Without the env vars (or without the
`openai-codex` extra) it is skipped with a message naming what to set.
