# veADK Runner Plugins Example

This example shows the smallest local veADK integration: build a regular
`Agent`, attach Harness plugins to `Runner`, and keep the agent code focused on
business behavior.

```python
from agent import build_runner

runner = build_runner()
```

The plugin bundle adds context engineering, tool-result compression, and answer
verification without changing the agent class.
