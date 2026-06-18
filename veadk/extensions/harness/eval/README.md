# Deterministic Harness Eval

The SDK includes small synthetic evals that run without a model. They prove the
core mechanics before live-model A/B testing:

| Scenario | Baseline | Enhanced | Good Direction |
| --- | ---: | ---: | --- |
| Large historical tool result | original context chars | compressed context chars | lower enhanced chars while preserving latest feedback |
| Unsupported completion claim | accepts unverified final claim | verifier marks it failed | false accept decreases |

Run:

```bash
python - <<'PY'
from veadk.extensions.harness.eval import run_deterministic_eval

for row in run_deterministic_eval():
    print(row.model_dump())
PY
```

Live-model latency/token A/B evaluation should reuse the same scenario-first
table shape with real usage metadata from the target runtime.
