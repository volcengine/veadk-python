# Studio Tool extensions

This directory contains first-party tools executed by the Studio BFF. Every public
Python module is imported at Studio startup in filename order and must export:

```python
def register_tools(registry):
    registry.register(...)
```

Use `current_time.py` as the minimal working example. For a new tool:

1. Add one public `.py` module in this directory. Files beginning with `_` are ignored.
2. Use a globally unique tool name; built-in and extension tools share one registry.
3. Update `executor_revision` whenever behavior or the input contract changes.
4. Keep credentials and trusted identity out of the manifest and model arguments.
5. Lazily load optional dependencies inside the executor when practical.
6. Add tests for registration, schema validation, execution, and safe failures.

Restart Studio after changing an extension. No configuration or Runtime deployment is
required.
