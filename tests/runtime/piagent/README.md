# PiAgent runtime tests

## Unit tests

These tests use a fake local `pi` RPC process and do not call a real model:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/veadk-pycache \
  .venv/bin/python -m pytest tests/runtime/piagent/test_piagent_runtime.py
```

## Real local smoke test

The native-history smoke runs a real Pi binary against a loopback model stub.
It verifies that pending tools resume through native assistant/tool-result
messages and that a new user request can call the same tool with the same
arguments again. It needs no model credentials:

```bash
PIAGENT_RUN_SMOKE=1 \
  .venv/bin/python -m pytest \
  tests/runtime/piagent/test_piagent_runtime_smoke.py::test_real_piagent_resumes_native_tool_results \
  -p no:xdist -rs
```

The greeting smoke below calls a real model. Both smoke tests are skipped
unless `PIAGENT_RUN_SMOKE=1` is set; the greeting also requires credentials.

```bash
export PIAGENT_BINARY=/private/tmp/veadk-piagent-binary/v0.80.6-darwin/extracted/pi/pi
export PIAGENT_AGENT_DIR=/private/tmp/veadk-piagent-test-home
export MODEL_AGENT_API_KEY=<your-model-key>
export PIAGENT_SMOKE_MODEL=<your-model-name>
export PIAGENT_SMOKE_API_BASE=https://ark.cn-beijing.volces.com/api/v3/
export PIAGENT_RUN_SMOKE=1

PYTHONPYCACHEPREFIX=/private/tmp/veadk-pycache \
  .venv/bin/python -m pytest tests/runtime/piagent/test_piagent_runtime_smoke.py -s
```

If `PIAGENT_BINARY` is unset, the runtime uses the managed Pi distribution at
`PIAGENT_INSTALL_DIR/pi/pi` (default `~/.cache/veadk/piagent/pi/pi`) and
downloads the Pi archive there when it is missing. If you set
`PIAGENT_BINARY`, point it at the `pi` executable inside a fully extracted Pi
release directory so the adjacent resources such as `theme/` are available.

After running, inspect the generated Pi custom model config:

```bash
cat /private/tmp/veadk-piagent-test-home/models.json
```
