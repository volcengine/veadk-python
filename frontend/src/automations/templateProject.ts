import {
  createGitHubPullRequest,
  normalizeGitHubRepository,
  normalizeRepositoryPath,
  type GitHubPullRequestFile,
} from "../adk/githubIntegration";
import {
  defaultCloudRegion,
  defaultModelName,
  defaultModelApiBase,
  type CloudProvider,
} from "../adk/cloudProvider";
import {
  baseBranchField,
  cloudCredentialSecretLabels,
  cloudCredentialSecretNames,
  cloudProviderDisplayName,
  commonGitHubInput,
  initialAutomationValues,
  repositoryField,
  runtimeIdField,
  runtimeNameField,
} from "./githubFields";
import { buildRuntimeDeliveryWorkflow } from "./runtimeDelivery";
import type { GitHubAutomationDefinition } from "./types";
import { automationT } from "./i18n";

function joinRepositoryPath(directory: string, path: string): string {
  return directory === "." ? path : `${directory}/${path}`;
}

function deliveryWorkflowPath(projectPath: string): string {
  const slug = projectPath.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase();
  return `.github/workflows/publish-agentkit-${slug || "root"}.yml`;
}

const AGENTKIT_BASE_IMAGES: Record<CloudProvider, string> = {
  volcengine:
    "agentkit-prod-public-cn-beijing.cr.volces.com/base/py-simple:python3.12-bookworm-slim-latest",
  byteplus:
    "agentkit-prod-public-ap-southeast-1.cr.bytepluses.com/base/py-simple:python3.12-bookworm-slim-latest",
};

const VEADK_VERSION = "1.1.9";
const VOLCENGINE_PYPI_INDEXES = [
  "https://repo.huaweicloud.com/repository/pypi/simple",
  "https://mirrors.aliyun.com/pypi/simple/",
  "https://pypi.org/simple",
] as const;

function buildPythonDependencyInstall(cloudProvider: CloudProvider): string {
  if (cloudProvider !== "volcengine") {
    return "RUN uv pip install -r requirements.txt";
  }

  const attempts = VOLCENGINE_PYPI_INDEXES.map(
    (index) => `uv pip install --index-url ${index} -r requirements.txt`,
  );
  return `RUN ${attempts.join(" || \\\n    ")}`;
}

function buildEnvExample(cloudProvider: CloudProvider): string {
  const secrets = cloudCredentialSecretNames(cloudProvider);
  const providerName = cloudProviderDisplayName(cloudProvider);
  return `# Local ${providerName} credentials. Never commit real values.
${secrets.accessKey}=
${secrets.secretKey}=
# ${secrets.sessionToken}=
${cloudProvider === "byteplus" ? "BYTEPLUS_REGION" : "VOLCENGINE_REGION"}=${defaultCloudRegion(cloudProvider)}
CLOUD_PROVIDER=${cloudProvider}
AGENTKIT_CLOUD_PROVIDER=${cloudProvider}

# Optional model overrides.
# MODEL_AGENT_PROVIDER=openai
# MODEL_AGENT_NAME=${defaultModelName(cloudProvider)}
# MODEL_AGENT_API_BASE=${defaultModelApiBase(cloudProvider)}
# MODEL_AGENT_API_KEY=

# Optional Feishu Channel credentials. Studio can create and bind these.
FEISHU_APP_ID=
FEISHU_APP_SECRET=
`;
}

