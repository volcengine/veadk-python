# Generated AgentKit project

This example shows the output of VeADK Studio for a root customer-support Agent
with one order assistant. Business logic lives under `agents/`; `app.py` only
connects the Agent to VeADK's shared AgentKit application component.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set MODEL_AGENT_API_KEY in .env.
python app.py
```

The service listens on `0.0.0.0:8000` by default. Override it with the `HOST`
and `PORT` environment variables.
