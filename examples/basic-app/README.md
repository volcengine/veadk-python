# basic-app · Deploy a front+back agent to Volcengine AgentKit

A minimal **full app**: one container that serves both the agent API and a web
UI, deployed to [Volcengine AgentKit](https://www.volcengine.com/) with the
`veadk agentkit` command.

> 中文版见 [README.zh.md](./README.zh.md)

## What's inside

```text
basic-app/
├── app.py                       # front+back server (the deploy entry point)
├── agents/
│   └── basic_app_agent/         # backend agent (A2UI on), exposes root_agent
├── agentkit.yaml                # AgentKit deployment config (build_script wired)
├── scripts/install_veadk.sh     # installs veadk[a2ui,pdf] (build time)
├── requirements.txt             # empty (veadk is installed by the build script)
├── .dockerignore
└── .env.example
```

- **Backend** — `agents/basic_app_agent` is a normal VeADK `Agent` with
  `enable_a2ui=True`, so it can answer with rich, declarative UI.
- **Frontend** — the built web UI ships **inside the veadk package**
  (`veadk/webui`). `app.py` mounts it, so once veadk[a2ui] is installed the
  container has everything — there is nothing to bundle into this project.
- **One process** — `app.py` builds the Google ADK FastAPI app
  (`/list-apps`, `/run_sse`, sessions, ...) and mounts the UI at `/`, on
  port 8000. AgentKit runs it with `python -m app`.

> The frontend (`veadk/webui`) and the A2UI Python support aren't on PyPI/`main`
> yet — they live on the **`feat/a2ui`** branch. So the image installs veadk
> from that branch via `scripts/install_veadk.sh` (a **shallow + sparse** clone
> over HTTP/1.1 that fetches only the `veadk/` package). A plain
> `pip install git+...@feat/a2ui` also works in theory, but a full clone of the
> repo's large docs history is slow/flaky in the build network, hence the
> targeted clone.

## 1. Configure

```bash
cd examples/basic-app
cp .env.example .env
# edit .env: MODEL_AGENT_API_KEY + VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
```

`veadk agentkit` uses the Volcengine AK/SK to build and deploy.

## 2. Run locally (optional)

```bash
pip install "veadk-python[a2ui,pdf]"
python app.py            # or: python -m app
# open http://127.0.0.1:8000
```

You should see the web UI; ask e.g. "show me a flight status card" and the agent
replies with rich A2UI. `/list-apps` returns `["basic_app_agent"]` and `/ping`
returns `{"status": "ok"}`.

### Attachments (image / PDF)

The composer's **+** button uploads **images** and **PDFs**. Images are sent to
the (vision-capable) model directly; PDFs are rendered to page images by a
`before_model_callback` (`veadk.utils.pdf_to_images`) so the model can read them
— this needs the `pdf` extra (included in `[a2ui,pdf]` above) and a
vision-capable model (the default `doubao-seed-1.6` is).

## 3. Deploy to AgentKit

```bash
# fill in account-specific fields in agentkit.yaml (interactive)
veadk agentkit config

# build the image and deploy in one step
veadk agentkit launch

# check status / send a test request once it's live
veadk agentkit status
veadk agentkit invoke "你好，做一张今天的天气卡片"
```

`veadk agentkit launch` = `build` + `deploy`. Use `veadk agentkit destroy` to
tear the runtime down.

## How the frontend reaches the container

AgentKit builds a Docker image whose build context is **this directory**
(`COPY . .`) and runs `python -m app`. The web UI is *not* copied from here — it
arrives **inside the veadk package** (`veadk/webui`) when the build script
installs `veadk[a2ui]` from the `feat/a2ui` branch. `scripts/install_veadk.sh`
is wired via `docker_build.build_script` in `agentkit.yaml` and runs during the
image build.

Why a build script rather than a one-line `pip install git+...`: a full clone of
the veadk repo (large docs/image history) repeatedly failed mid-fetch in the
build network (`curl 92 HTTP/2 stream not closed cleanly`). The script makes the
fetch tiny and reliable — `--depth 1 --filter=blob:none --sparse` so it pulls
only the `veadk/` package, over HTTP/1.1, with retries (~4 MB instead of the
whole repo).