export function buildBasicTemplateFiles(
  projectName: string,
  cloudProvider: CloudProvider = "volcengine",
): Record<string, string> {
  const files = {
    "app.py": `"""__PROJECT_NAME__ — a VeADK agent with the full Studio App Server."""

from assistant import root_agent
from veadk.integrations.agentkit import create_agentkit_app, run_agentkit_app

app = create_agentkit_app(
    root_agent,
    {root_agent.name: "Basic Assistant"},
    enable_feishu=True,
    enable_studio_tools=True,
)


if __name__ == "__main__":
    run_agentkit_app(app)
`,
    "assistant/__init__.py": `from .agent import root_agent

__all__ = ["root_agent"]
`,
    "assistant/agent.py": `"""A minimal VeADK agent with one example tool."""

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
`,
    "requirements.txt": `veadk-python==${VEADK_VERSION}
agentkit-sdk-python==0.8.4
google-adk==2.1.0
lark-channel-sdk==1.2.0
lark-oapi==1.7.3
starlette==0.52.1
`,
    Dockerfile: `FROM ${AGENTKIT_BASE_IMAGES[cloudProvider]}

ENV UV_SYSTEM_PYTHON=1 UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./
${buildPythonDependencyInstall(cloudProvider)}

COPY . .

EXPOSE 8000
CMD ["python", "app.py"]
`,
    "README.md": `# __PROJECT_NAME__

A minimal VeADK Agent with the full Studio App Server and one example weather
tool.

## Run in AgentKit Studio

\`\`\`bash
pip install -r requirements.txt
cp .env.example .env
python app.py
\`\`\`

Open \`http://localhost:8000\`. The app uses VeADK's enhanced Studio server,
including conversation APIs, health and topology endpoints, the bundled Web UI,
and local short-term memory fallback.

Pushes to the configured target branch are continuously published by the
GitHub Actions workflow added with this project.
`,
    ".env.example": buildEnvExample(cloudProvider),
    ".gitignore": `__pycache__/
*.pyc
.venv/
.env
.agentkit/artifacts/
`,
    ".dockerignore": `.git
.env
.venv/
__pycache__/
*.pyc
.DS_Store
Dockerfile
.dockerignore
README.md
`,
  };
  return Object.fromEntries(
    Object.entries(files).map(([path, content]) => [
      path,
      content.split("__PROJECT_NAME__").join(projectName),
    ]),
  );
}

export const templateProjectAutomation: GitHubAutomationDefinition = {
  id: "template",
  kind: "github",
  category: "development",
  icon: "github",
  name: "Import starter project",
  description: "Create a minimal Agent project in your repository with continuous delivery to AgentKit Runtime.",
  title: "Import starter project",
  subtitle: "Add a ready-to-run basic Agent and continuous delivery configuration to your repository",
  panel: "This creates a pull request containing the basic project and AgentKit Runtime delivery workflow.",
  submitLabel: "Import template and create PR",
  fields: [
    repositoryField,
    baseBranchField,
    {
      name: "projectPath",
      label: "Agent project directory",
      placeholder: "agentkit-basic-agent",
      help: "The basic project will be added here; app.py mounts the complete Studio App Server and serves as the entry point",
      required: true,
    },
    runtimeNameField,
    runtimeIdField,
  ],
  initialValues: ({ cloudProvider }) => initialAutomationValues(
    cloudProvider,
    { projectPath: "agentkit-basic-agent" },
  ),
  regionHelp: "Must match the target Runtime region",
  secrets: ({ cloudProvider }) => cloudCredentialSecretLabels(cloudProvider),
  submit(values, context, signal) {
    const input = commonGitHubInput(values);
    const repository = normalizeGitHubRepository(input.repository);
    const projectPath = normalizeRepositoryPath(values.projectPath, "agentkit-basic-agent");
    const projectName = projectPath === "."
      ? repository.split("/").slice(-1)[0] || "agentkit-basic-agent"
      : projectPath.split("/").slice(-1)[0] || "agentkit-basic-agent";
    const files: GitHubPullRequestFile[] = Object.entries(
      buildBasicTemplateFiles(projectName, context.cloudProvider),
    )
      .map(([path, content]) => ({
        path: joinRepositoryPath(projectPath, path),
        content,
        commitMessage: "feat: import AgentKit basic template",
        mustBeNew: true,
      }));
    files.push({
      path: deliveryWorkflowPath(projectPath),
      content: buildRuntimeDeliveryWorkflow({
        baseBranch: input.baseBranch,
        projectPath,
        runtimeName: values.runtimeName.trim(),
        runtimeId: values.runtimeId.trim(),
        region: input.region,
        cloudProvider: context.cloudProvider,
      }),
      commitMessage: "feat: add AgentKit Runtime delivery",
      mustBeNew: true,
    });
    return createGitHubPullRequest(
      {
        ...input,
        repository,
        files,
        branchPrefix: "feat/agentkit-basic-template",
        title: automationT("cards.template.pullRequest.title"),
        description: automationT("cards.template.pullRequest.description", {
          provider: cloudProviderDisplayName(context.cloudProvider),
        }),
      },
      signal,
    );
  },
};
