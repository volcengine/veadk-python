# 07 · Structured output

Make the agent return JSON that matches a schema you define, instead of free
text. Pass a Pydantic model as `output_schema`.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```python
class Ticket(BaseModel):
    summary: str
    category: str
    priority: str
    sentiment: str

agent = Agent(output_schema=Ticket, instruction="Extract a support ticket.")

raw = await runner.run(messages="The app keeps crashing on billing!", ...)
ticket = Ticket.model_validate_json(raw)   # guaranteed to parse
```

The reply is guaranteed to conform to `Ticket`, so you can `model_validate_json`
(or `json.loads`) it directly — great for extraction, classification, and
feeding the result into downstream code.

> ⚠️ When `output_schema` is set, the agent returns **only** the structured
> answer — it cannot call tools or transfer to sub-agents.

## Run it

```bash
pip install veadk-python
cp .env.example .env   # then set MODEL_AGENT_API_KEY
python main.py
```

You'll get a parsed `Ticket` printed as pretty JSON.

## What to try next

- Add fields (e.g. `affected_feature: str`) and rerun.
- Combine structured extraction with a workflow ([06](../06_multi_agent/)): one
  agent extracts, the next acts on the structured result.
