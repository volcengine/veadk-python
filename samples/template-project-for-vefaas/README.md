# Template project for Vefaas

This is a template project for Vefaas. You can use it as a starting point for your own project.

We implement an minimal agent to report weather in terms of the given city.

## Structure

| File | Illustration |
| - | - |
| `src/app.py` | The entrypoint of VeFaaS server. |
| `src/run.sh` | The launch script of VeFaaS server. |
| `src/requirements.txt` | Dependencies of your project. `VeADK`, `FastAPI`, and `uvicorn` must be included. |
| `src/config.py` | The agent and memory definitions. **You may edit this file.** |
| `config.yaml.example` | Envs for your project (e.g., `api_key`, `token`, ...). **You may edit this file.** |
| `deploy.py` | Local script for deployment. |

You must export your agent and short-term memory in `src/config.py`.

## Deploy

We recommand you deploy this project by the `cloud` module of VeADK.

```bash
python deploy.py
```

You may see output like this:

```bash
Successfully deployed on:

https://....volceapi.com
Message ID: ...
Response from ...: The weather in Beijing is sunny, with a temperature of 25°C.
App ID: ...
```
