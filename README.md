<p align="center">
    <img src="assets/images/logo.png" alt="Volcengine Agent Development Kit Logo" width="50%">
</p>

# Volcengine Agent Development Kit

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Deepwiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/volcengine/veadk-python)

An open-source kit for agent development, integrated the powerful capabilities of Volcengine.

For more details, see our [documents](https://volcengine.github.io/veadk-python/).

A [tutorial](https://github.com/volcengine/veadk-python/blob/main/veadk_tutorial.ipynb) is available by Jupyter Notebook, or open it in [Google Colab](https://colab.research.google.com/github/volcengine/veadk-python/blob/main/veadk_tutorial.ipynb) directly.

## Installation

### From PyPI

```python
pip install veadk-python

# install extensions
pip install veadk-python[extensions]
```

### Build from source

We use `uv` to build this project ([how-to-install-uv](https://docs.astral.sh/uv/getting-started/installation/)).

```bash
git clone ... # clone repo first

cd veadk-python

# create a virtual environment with python 3.12
uv venv --python 3.12

# only install necessary requirements
uv sync

# or, install extra requirements
# uv sync --extra database
# uv sync --extra eval
# uv sync --extra cli

# or, directly install all requirements
# uv sync --all-extras

# install veadk-python with editable mode
uv pip install -e .
```

## Configuration

We recommand you to create a `config.yaml` file in the root directory of your own project, `VeADK` is able to read it automatically. For running a minimal agent, you just need to set the following configs in your `config.yaml` file:

```yaml
model:
  agent:
    provider: openai
    name: doubao-seed-1-6-250615
    api_base: https://ark.cn-beijing.volces.com/api/v3/
    api_key: # <-- set your Volcengine ARK api key here
```

You can refer to the [config instructions](https://volcengine.github.io/veadk-python/configuration/) for more details.

## Have a try

Enjoy a minimal agent from VeADK:

```python
from veadk import Agent
import asyncio

agent = Agent()

res = asyncio.run(agent.run("hello!"))
print(res)
```

## AgentKit application

Use the shared AgentKit application factory when your project needs AgentKit
APIs, VeADK's bundled Web UI, health checks, and agent-topology endpoints. This
keeps platform routes and lifecycle code out of your agent module:

```python
from veadk import Agent
from veadk.integrations.agentkit import create_agentkit_app

root_agent = Agent(name="customer_support")
app = create_agentkit_app(root_agent)
```

See [`examples/generated_agentkit_project`](examples/generated_agentkit_project)
for a complete generated project.

The Agent Server metadata endpoint reports the root Agent's name, description,
model, sub-Agents, tools, skills, and mounted component summaries. Each Runtime
row in Studio has explicit connect and info actions; the info panel's tabs switch
between this live metadata and control-plane information without exposing prompts
or credentials.

The Studio deployment flow lists Feishu, knowledge-base, short-/long-term
memory, and observability settings in their feature sections. Values entered
there are mirrored in the deployment environment-variable summary and converted
to VeADK runtime environment variables only when deploying; secrets are not
written to generated source or exported YAML. For multi-instance runtimes, use
a database-backed short-term memory store so sessions remain available across
instances.

When a cloud image build fails from the bundled Web UI, the deployment error
includes a credential-safe excerpt from the build log so dependency and
Dockerfile failures can be diagnosed directly.

## Feishu bot channel

VeADK now provides `veadk.extensions.FeishuChannelExtension` for bridging a Feishu bot with a `Runner`. It maps `union_id` to `user_id`, and `thread_id` / `chat_id` to `session_id`, so VeADK memory and tracing can work directly in Feishu conversations.

```python
from veadk import Agent, Runner
from veadk.extensions import FeishuChannelExtension

agent = Agent()
runner = Runner(agent=agent, app_name="feishu_demo")
channel = FeishuChannelExtension(runner=runner)
```

Configure credentials with `TOOL_FEISHU_CHANNEL_APP_ID` and `TOOL_FEISHU_CHANNEL_APP_SECRET`, or in `config.yaml` under `tool.feishu_channel`.

## A2UI (agent-driven UI)

VeADK integrates Google's [A2UI](https://a2ui.org), letting an agent reply with
declarative UI (cards, rows, forms) instead of plain text. A client renders the
UI with native components. Enable it with a single flag (requires the optional
`a2ui-agent-sdk` dependency: `pip install veadk-python[a2ui]`):

```python
from veadk import Agent

agent = Agent(enable_a2ui=True)  # uses the bundled "basic" component catalog
```

A bundled React web UI renders A2UI over the standard ADK API server. The built
UI ships inside the package (`veadk/webui`, produced by `npm run build`), so
installed users can launch it directly. Its custom-agent workbench supports
in-page debugging followed by source review and AgentKit deployment
configuration. Knowledge-base, memory, tool, and tracing components request only
settings that cannot be derived automatically. Studio forwards its server-side
Volcengine credentials and lets VeADK resolve Ark, embedding, media, speech,
VeSearch, and APMPlus keys for debug runs and deployed runtimes:

```bash
veadk frontend --agents-dir examples           # serve UI + API on http://127.0.0.1:8000
```

To rebuild the UI from source (output goes to `veadk/webui`, which is committed
so it ships with the wheel):

```bash
cd frontend && npm install && npm run build
```

Point the agent at a custom component catalog (relative paths resolve against the
agent's directory; absolute paths work too). With no argument it auto-discovers a
`catalog.json` next to the agent, falling back to the bundled basic catalog:

```python
Agent(enable_a2ui=True, a2ui_catalog="catalog.json")  # beside the agent
```

Enterprises extend the component set in two matching halves: a backend catalog
(a `catalog.json` or a `veadk.a2ui.BaseA2UICatalog` subclass) and a frontend
renderer directory (`frontend/src/a2ui/components/<Name>/`). See
[`frontend/README.md`](frontend/README.md).

## Command line tools

`veadk studio deploy` automatically provisions `ServerlessApplicationRole`
when the required VeFaaS role is missing.

VeADK provides several useful command line tools for faster deployment and optimization, such as:

- `veadk deploy`: deploy your project to [Volcengine VeFaaS platform](https://www.volcengine.com/product/vefaas) (you can use `veadk init` to init a demo project first)
- `veadk prompt`: otpimize the system prompt of your agent by [PromptPilot](https://promptpilot.volcengine.com)
- `veadk frontend`: serve the A2UI web UI together with the ADK agent API server
  and forward its validated OAuth access token when connecting to an AgentKit
  runtime protected by `custom_jwt`; the login footer uses AgentKit product
  branding, and you can customize the browser/sidebar branding with `--site-title`
  and `--site-logo` (omitting the title keeps `VeADK Studio`)
- `veadk studio deploy`: deploy Studio and ensure its default IAM role has the
  required model, observability, search, security, memory, and identity system
  policies; target `cn-beijing` (default) or `cn-shanghai` with
  `--region`, automatically locate the Identity user pool across Beijing and
  Shanghai, and select the VeFaaS project with `--project` (default `default`);
  custom local or remote logo images are bundled into the deployment; the
  deployed client skips the second OAuth consent confirmation after login
- `veadk studio update --vefaas-app-name <app-name>`: build the frontend from a
  local VeADK source checkout and release it through the existing VeFaaS
  Application and Function. Omit `--region` and `--project` to search Beijing,
  Shanghai, and all visible projects. Existing URL, SSO, IAM, gateway,
  environment variables, title, and logo are preserved; pass `--site-title` or
  `--site-logo` only when those branding values should be replaced

Studio can assign comma-separated local usernames or OAuth emails to the
`admin` and `developer` roles:

```bash
veadk studio \
  --admin "admin,admin@example.com" \
  --developer "alice,alice@example.com"

veadk studio deploy \
  --user-pool-id <pool-id> \
  --allowed-client-id <client-id> \
  --vefaas-app-name <app-name> \
  --admin "admin@example.com" \
  --developer "alice@example.com,bob@example.com"
```

Supplying either role list enables role-based access control; users not in a
list are regular users, and `admin` wins when an identity appears in both
lists. Admins have all Studio capabilities and can see every Runtime.
Developers can add and manage agents but can see and manage only their own
Runtimes. Regular users can see only their own Runtimes; the add/manage-agent
sidebar items are hidden. The sidebar account footer shows the OAuth email
beneath the display name and identifies the current role with a color-coded
badge. Existing Runtimes without owner metadata are visible
only to admins unless they carry the legacy-compatible `veadk:author`
ownership tag. Local usernames are browser-provided and can be impersonated, so
use OAuth or gateway authentication for production authorization.

## Contribution

Before making your contribution to our repository, please install and config the `pre-commit` linter first.

```bash
pip install pre-commit
pre-commit install
```

Before commit or push your changes, please make sure the unittests are passed ,otherwise your PR will be rejected by CI/CD workflow. Running the unittests by:

```bash
pytest -n 16
```

## Security and privacy

This project takes security seriously.
For vulnerability reporting and supported versions, see [SECURITY.md](SECURITY.md)

## Contact with us

Join our discussion group by scanning the QR code below:

<p align="center">
    <img src="assets/images/veadk_group_qrcode.jpg" alt="Volcengine Agent Development Kit Logo" width="40%">
</p>

## License

This project is licensed under the [Apache 2.0 License](./LICENSE).
