# intent_and_sql_tools

Minimal Brain + Hands + Registry Data Agent SDK scaffold for VeADK/Google ADK.

## Quick Start

```bash
python train.py all
python app.py
```

## Structure

- sdk/core_engine.py: IntentVanna and SQLVanna
- sdk/registry.py: intent to tool routing map
- sdk/compiler.py: compile IntentEnvelope into rich prompt
- sdk/tools/: gateway and worker tools
- train.py: offline training pipeline
- app.py: runtime entry
