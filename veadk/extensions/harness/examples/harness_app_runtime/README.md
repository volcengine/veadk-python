# HarnessApp Runtime Example

When deploying a veADK HarnessApp runtime, enable Harness plugins through the
runtime configuration:

```yaml
harness_enhance:
  enabled: true
  components: [invocation_context, compactor, response_verification]
  profile: general
  compression_provider: builtin
```

The runtime reads this configuration as environment variables and attaches the
plugin bundle to the veADK Runner.

## Local Latency And Context Benchmark

Run the local HarnessApp benchmark from the repository root:

```bash
PYTHONPATH=. python \
  veadk/extensions/harness/examples/harness_app_runtime/stable_latency_token_case.py \
  --repeats 3
```

If your local environment needs model or runtime variables, pass an env file:

```bash
PYTHONPATH=. python \
  veadk/extensions/harness/examples/harness_app_runtime/stable_latency_token_case.py \
  --env-file /path/to/.env \
  --repeats 3
```

The script starts a local HarnessApp Runtime, invokes it through
`veadk agentkit invoke`, and compares:

- no enhancement headers
- `--enable-harness-enhance` with built-in compression

It prints a JSON report with latency, prompt-context size, compression impact,
and answer consistency.
