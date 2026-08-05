"""Studio-compatible basic project import automation."""

from __future__ import annotations

from pathlib import PurePosixPath

from pydantic import Field

from veadk.cli.github_automations._shared import (
    AutomationPullRequest,
    PullRequestFile,
    RuntimePullRequestBody,
    join_repo_path,
    validate_runtime,
    workflow_path,
)
from veadk.cli.github_automations.runtime_delivery import runtime_delivery_workflow


class TemplateProjectBody(RuntimePullRequestBody):
    """Configuration submitted by the basic template card."""

    project_path: str = Field(
        default="agentkit-basic-agent", alias="projectPath", max_length=240
    )


def basic_template_files(project_name: str) -> dict[str, str]:
    files = {
        "app.py": '''"""__PROJECT_NAME__ — a VeADK agent with the full Studio App Server."""

from assistant import root_agent
from veadk.integrations.agentkit import create_agentkit_app, run_agentkit_app

app = create_agentkit_app(
    root_agent,
    {root_agent.name: "Basic Assistant"},
    enable_feishu=True,
)


if __name__ == "__main__":
    run_agentkit_app(app)
''',
        "assistant/__init__.py": """from .agent import root_agent

__all__ = ["root_agent"]
""",
        "assistant/agent.py": '''"""A minimal VeADK agent with one example tool."""

from veadk import Agent


def get_city_weather(city: str) -> dict[str, str]:
    """Get the current weather for a city.

    Args:
        city: The English name of the city, for example Beijing.
    """
    fixed_weather = {
        "beijing": "Sunny, 25°C",
        "shanghai": "Cloudy, 22°C",
        "shenzhen": "Partly cloudy, 29°C",
    }
    result = fixed_weather.get(city.lower().strip(), f"No data for {city}")
    return {"result": result}


root_agent = Agent(
    name="assistant",
    description="A friendly assistant that can look up the weather.",
    instruction="You are a helpful assistant. Use your tools when relevant.",
    tools=[get_city_weather],
)
''',
        "requirements.txt": """veadk-python>=1.0.5
agentkit-sdk-python
google-adk
lark-channel-sdk
lark-oapi
starlette<1.0.0
""",
        "Dockerfile": """FROM agentkit-prod-public-cn-beijing.cr.volces.com/base/py-simple:python3.12-bookworm-slim-latest

ENV UV_SYSTEM_PYTHON=1 UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./
RUN uv pip install -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "app.py"]
""",
        "README.md": """# __PROJECT_NAME__

A minimal VeADK Agent with the full Studio App Server and one example weather
tool.

## Run in VeADK Studio

```bash
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open `http://localhost:8000`. The app uses VeADK's enhanced Studio server,
including conversation APIs, health and topology endpoints, the bundled Web UI,
and local short-term memory fallback.

Pushes to the configured target branch are continuously published by the
GitHub Actions workflow added with this project.
""",
        ".env.example": """# Local Volcengine credentials. Never commit real values.
VOLCENGINE_ACCESS_KEY=
VOLCENGINE_SECRET_KEY=
# VOLCENGINE_REGION=cn-beijing

# Optional model overrides.
# MODEL_AGENT_PROVIDER=openai
# MODEL_AGENT_NAME=doubao-seed-1-6-250615
# MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3/
# MODEL_AGENT_API_KEY=

# Optional Feishu Channel credentials. Studio can create and bind these.
FEISHU_APP_ID=
FEISHU_APP_SECRET=
""",
        ".gitignore": """__pycache__/
*.pyc
.venv/
.env
.agentkit/artifacts/
""",
        ".dockerignore": """.git
.env
.venv/
__pycache__/
*.pyc
.DS_Store
Dockerfile
.dockerignore
README.md
""",
    }
    return {
        path: content.replace("__PROJECT_NAME__", project_name)
        for path, content in files.items()
    }


def build_template_project(body: TemplateProjectBody) -> AutomationPullRequest:
    repository, project_path = validate_runtime(body)
    project_name = (
        repository.rsplit("/", 1)[-1]
        if project_path == "."
        else PurePosixPath(project_path).name
    )
    files = [
        PullRequestFile(
            path=join_repo_path(project_path, path),
            content=content,
            commit_message="feat: import AgentKit basic template",
            must_be_new=True,
        )
        for path, content in basic_template_files(project_name).items()
    ]
    files.append(
        PullRequestFile(
            path=workflow_path("publish-agentkit", project_path),
            content=runtime_delivery_workflow(
                base_branch=body.base_branch,
                project_path=project_path,
                runtime_name=body.runtime_name,
                runtime_id=body.runtime_id,
                region=body.region,
            ),
            commit_message="feat: add AgentKit Runtime delivery",
            must_be_new=True,
        )
    )
    return AutomationPullRequest(
        repository=repository,
        files=tuple(files),
        branch_prefix="feat/agentkit-basic-template",
        title="feat: 导入 AgentKit basic 模板",
        description=(
            "导入带有 VeADK Studio App Server 的 basic Agent 项目，并添加持续"
            "发布到 AgentKit Runtime 的工作流。合并前请配置 Volcengine Secrets。"
        ),
    )
