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

The last two are the only tests that touch the real SDK types, and they are the
ones a developer machine is most likely to skip without noticing. `openai-codex`
is an optional extra; CI installs it (`uv sync --all-extras` in
`.github/workflows/unit-tests.yaml`), a checkout usually does not. A green local
run therefore does **not** mean the SDK contract holds.

To run them locally:

```bash
uv sync --all-extras     # or: pip install 'openai-codex==0.1.0b3'
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

Nothing in this directory or in `../differential/` binds a port, spawns the
Codex CLI, or reaches the network — with one exception:
`test_codex_runtime.py::test_tool_executor_supports_stdio_mcp_toolset` spawns a
real Python subprocess from `examples/`. It is bounded by an explicit timeout so
it cannot hang a `pytest -n 16` run.

`test_codex_shim_rounds.py` constructs `ResponsesShim` directly rather than
calling `get_shim`, so the process-global `_SHIMS` cache (and its uvicorn
servers) is never populated; an autouse fixture asserts that.
