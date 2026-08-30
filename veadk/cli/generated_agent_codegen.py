# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generate VeADK projects from frontend AgentDraft JSON on the backend."""

from __future__ import annotations

import re
from pprint import pformat
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from veadk.cli.generated_agent_catalog import (
    A2A_REGISTRY_ENV,
    EXPORTER_BY_ID,
    KB_BY_ID,
    LTM_BY_ID,
    STM_BY_ID,
    TOOL_BY_ID,
    EnvVar,
    a2a_registry_env_for_provider,
    env_for_provider,
    model_env_for_provider,
)
from veadk.cli.studio_model_catalog import is_provider_modelark_base_url
from veadk.extensions.harness.sidecar import (
    normalize_studio_harness_intent,
    studio_harness_env_example,
    studio_harness_intent_payload,
)
from veadk.tools.builtin_tools.create_agent.models import (
    CreateAgentsInput,
    LegacyCreateAgentsInput,
)

_PYTHON_LICENSE_HEADER = """# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""

_AGENTKIT_BASE_IMAGES = {
    "volcengine": "agentkit-prod-public-cn-beijing.cr.volces.com/base/py-simple:python3.12-bookworm-slim-latest",
    "byteplus": "agentkit-prod-public-ap-southeast-1.cr.bytepluses.com/base/py-simple:python3.12-bookworm-slim-latest",
}
_PYPI_FALLBACK_INDEX = "https://repo.huaweicloud.com/repository/pypi/simple"
_LARK_CLI_VERSION = "1.0.87"
_LARK_CLI_SHA256 = {
    "amd64": "6027b1ddc12440400581bbdf9554850d8e119c7dd400439b1220e7a87b9673c5",
    "arm64": "fade9a22d363172a9c18a8287c99c80d6d106a2900f3fce4015e4e156c5fc776",
}
_GITHUB_CLI_VERSION = "2.97.0"
_GITHUB_CLI_SHA256 = {
    "amd64": "a2c9b8497e1f85b1ad0dfcb78b5a622e098801b8e461e459e88e1ee12f018112",
    "arm64": "73ea440ecad9c9e284429997ee6f93577bc6f7bc6fba357ef62c53ad8fb641a5",
}

_DYNAMIC_AGENT_DELEGATION_RULES = """动态子智能体协作规则：
- 对于问候、身份介绍、能力说明或可以直接完成的简单任务，直接回答，不要创建子智能体。
- 对于需要专业技能、知识库、工具调用、资料检索或临时 Python 工具的复杂任务，通常必须先调用 collect_resources。根据用户任务提炼 2 到 5 个简短检索关键词，通过 skill_hub_keywords 传入。
- 如果用户明确禁止联网、知识库或任何外部资源，跳过 collect_resources，直接调用 create_agents，传入 collection_id=""，并确保每个 LLM 节点的 resources=[]。不得发起 Skill Hub 关键词检索或其他资源源调用；子智能体仍使用自身模型能力完成当前任务。
- collect_resources 返回的是候选资源，不会自动挂载。只创建完成任务所需的最少数量子智能体，并把实际需要的 Skill、知识库和内置工具完整 ref 显式写入对应 LLM 节点的 resources。存在相关 Skill 时至少绑定一个；确实没有匹配 Skill 时才允许不绑定 Skill。
- 调用 create_agents 前，必须把“当前一次性任务”和“可复用能力身份”分开：agents[*].task 完整保留当前用户的具体目标、对象、输入和交付要求；agents[*].name 以及所有 nodes[*] 的 id、description、instruction 只描述可重复使用的稳定能力域。
- 人物或虚构角色、品牌、产品、组织、平台或渠道、行业或赛道、细分领域、业务领域、内容类别、研究主题、源语言或目标语言、地点、日期、活动名称、具体题材、一次性问题或事件、文档标题、文件名、URL 等请求特有信息只能出现在 agents[*].task 中，不得出现在 name、id、description 或 instruction 中。即使这些信息会影响执行方法，也只能通过“用户指定的平台/产品/行业/主题/语言/问题”等参数化表达写入 instruction。禁止通过音译、拼音、翻译、首字母缩写、行业简称、拼接或轻微改写把这些特有信息写入名称。
- 子智能体名称使用简洁的 snake_case 能力名，例如 video_creation_agent、document_translation_agent、financial_report_analysis_agent；不要按本次交付物命名，也不要一律退化成 generic_agent 或 general_assistant，保留真正影响专业能力和工具选择的领域边界。
- 每个 LLM 节点的 instruction 必须是长期可复用的角色说明：要求读取当前用户请求及其上下文，明确期望输出格式和完成标准，使用所挂载资源完整完成当前任务，并直接向用户给出最终结果；不得复述或硬编码本次任务中的特有实体。需要临时计算能力时，可以在 python_tools 中提供完整代码。
- 小规模、可直接枚举或心算验证的问题优先由子智能体直接推理，不要创建临时 Python 工具。确需 python_tools 时，函数参数、返回值以及跨工具边界传递的全部数据必须可由标准 JSON 无损表达：对象键只能是字符串，不得使用 tuple、对象或其他非字符串字典键，也不得依赖 Python 特有类型在 JSON 往返后保持不变。组合、边或协同项等复合键必须改成记录列表，例如 [{"items": ["A", "C", "F"], "value": 13}]，并在工具内显式转换。调用前先检查生成函数的参数 schema；若 schema 不兼容或工具结果明显错误，立即重写工具，或者停止调用工具并直接完成推理，禁止用同一错误输入反复循环。
- 所有具体输出语言要求只能保留在 agents[*].task 中；即使用户要求使用其当前所用语言，也不得在节点 instruction 中写入或推断具体语言。instruction 必须统一参数化为“使用用户指定语言输出”。
- 示例：用户要求“给我生成葫芦娃大战钢铁侠的视频”时，使用 video_creation_agent / video_creator 等通用能力名称，把原句和视频交付要求放入 task，并为 LLM 节点绑定视频生成资源；不得使用 huluxia_vs_ironman_video 或任何包含葫芦娃、钢铁侠及其音译/翻译的 name、id、description、instruction。指定平台上的品牌营销必须使用 social_media_campaign_agent，并在 instruction 中写“适配用户指定的平台”，不得把平台名、品牌名或本次产品写入身份。指定产品故障的售后任务必须使用 customer_support_agent，并写“诊断用户当前描述的问题”，不得把产品类别或本次故障写入身份。财报文件分析、指定人物播客等任务同样抽象为 financial_report_analysis_agent、podcast_production_agent 等稳定能力。
- 精确示例：用户要求“请调研并比较三家主流新能源汽车公司的最新财务表现、产品竞争力与主要风险，给出结构化投资分析报告”时，必须使用 investment_analysis_agent 等跨行业可复用能力名称；description 和 instruction 只能描述调研用户指定公司、比较财务表现与竞争力、分析风险并生成投资报告的通用能力。完整原句和“新能源汽车”行业只放入 task。不得使用 ev_investment_research_agent、new_energy_vehicle_investment_agent，也不得在 description 或 instruction 中出现新能源汽车、EV、electric vehicle 等行业名称、简称或翻译。
- 文件翻译任务必须使用 document_translation_agent 等跨语言可复用能力名称，并在 instruction 中写“翻译为用户指定的目标语言”；文件名、源语言和目标语言完整保留在 task，不得使用 japanese_translation_agent，也不得在 description 或 instruction 中出现日语、Japanese 等本次指定语言。
- 区分“执行方法或交付类型”和“本次研究对象或内容类别”：前者可以成为能力身份，例如 investment_analysis、document_rag_qa、podcast_production、technology_comparison、incident_diagnostics；后者只能留在 task。不得使用 financial_rag_qa_assistant、music_album_research_agent、cloud_database_comparison_agent、cloud_api_diagnostic_agent 等绑定本次语料主题、节目题材、技术类别或运行环境的身份；应分别使用 document_rag_qa_agent、content_researcher、technology_comparison_agent、incident_diagnostics_agent 等跨主题名称，并在 instruction 中读取用户指定的语料、主题、候选技术或运行环境。
- 上述约束逐个适用于所有子节点，而不只是 agents[*].name：云上 API 故障任务的每个 node 都只能描述“诊断用户指定系统的当前故障”，不得出现 cloud 或 API；音乐专辑播客任务应使用 content_researcher、podcast_script_writer、podcast_audio_producer，并描述“用户指定主题”，不得出现 music、album 或 专辑；云数据库对比任务应使用 technology_researcher、technology_comparison_agent，并描述“用户指定的候选技术”，不得出现 cloud、database 或 数据库。
- agents[*].task 是当前任务具体信息的唯一载体；nodes[*].instruction 不要为了说明如何完成当前任务而再次复述研究对象或类别。技术方案对比节点使用领域中立模板：“读取当前用户请求，调研并比较用户指定的候选项，按用户要求的维度评估并输出结构化决策报告”，具体候选技术、所属类别和比较维度只从 task 与当前请求读取。
- 对任何技术方案对比任务，统一使用 technology_comparison_agent 作为可复用能力身份；需要拆分节点时，只使用 evidence_researcher、criteria_evaluator、decision_report_writer 等按执行步骤命名的节点。所有节点 description 和 instruction 只写“用户指定的候选项”“用户要求的评估维度”“结构化决策报告”，不得为说明角色而补充候选项所属技术类别。
- 当用户明确要求子智能体跨行业、跨领域或跨场景复用时，必须采用不绑定业务对象的最高合理抽象。对于带预算、风险、数量或其他约束的枚举、组合与敏感性分析，统一使用 decision_optimization_agent 或 decision_analysis_agent；节点只使用 constraint_validator、option_evaluator、scenario_analyst、decision_report_writer 等执行步骤名称。不得使用 portfolio、project、investment、asset、campaign 等业务对象或其中文、缩写作为 name、id、description 或 instruction 的身份边界，即使当前任务看起来属于该领域。
- 在调用 create_agents 前逐字段自检每个 agents[*].name 和 nodes[*] 的 id、description、instruction。只要其中仍含本次任务特有的品牌、平台或渠道、产品或品类、行业或赛道、细分领域、业务领域、内容类别、研究主题、源语言或目标语言、故障或事件、人物、题材、文件名，或这些词的拼音、翻译、首字母缩写、行业简称，工具调用就是无效的，必须先改写为通用能力表达。使用“替换测试”检查：把当前请求的实体、行业、赛道、主题和语言全部换成另一组后，这些身份字段应当保持不变。xiaohongshu、douyin、tiktok 等渠道都只能作为 task 中的运行时参数；新能源汽车、EV 等行业赛道，智能手机、电池异常等产品类别和具体问题，以及日语、Japanese 等目标语言也只能作为 task 数据。
- 调用 create_agents 时，在 handoff_to 中指定真正负责完成用户任务的智能体。任务移交后不要自行重复作答。
- 不要向用户暴露内部运行时名称、资源引用、版本判断或编排实现细节。"""


class GeneratedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str


class GeneratedProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    files: list[GeneratedFile]


class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shortTerm: bool = False
    longTerm: bool = False


class CustomTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    description: str = ""


class McpTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    transport: Literal["http", "stdio"] = "http"
    url: str = ""
    authToken: str = ""
    authTokenEnv: str = ""
    command: str = ""
    args: list[str] = Field(default_factory=list)


class A2ARegistryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    registrySpaceId: str = ""
    registryTopK: str = ""
    registryRegion: str = ""
    registryEndpoint: str = ""

    @field_validator(
        "registrySpaceId",
        "registryTopK",
        "registryRegion",
        "registryEndpoint",
        mode="before",
    )
    @classmethod
    def _coerce_string(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value)


class SelectedSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["skillhub", "local", "skillspace", "runtime"] = "skillhub"
    folder: str = ""
    name: str = ""
    description: str = ""
    slug: str = ""
    namespace: str = "public"
    localFiles: list[GeneratedFile] = Field(default_factory=list)
    skillSpaceId: str = ""
    skillSpaceName: str = ""
    skillSpaceRegion: str = ""
    skillId: str = ""
    version: str = ""

    @model_validator(mode="after")
    def _default_folder(self) -> "SelectedSkill":
        if not self.folder:
            self.folder = (
                self.name or self.slug.rsplit("/", 1)[-1] or self.skillId or "skill"
            )
        if not self.name:
            self.name = self.folder
        if self.source == "skillhub" and not self.namespace:
            self.namespace = "public"
        return self


class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = ""
    agent: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="allow")

    from_: str = Field(default="", alias="from")
    to: str = ""


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


class DeploymentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feishuEnabled: bool = False
    modelApiKeyId: str = ""
    modelApiKeyName: str = ""
    envValues: dict[str, str] = Field(default_factory=dict)


class EnvironmentSkillManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    folder: str = ""
    source: Literal["skillhub", "local", "skillspace"] = "local"
    version: str = ""
    digest: str = ""


class CloudEnvironmentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environmentId: str = ""
    environmentVersionId: str = ""
    cliTools: list[Literal["lark-cli", "github-cli", "pandoc"]] = Field(
        default_factory=list
    )
    dockerfile: str | None = Field(default=None, max_length=65_536)
    resolvedImage: str = Field(default="", exclude=True)
    environmentSkills: list[EnvironmentSkillManifestEntry] = Field(
        default_factory=list, exclude=True
    )

    @field_validator("cliTools")
    @classmethod
    def _dedupe_cli_tools(
        cls, value: list[Literal["lark-cli", "github-cli", "pandoc"]]
    ) -> list[Literal["lark-cli", "github-cli", "pandoc"]]:
        return list(dict.fromkeys(value))

    @field_validator("dockerfile")
    @classmethod
    def _validate_dockerfile(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Dockerfile 不能为空")
        return value


class HarnessSidecarIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    profile: Literal["default", "ops"] = "default"
    componentOverrides: dict[str, bool] = Field(default_factory=dict)
    catalogVersion: str | None = None
    planHash: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_selection(cls, value: Any) -> dict[str, Any]:
        return studio_harness_intent_payload(value)


class AgentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    cloudProvider: Literal["volcengine", "byteplus"] = "volcengine"
    description: str = ""
    instruction: str = ""
    dynamicAgentDelegation: bool = False
    agentType: Literal["llm", "sequential", "parallel", "loop", "a2a"] = "llm"
    maxIterations: int = 3
    a2aUrl: str = ""
    model: str = ""
    modelSource: Literal["ark", "custom"] | None = None
    modelName: str = ""
    modelProvider: str = ""
    modelApiBase: str = ""
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    knowledgebase: bool = False
    tracing: bool = False
    subAgents: list["AgentDraft"] = Field(default_factory=list)
    builtinTools: list[str] = Field(default_factory=list)
    customTools: list[CustomTool] = Field(default_factory=list)
    mcpTools: list[McpTool] = Field(default_factory=list)
    a2aRegistry: A2ARegistryConfig = Field(default_factory=A2ARegistryConfig)
    shortTermBackend: str = "local"
    longTermBackend: str = "local"
    longTermMemoryIndex: str = ""
    autoSaveSession: bool = False
    knowledgebaseBackend: str = "viking"
    knowledgebaseIndex: str = ""
    tracingExporters: list[str] = Field(default_factory=list)
    selectedSkills: list[SelectedSkill] = Field(default_factory=list)
    workflow: WorkflowConfig | None = None
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)
    cloudEnvironment: CloudEnvironmentConfig = Field(
        default_factory=CloudEnvironmentConfig
    )
    harnessSidecar: HarnessSidecarIntent | None = None

    @model_validator(mode="before")
    @classmethod
    def _ignore_retired_a2ui_option(cls, value: Any) -> Any:
        """Accept old Studio drafts without carrying A2UI into generation."""
        if not isinstance(value, dict) or "enableA2ui" not in value:
            return value
        normalized = value.copy()
        normalized.pop("enableA2ui")
        return normalized

    @field_validator("maxIterations", mode="before")
    @classmethod
    def _coerce_max_iterations(cls, value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 3


class GeneratedAgentProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: AgentDraft


class GeneratedAgentTestRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: AgentDraft
    runtimeId: str = ""
    runtimeRegion: str = "cn-beijing"


class _Acc:
    def __init__(
        self,
        cloud_provider: str = "volcengine",
        *,
        managed_mcp_gateway: bool = False,
    ) -> None:
        self.cloud_provider = cloud_provider
        self.managed_mcp_gateway = managed_mcp_gateway
        self.managed_mcp_http_count = 0
        self.imports: list[str] = []
        self.pre_lines: list[str] = []
        self.env: list[EnvVar] = list(model_env_for_provider(cloud_provider))
        self.extras: set[str] = set()
        self.used_names: set[str] = set()
        self.used_env_names: set[str] = set()
        self.agent_display_names: dict[str, str] = {}
        self.environment_skills: list[EnvironmentSkillManifestEntry] = []


def normalize_and_validate_draft(raw: Any) -> AgentDraft:
    if isinstance(raw, AgentDraft):
        return raw
    return AgentDraft.model_validate(raw)


_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENV_REFERENCE_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _env_segment(value: str, fallback: str) -> str:
    segment = re.sub(r"[^A-Z0-9]+", "_", (value or "").strip().upper())
    return segment.strip("_") or fallback


def _next_env_name(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    suffix = 2
    while f"{base}_{suffix}" in used:
        suffix += 1
    return f"{base}_{suffix}"


def prepare_mcp_auth(draft: AgentDraft) -> AgentDraft:
    """Move transient MCP tokens into deployment env values on a deep copy."""
    used: set[str] = set()
    env_values = dict(draft.deployment.envValues)

    def visit(node: AgentDraft) -> AgentDraft:
        agent_segment = _env_segment(node.name, "AGENT")
        tools: list[McpTool] = []
        for index, tool in enumerate(node.mcpTools):
            raw_token = tool.authToken.strip()
            reference = _ENV_REFERENCE_RE.fullmatch(raw_token)
            explicit = tool.authTokenEnv.strip()
            env_name = explicit if _ENV_NAME_RE.fullmatch(explicit) else ""
            if not env_name and reference:
                env_name = reference.group(1)
            if not env_name and raw_token:
                tool_segment = _env_segment(tool.name, f"TOOL_{index + 1}")
                env_name = _next_env_name(
                    f"MCP_{agent_segment}_{tool_segment}_AUTH_TOKEN",
                    used,
                )
            if env_name:
                used.add(env_name)
            if env_name and raw_token and reference is None:
                env_values[env_name] = raw_token
            tools.append(
                tool.model_copy(
                    deep=True,
                    update={"authToken": "", "authTokenEnv": env_name},
                )
            )
        return node.model_copy(
            deep=True,
            update={
                "mcpTools": tools,
                "subAgents": [visit(sub_agent) for sub_agent in node.subAgents],
            },
        )

    prepared = visit(draft)
    return prepared.model_copy(
        update={
            "deployment": prepared.deployment.model_copy(
                update={"envValues": env_values}
            )
        }
    )


def _safe_draft_payload(draft: AgentDraft) -> dict[str, Any]:
    """Serialize editable metadata without deployment values or MCP secrets."""
    payload = draft.model_dump(mode="json", by_alias=True)
    used: set[str] = set()

    def sanitize(node: dict[str, Any]) -> None:
        if not node.get("dynamicAgentDelegation"):
            node.pop("dynamicAgentDelegation", None)
        if node.get("cloudProvider") == "volcengine":
            node.pop("cloudProvider", None)
        if node.get("modelSource") is None:
            node.pop("modelSource", None)
        if not str(node.get("longTermMemoryIndex") or "").strip():
            node.pop("longTermMemoryIndex", None)
        cloud_environment = node.get("cloudEnvironment")
        if (
            isinstance(cloud_environment, dict)
            and not cloud_environment.get("cliTools")
            and cloud_environment.get("dockerfile") is None
        ):
            node.pop("cloudEnvironment", None)
        # Keep generated metadata byte-for-byte compatible for ordinary
        # projects. This optional field is emitted only when Sidecar is
        # actually selected.
        if node.get("harnessSidecar") is None:
            node.pop("harnessSidecar", None)
        agent_segment = _env_segment(str(node.get("name") or ""), "AGENT")
        tools = node.get("mcpTools")
        if isinstance(tools, list):
            for index, raw_tool in enumerate(tools):
                if not isinstance(raw_tool, dict):
                    continue
                raw_token = str(raw_tool.pop("authToken", "") or "").strip()
                explicit = str(raw_tool.get("authTokenEnv") or "").strip()
                reference = _ENV_REFERENCE_RE.fullmatch(raw_token)
                env_name = explicit if _ENV_NAME_RE.fullmatch(explicit) else ""
                if not env_name and reference:
                    env_name = reference.group(1)
                if not env_name and raw_token:
                    tool_segment = _env_segment(
                        str(raw_tool.get("name") or ""),
                        f"TOOL_{index + 1}",
                    )
                    env_name = _next_env_name(
                        f"MCP_{agent_segment}_{tool_segment}_AUTH_TOKEN",
                        used,
                    )
                if env_name:
                    used.add(env_name)
                    raw_tool["authTokenEnv"] = env_name
                else:
                    raw_tool.pop("authTokenEnv", None)
        deployment = node.get("deployment")
        if isinstance(deployment, dict):
            deployment.pop("envValues", None)
            if not str(deployment.get("modelApiKeyId") or "").strip():
                deployment.pop("modelApiKeyId", None)
            if not str(deployment.get("modelApiKeyName") or "").strip():
                deployment.pop("modelApiKeyName", None)
        sub_agents = node.get("subAgents")
        if isinstance(sub_agents, list):
            for sub_agent in sub_agents:
                if isinstance(sub_agent, dict):
                    sanitize(sub_agent)
        workflow = node.get("workflow")
        if isinstance(workflow, dict) and isinstance(workflow.get("nodes"), list):
            for workflow_node in workflow["nodes"]:
                if not isinstance(workflow_node, dict):
                    continue
                workflow_agent = workflow_node.get("agent")
                if isinstance(workflow_agent, dict):
                    sanitize(workflow_agent)

    sanitize(payload)
    return payload


def ident(raw: str, fallback: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or s[0].isdigit():
        return f"a_{s}" if s else fallback
    return s


def _agent_name(acc: _Acc, draft: AgentDraft, fallback: str) -> str:
    """Return the ADK-safe id while retaining the user-facing Agent name."""
    agent_name = ident(draft.name, fallback)
    acc.agent_display_names[agent_name] = draft.name.strip() or agent_name
    return agent_name


def _py_str(value: str) -> str:
    escaped = (
        (value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )
    return f'"{escaped}"'


def _py_triple(value: str) -> str:
    escaped = (value or "").replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return f'"""{escaped}"""'


def _unique_ident(acc: _Acc, raw: str, fallback: str) -> str:
    base = ident(raw, fallback)
    name = base
    n = 2
    while name in acc.used_names:
        name = f"{base}_{n}"
        n += 1
    acc.used_names.add(name)
    return name


def _add_import(acc: _Acc, line: str) -> None:
    if line not in acc.imports:
        acc.imports.append(line)


def _add_env(acc: _Acc, env: tuple[EnvVar, ...]) -> None:
    acc.env.extend(env_for_provider(acc.cloud_provider, env))


def _emit_tool_stub(acc: _Acc, name: str, description: str) -> str:
    fn = _unique_ident(acc, name, "custom_tool")
    doc = (description or "").strip() or f"TODO: 描述 {name} 的用途与参数。"
    comment_name = name.replace("\r", " ").replace("\n", " ")
    acc.pre_lines.append(
        f"def {fn}(query: str) -> dict:\n"
        f"    {_py_triple(doc)}\n"
        f"    # TODO: 实现「{comment_name}」的逻辑。\n"
        f'    return {{"result": f"{fn} 尚未实现: {{query}}"}}'
    )
    return fn


def _build_orchestrator(acc: _Acc, draft: AgentDraft, var_name: str) -> str:
    cls = {
        "parallel": "ParallelAgent",
        "loop": "LoopAgent",
        "sequential": "SequentialAgent",
    }.get(draft.agentType, "SequentialAgent")
    _add_import(acc, f"from google.adk.agents import {cls}")

    sub_vars: list[str] = []
    for idx, sub in enumerate(draft.subAgents):
        child_var = f"{var_name}_sub_{idx + 1}"
        _build_agent(acc, sub, child_var)
        sub_vars.append(child_var)

    kwargs = [
        f"name={_py_str(_agent_name(acc, draft, var_name))}",
        f"description={_py_str(draft.description or draft.name or 'A VeADK orchestrator agent.')}",
    ]
    if draft.agentType == "loop":
        kwargs.append(
            f"max_iterations={draft.maxIterations if draft.maxIterations > 0 else 3}"
        )
    kwargs.append(f"sub_agents=[{', '.join(sub_vars)}]")
    joined_kwargs = ",\n    ".join(kwargs)
    acc.pre_lines.append(f"{var_name} = {cls}(\n    {joined_kwargs},\n)")
    return var_name


def _build_a2a(acc: _Acc, draft: AgentDraft, var_name: str) -> str:
    _add_import(acc, "from veadk.a2a.remote_ve_agent import RemoteVeAgent")
    internal_draft = draft.model_copy(update={"name": ""})
    kwargs = [
        f"name={_py_str(_agent_name(acc, internal_draft, var_name))}",
        f"url={_py_str((draft.a2aUrl or '').strip())}",
    ]
    joined_kwargs = ",\n    ".join(kwargs)
    acc.pre_lines.append(f"{var_name} = RemoteVeAgent(\n    {joined_kwargs},\n)")
    return var_name


def _is_registry_backed_a2a(draft: AgentDraft) -> bool:
    return draft.agentType == "a2a" and draft.a2aRegistry.enabled


def _append_a2a_registry_tools(acc: _Acc, var_name: str) -> tuple[str, str]:
    _add_import(acc, "from veadk.a2a.registry_client import registry_config_from_env")
    _add_import(
        acc,
        "from veadk.tools.builtin_tools.a2a_registry import build_a2a_registry_tools",
    )
    registry_var = _unique_ident(
        acc,
        f"a2a_registry_config_{var_name}",
        "a2a_registry_config",
    )
    tools_var = _unique_ident(
        acc,
        f"a2a_registry_tools_{var_name}",
        "a2a_registry_tools",
    )
    acc.pre_lines.append(f"{registry_var} = registry_config_from_env()")
    acc.pre_lines.append(f"{tools_var} = build_a2a_registry_tools({registry_var})")
    return registry_var, tools_var


def _build_agent(acc: _Acc, draft: AgentDraft, var_name: str) -> str:
    if draft.agentType == "a2a":
        if draft.a2aRegistry.enabled:
            return _build_agent(
                acc,
                AgentDraft(agentType="llm", a2aRegistry=draft.a2aRegistry),
                var_name,
            )
        return _build_a2a(acc, draft, var_name)
    if draft.agentType != "llm":
        return _build_orchestrator(acc, draft, var_name)

    tool_exprs: list[str] = []

    if draft.dynamicAgentDelegation:
        _add_import(
            acc,
            "from .quick_mode_compat import CreateAgentToolset",
        )
        dynamic_agent_toolset = _unique_ident(
            acc,
            f"dynamic_agent_toolset_{var_name}",
            "dynamic_agent_toolset",
        )
        acc.pre_lines.append(f"{dynamic_agent_toolset} = CreateAgentToolset()")
        tool_exprs.append(dynamic_agent_toolset)

    for tool_id in draft.builtinTools:
        tool = TOOL_BY_ID.get(tool_id)
        if tool is None:
            continue
        _add_import(acc, tool.import_line)
        tool_exprs.extend(tool.tool_names)
        _add_env(acc, tool.env)
        if tool.pip_extra:
            acc.extras.add(tool.pip_extra)

    for custom_tool in draft.customTools:
        if custom_tool.name.strip():
            tool_exprs.append(
                _emit_tool_stub(acc, custom_tool.name, custom_tool.description)
            )

    for mcp_tool in draft.mcpTools:
        if mcp_tool.transport == "http" and mcp_tool.url.strip():
            _add_import(
                acc, "from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset"
            )
            _add_import(
                acc,
                "from google.adk.tools.mcp_tool.mcp_session_manager import "
                "StreamableHTTPConnectionParams",
            )
            v = _unique_ident(acc, f"{mcp_tool.name or 'mcp'}_mcp", "mcp_tool")
            if acc.managed_mcp_gateway:
                index = acc.managed_mcp_http_count
                acc.managed_mcp_http_count += 1
                acc.pre_lines.append(
                    f"{v} = MCPToolset("
                    f"connection_params=_managed_mcp_connection({index}))"
                )
                tool_exprs.append(v)
                continue
            headers = ""
            if mcp_tool.authTokenEnv.strip():
                _add_import(acc, "import os")
                env_name = mcp_tool.authTokenEnv.strip()
                headers = (
                    ', headers={"Authorization": '
                    f'"Bearer " + os.environ[{_py_str(env_name)}]}}'
                )
                acc.env.append(
                    EnvVar(
                        env_name,
                        True,
                        "",
                        f"{mcp_tool.name.strip() or 'MCP'} Bearer Token",
                    )
                )
            acc.pre_lines.append(
                f"{v} = MCPToolset(connection_params=StreamableHTTPConnectionParams("
                f"url={_py_str(mcp_tool.url.strip())}{headers}))"
            )
            tool_exprs.append(v)
        elif mcp_tool.transport == "stdio" and mcp_tool.command.strip():
            _add_import(
                acc, "from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset"
            )
            _add_import(
                acc,
                "from google.adk.tools.mcp_tool.mcp_toolset import "
                "StdioConnectionParams, StdioServerParameters",
            )
            v = _unique_ident(acc, f"{mcp_tool.name or 'mcp'}_mcp", "mcp_tool")
            args = ", ".join(_py_str(arg) for arg in mcp_tool.args if arg.strip())
            acc.pre_lines.append(
                f"{v} = MCPToolset(connection_params=StdioConnectionParams("
                "server_params=StdioServerParameters("
                f"command={_py_str(mcp_tool.command.strip())}, args=[{args}]), "
                "timeout=30))"
            )
            tool_exprs.append(v)

    registry_var = ""
    registry_source_var = ""
    if draft.a2aRegistry.enabled:
        registry_source_var = var_name
    else:
        for idx, sub in enumerate(draft.subAgents):
            if _is_registry_backed_a2a(sub):
                registry_source_var = f"{var_name}_sub_{idx + 1}"
                break
    if registry_source_var:
        registry_var, registry_tools_var = _append_a2a_registry_tools(
            acc, registry_source_var
        )
        tool_exprs.append(f"*{registry_tools_var}")
        _add_env(acc, A2A_REGISTRY_ENV)

    for name in draft.tools:
        if name.strip():
            tool_exprs.append(_emit_tool_stub(acc, name, ""))

    skill_folders = [
        skill.folder
        for skill in draft.selectedSkills
        if skill.source != "runtime" and skill.folder.strip()
    ]
    environment_skill_folders = [
        skill.folder for skill in acc.environment_skills if skill.folder.strip()
    ]
    if skill_folders or environment_skill_folders:
        _add_import(acc, "from pathlib import Path as _Path")
        _add_import(
            acc,
            "from google.adk.code_executors import UnsafeLocalCodeExecutor",
        )
        _add_import(acc, "from google.adk.skills import load_skill_from_dir")
        _add_import(acc, "from google.adk.tools.skill_toolset import SkillToolset")
        v = _unique_ident(acc, f"skills_{var_name}", "skill_toolset")
        loaders = [
            "        load_skill_from_dir("
            f'_Path(__file__).parent.parent.parent / "skills" / {_py_str(folder)})'
            for folder in skill_folders
        ]
        if not environment_skill_folders:
            joined_loaders = ",\n".join(loaders)
            acc.pre_lines.append(
                f"{v} = SkillToolset(\n"
                f"    skills=[\n{joined_loaders},\n    ],\n"
                "    code_executor=UnsafeLocalCodeExecutor(),\n"
                ")"
            )
        else:
            _add_import(acc, "import os as _os")
            project_skills_var = _unique_ident(
                acc, f"project_skills_{var_name}", "project_skills"
            )
            environment_skills_var = _unique_ident(
                acc, f"environment_skills_{var_name}", "environment_skills"
            )
            project_names_var = _unique_ident(
                acc, f"project_skill_names_{var_name}", "project_skill_names"
            )
            environment_root_var = _unique_ident(
                acc, f"environment_skill_root_{var_name}", "environment_skill_root"
            )
            joined_loaders = ",\n".join(loaders)
            environment_loaders = ",\n".join(
                "        load_skill_from_dir("
                f"{environment_root_var} / {_py_str(folder)})"
                for folder in environment_skill_folders
            )
            acc.pre_lines.extend(
                [
                    f"{project_skills_var} = [\n{joined_loaders}\n    ]",
                    (
                        f"{project_names_var} = "
                        f"{{skill.name.casefold() for skill in {project_skills_var}}}"
                    ),
                    (
                        f"{environment_root_var} = _Path(_os.environ.get("
                        '"VEADK_ENVIRONMENT_SKILLS_DIR", '
                        '"/opt/veadk/environment/skills"))'
                    ),
                    f"{environment_skills_var} = [\n{environment_loaders}\n    ]",
                    (
                        f"{environment_skills_var} = [environment_skill for "
                        f"environment_skill in {environment_skills_var} if "
                        f"environment_skill.name.casefold() not in {project_names_var}]"
                    ),
                    (
                        f"{v} = SkillToolset(\n"
                        f"    skills=[*{project_skills_var}, *{environment_skills_var}],\n"
                        "    code_executor=UnsafeLocalCodeExecutor(),\n"
                        ")"
                    ),
                ]
            )
        tool_exprs.append(v)

    kwargs = [
        f"name={_py_str(_agent_name(acc, draft, var_name))}",
        f"description={_py_str(draft.description or draft.name or 'A VeADK agent.')}",
        f"instruction=INSTRUCTION_{var_name.upper()}",
    ]
    instruction = draft.instruction or "You are a helpful assistant."
    if draft.dynamicAgentDelegation:
        instruction = f"{instruction.rstrip()}\n\n{_DYNAMIC_AGENT_DELEGATION_RULES}"
    acc.pre_lines.append(f"INSTRUCTION_{var_name.upper()} = {_py_triple(instruction)}")

    if tool_exprs:
        kwargs.append(f"tools=[{', '.join(tool_exprs)}]")
    if draft.modelName.strip():
        kwargs.append(f"model_name={_py_str(draft.modelName.strip())}")
    is_custom_model = draft.modelSource == "custom" or (
        draft.modelSource is None
        and bool(draft.modelApiBase.strip())
        and not is_provider_modelark_base_url(
            acc.cloud_provider,
            draft.modelApiBase,
        )
    )
    if is_custom_model:
        _add_import(acc, "import os")
        agent_segment = _env_segment(draft.name, _env_segment(var_name, "AGENT"))

        def custom_model_env(suffix: str) -> str:
            env_name = _next_env_name(
                f"CUSTOM_MODEL_{agent_segment}_{suffix}",
                acc.used_env_names,
            )
            acc.used_env_names.add(env_name)
            return env_name

        if draft.modelProvider.strip():
            provider_env = custom_model_env("PROVIDER")
            acc.env.append(
                EnvVar(
                    provider_env,
                    True,
                    draft.modelProvider.strip(),
                    f"{draft.name.strip() or 'Custom model'} Provider",
                )
            )
            kwargs.append(f"model_provider=os.environ[{_py_str(provider_env)}]")
        if draft.modelApiBase.strip():
            api_base_env = custom_model_env("API_BASE")
            acc.env.append(
                EnvVar(
                    api_base_env,
                    True,
                    draft.modelApiBase.strip(),
                    f"{draft.name.strip() or 'Custom model'} API Base",
                )
            )
            kwargs.append(f"model_api_base=os.environ[{_py_str(api_base_env)}]")
        api_key_env = custom_model_env("API_KEY")
        acc.env.append(
            EnvVar(
                api_key_env,
                True,
                "replace-with-your-own-model-api-key",
                f"{draft.name.strip() or 'Custom model'} API Key",
            )
        )
        kwargs.append(f"model_api_key=os.environ[{_py_str(api_key_env)}]")
    else:
        if draft.modelProvider.strip():
            kwargs.append(f"model_provider={_py_str(draft.modelProvider.strip())}")
        if draft.modelApiBase.strip():
            kwargs.append(f"model_api_base={_py_str(draft.modelApiBase.strip())}")

    if draft.memory.shortTerm:
        backend = STM_BY_ID.get(draft.shortTermBackend or "local")
        if backend:
            _add_import(
                acc, "from veadk.memory.short_term_memory import ShortTermMemory"
            )
            args = [f"backend={_py_str(backend.id)}"]
            if backend.extra_args:
                args.append(backend.extra_args)
            v = f"stm_{var_name}"
            acc.pre_lines.append(f"{v} = ShortTermMemory({', '.join(args)})")
            kwargs.append(f"short_term_memory={v}")
            _add_env(acc, backend.env)
            if backend.pip_extra:
                acc.extras.add(backend.pip_extra)

    if draft.memory.longTerm:
        backend = LTM_BY_ID.get(draft.longTermBackend or "local")
        if backend:
            _add_import(acc, "from veadk.memory.long_term_memory import LongTermMemory")
            idx = draft.longTermMemoryIndex.strip() or ident(draft.name, var_name)
            v = f"ltm_{var_name}"
            acc.pre_lines.append(
                f"{v} = LongTermMemory(backend={_py_str(backend.id)}, "
                f"index={_py_str(idx)}, app_name={_py_str(idx)})"
            )
            kwargs.append(f"long_term_memory={v}")
            if draft.autoSaveSession:
                kwargs.append("auto_save_session=True")
            _add_env(acc, backend.env)
            if backend.pip_extra:
                acc.extras.add(backend.pip_extra)

    if draft.knowledgebase:
        backend = KB_BY_ID.get(draft.knowledgebaseBackend or "viking")
        if backend:
            _add_import(acc, "from veadk.knowledgebase import KnowledgeBase")
            idx = draft.knowledgebaseIndex.strip() or ident(
                f"{draft.name}_kb", f"{var_name}_kb"
            )
            v = f"kb_{var_name}"
            acc.pre_lines.append(
                f"{v} = KnowledgeBase(backend={_py_str(backend.id)}, "
                f"index={_py_str(idx)}, app_name={_py_str(idx)})"
            )
            kwargs.append(f"knowledgebase={v}")
            _add_env(acc, backend.env)
            if backend.pip_extra:
                acc.extras.add(backend.pip_extra)

    if draft.tracing and draft.tracingExporters:
        _add_import(
            acc,
            "from veadk.tracing.telemetry.opentelemetry_tracer import "
            "OpentelemetryTracer",
        )
        v = f"tracer_{var_name}"
        acc.pre_lines.append(f"{v} = OpentelemetryTracer()")
        kwargs.append(f"tracers=[{v}]")
        for exporter_id in draft.tracingExporters:
            exporter = EXPORTER_BY_ID.get(exporter_id)
            if exporter:
                acc.env.append(
                    EnvVar(exporter.enable_flag, True, "true", f"{exporter.label} 开关")
                )
                _add_env(acc, exporter.env)

    sub_vars: list[str] = []
    for idx, sub in enumerate(draft.subAgents):
        if _is_registry_backed_a2a(sub):
            continue
        child_var = f"{var_name}_sub_{idx + 1}"
        _build_agent(acc, sub, child_var)
        sub_vars.append(child_var)
    if sub_vars:
        kwargs.append(f"sub_agents=[{', '.join(sub_vars)}]")

    joined_kwargs = ",\n    ".join(kwargs)
    acc.pre_lines.append(f"{var_name} = Agent(\n    {joined_kwargs},\n)")
    if registry_var:
        acc.pre_lines.append(
            f'setattr({var_name}, "_veadk_a2a_registry_config", {registry_var})'
        )
    return var_name


def _dedupe_imports(imports: list[str]) -> list[str]:
    return list(dict.fromkeys(imports))


def _dedupe_env(env: list[EnvVar]) -> list[EnvVar]:
    deduped: dict[str, EnvVar] = {}
    for item in env:
        cur = deduped.get(item.key)
        if cur is None:
            deduped[item.key] = item
        elif item.required and not cur.required:
            deduped[item.key] = EnvVar(
                cur.key,
                True,
                cur.placeholder,
                cur.comment,
                cur.hidden,
            )
    return list(deduped.values())


def render_env_example(env: list[EnvVar]) -> str:
    lines = [
        "# 复制为 .env 并填入真实值（或改用 config.yaml）。",
        "# 标记 [必填] 的变量缺失时 Agent 无法启动。",
        "",
    ]
    for item in env:
        if item.comment or item.required:
            lines.append(
                f"# {'[必填] ' if item.required else ''}{item.comment}".rstrip()
            )
        lines.append(f"{item.key}={item.placeholder}")
    return "\n".join(lines) + "\n"


def render_requirements(
    extras: set[str],
    include_feishu_channel: bool,
    *,
    dynamic_agent_delegation: bool = False,
) -> str:
    # Keep Studio-generated projects reproducible. google-adk 2.2+ requires
    # Starlette 1.x, while AgentKit SDK 0.8.4 still relies on APIs removed in
    # Starlette 1.x, so these versions must be upgraded together.
    all_extras = set(extras)
    if include_feishu_channel:
        all_extras.add("extensions")
    unique_extras = sorted(all_extras)
    extras_str = f"[{','.join(unique_extras)}]" if unique_extras else ""
    managed_sidecar = "harness-sidecar" in all_extras
    pkg = f"veadk-python{extras_str}==1.1.7"
    agentkit_sdk = (
        "agentkit-sdk-python==0.8.1"
        if managed_sidecar
        else "agentkit-sdk-python==0.8.4"
    )
    packages = [pkg, agentkit_sdk, "google-adk==2.1.0"]
    if include_feishu_channel:
        packages.extend(
            [
                "lark-channel-sdk==1.2.0",
                "lark-oapi==1.7.3",
            ]
        )
    if managed_sidecar:
        # Managed source staging copies VeADK without installing its project
        # metadata, so declare the MCP transport version that VeADK itself
        # requires instead of inheriting an arbitrary version from the base.
        packages.append("mcp==1.26.0")
    packages.append("starlette==0.52.1")
    return "\n".join(packages) + "\n"


def render_readme(name: str, draft: AgentDraft) -> str:
    lines = [
        f"# {name}",
        "",
        draft.description or "由 VeADK Web UI「自定义模式」生成的 Agent 项目。",
        "",
        "## 运行",
        "",
        "```bash",
        "pip install -r requirements.txt",
        "cp .env.example .env   # 填入你的密钥",
        "python app.py",
        "```",
        "",
        "`app.py` 通过 VeADK 的 AgentKit 公共组件发布 `root_agent`，监听 `0.0.0.0:8000`。",
        "",
    ]
    if draft.deployment.feishuEnabled:
        lines.extend(
            [
                "## 飞书机器人",
                "",
                "在 VeADK 前端部署时勾选「飞书」并填写 App ID / App Secret，runtime 会在同一进程内启动 FeishuChannelExtension。",
                "",
            ]
        )
    if draft.harnessSidecar and draft.harnessSidecar.enabled:
        lines.extend(
            [
                "## Harness Sidecar",
                "",
                "项目已启用 Harness Sidecar 公有集成。运行前请使用受支持的 Sidecar-enabled Runtime，并按 `.env.example` 配置所选能力。",
                "",
            ]
        )
    return "\n".join(lines)


def _render_app_py(
    pkg: str,
    feishu_channel_enabled: bool,
    harness_sidecar_enabled: bool,
) -> str:
    lines = [
        _PYTHON_LICENSE_HEADER.rstrip(),
        "",
        "from inspect import signature",
        "",
    ]
    if harness_sidecar_enabled:
        lines.append(
            f"from agents.{pkg}.agent import ("
            "AGENT_DISPLAY_NAMES, AGENT_DRAFT, app as agent_app, "
            "harness_extension, root_agent)"
        )
    else:
        lines.append(
            f"from agents.{pkg}.agent import AGENT_DISPLAY_NAMES, AGENT_DRAFT, root_agent"
        )
    lines.append(f"from agents.{pkg}.dynamic_a2a import enable_dynamic_a2a_tools")
    lines.extend(
        [
            "from veadk.integrations.agentkit import create_agentkit_app, run_agentkit_app",
            "",
            "_app_options = {",
            f'    "enable_feishu": {feishu_channel_enabled!r},',
            '    "enable_studio_tools": True,',
            "}",
            'if "agent_draft" in signature(create_agentkit_app).parameters:',
            '    _app_options["agent_draft"] = AGENT_DRAFT',
            "",
        ]
    )
    if harness_sidecar_enabled:
        lines.extend(
            [
                "app = create_agentkit_app(",
                "    app=agent_app,",
                "    display_names=AGENT_DISPLAY_NAMES,",
                "    harness_extension=harness_extension,",
                "    **_app_options,",
                ")",
            ]
        )
    else:
        lines.extend(
            [
                "app = create_agentkit_app(",
                "    root_agent,",
                "    AGENT_DISPLAY_NAMES,",
                "    **_app_options,",
                ")",
            ]
        )
    lines.extend(
        [
            "",
            "_agent_info_index = next(",
            "    index",
            "    for index, route in enumerate(app.router.routes)",
            '    if getattr(route, "path", "") == "/web/agent-info/{app_name}"',
            ")",
            "_agent_info_route = app.router.routes.pop(_agent_info_index)",
            "_agent_info_handler = _agent_info_route.endpoint",
            "",
            '@app.get("/web/agent-info/{app_name}")',
            "def agent_info_with_draft(app_name: str):",
            '    return {**_agent_info_handler(app_name), "draft": AGENT_DRAFT}',
            "",
            "app.router.routes.insert(_agent_info_index, app.router.routes.pop())",
        ]
    )
    lines.extend(["", "enable_dynamic_a2a_tools(app, root_agent)"])
    lines.extend(["", 'if __name__ == "__main__":', "    run_agentkit_app(app)", ""])
    return "\n".join(lines)


def _render_managed_main_py() -> str:
    """Bridge the CLI-managed Python Dockerfile to VeStudio's app entrypoint."""
    return "\n".join(
        [
            _PYTHON_LICENSE_HEADER.rstrip(),
            "",
            "from app import app",
            "from veadk.integrations.agentkit import run_agentkit_app",
            "",
            'if __name__ == "__main__":',
            "    run_agentkit_app(app)",
            "",
        ]
    )


def _render_quick_mode_compat_py() -> str:
    """Backport quick-mode runtime behavior while deployments stay on 1.1.7."""

    create_agents_schema = pformat(
        CreateAgentsInput.model_json_schema(by_alias=True),
        sort_dicts=False,
        width=88,
    )
    legacy_create_agents_schema = pformat(
        LegacyCreateAgentsInput.model_json_schema(by_alias=True),
        sort_dicts=False,
        width=88,
    )
    return (
        _PYTHON_LICENSE_HEADER
        + f'''\
from __future__ import annotations

from typing import Any

from google.adk.tools import FunctionTool, ToolContext
from google.genai import types
from typing_extensions import override

from veadk.tools.builtin_tools.create_agent import (
    CreateAgentToolset as _BaseCreateAgentToolset,
)
from veadk.tools.builtin_tools.create_agent import orchestrator as _orchestrator_module


_CREATE_AGENTS_DESCRIPTION = (
    "Create one or more sub-agents and transfer the current task to the agent "
    "named by handoff_to. Normally call collect_resources first, use its "
    "collection_id, and select only resource refs returned by that call. If the "
    "user explicitly prohibits network, knowledge-base, and external-resource "
    "access, skip collection, pass an empty collection_id, and leave every "
    "node's resources empty. Collected resources are candidates only and are "
    "not mounted automatically. For every LLM node, explicitly include each "
    "relevant Skill, knowledge base, and built-in tool in resources; when "
    "relevant Skills were returned, bind at least one. Keep the one-off user "
    "objective in agents[*].task and keep reusable identity fields free of "
    "request-specific entities. The selected sub-agent, not the main agent, "
    "produces the final answer."
)
_CREATE_AGENTS_SCHEMA = {create_agents_schema}
_LEGACY_CREATE_AGENTS_SCHEMA = {legacy_create_agents_schema}
_NATIVE_TASK_CONTEXT = hasattr(
    _orchestrator_module,
    "_with_delegated_task_context",
)


def _runtime_owner(tool_context: ToolContext | None) -> str:
    if tool_context is None:
        return "local"
    invocation = getattr(tool_context, "_invocation_context", None)
    session = getattr(invocation, "session", None)
    return ":".join(
        str(value or "")
        for value in (
            getattr(session, "app_name", None)
            or getattr(session, "appName", None),
            getattr(invocation, "user_id", None)
            or getattr(session, "user_id", None),
            getattr(session, "id", None),
            getattr(invocation, "invocation_id", None),
        )
    )


def _with_delegated_task(instruction: str, task: str) -> str:
    delegated_task = task.strip()
    if not delegated_task:
        return instruction
    return (
        f"{{instruction.rstrip()}}\\n\\n"
        "Current delegated task (runtime context, not reusable identity):\\n"
        f"{{delegated_task}}"
    )


def _inject_delegated_task(blueprint: Any) -> Any:
    if _NATIVE_TASK_CONTEXT:
        return blueprint
    nodes = [
        node.model_copy(
            update={{
                "instruction": _with_delegated_task(
                    node.instruction,
                    blueprint.task,
                )
            }}
        )
        if node.type == "llm"
        else node
        for node in blueprint.nodes
    ]
    return blueprint.model_copy(update={{"nodes": nodes}})


class _RuntimeCompatibleCreateAgentsTool(FunctionTool):
    def __init__(self, function: Any, *, parameters_json_schema: dict[str, Any]):
        self._parameters_json_schema = parameters_json_schema
        super().__init__(function)

    @override
    def _get_declaration(self) -> types.FunctionDeclaration | None:
        return types.FunctionDeclaration(
            name=self.name,
            description=_CREATE_AGENTS_DESCRIPTION,
            parameters_json_schema=self._parameters_json_schema,
        )


class CreateAgentToolset(_BaseCreateAgentToolset):
    """Keep quick-mode semantics available in the pinned 1.1.7 runtime."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        schema = (
            _CREATE_AGENTS_SCHEMA
            if self._input_model.__name__ == "CreateAgentsInput"
            else _LEGACY_CREATE_AGENTS_SCHEMA
        )
        self._tools[1] = _RuntimeCompatibleCreateAgentsTool(
            self.create_agents,
            parameters_json_schema=schema,
        )

    @override
    async def create_agents(
        self,
        collection_id: str,
        agents: list[Any],
        handoff_to: str,
        tool_context: ToolContext | None = None,
    ) -> dict[str, Any]:
        request = self._input_model.model_validate(
            {{
                "collection_id": collection_id,
                "agents": agents,
                "handoff_to": handoff_to,
            }}
        )
        parsed_agents = list(request.agents)
        if not collection_id:
            invalid_nodes = [
                f"{{blueprint.name}}.{{node.id}}"
                for blueprint in parsed_agents
                for node in blueprint.nodes
                if node.type == "llm" and node.resources
            ]
            if invalid_nodes:
                raise ValueError(
                    "Offline agent creation requires empty resources for every "
                    f"LLM node: {{', '.join(invalid_nodes)}}."
                )
            snapshot = self._store.put(
                owner=_runtime_owner(tool_context),
                capabilities=self.capabilities,
                resources=[],
            )
            collection_id = snapshot.collection_id

        compatible_agents = [
            _inject_delegated_task(blueprint) for blueprint in parsed_agents
        ]
        return await super().create_agents(
            collection_id=collection_id,
            agents=compatible_agents,
            handoff_to=handoff_to,
            tool_context=tool_context,
        )
'''
    )


def _render_dynamic_a2a_py() -> str:
    return (
        _PYTHON_LICENSE_HEADER
        + r"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from google.adk.agents import RunConfig
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.run_config import StreamingMode
from google.adk.apps.app import App
from google.adk.cli.adk_web_server import RunAgentRequest
from google.adk.runners import Runner as AdkRunner
from google.adk.utils.context_utils import Aclosing
from google.genai import types
from veadk.cli.frontend_invocation import FrontendInvocationPlugin


_SERVER_STATE_KEY = "_veadk_agentkit_server"
_ADK_SERVER_STATE_KEY = "_veadk_adk_server"
_DYNAMIC_A2A_ROUTES_ENABLED_STATE_KEY = "_veadk_dynamic_a2a_routes_enabled"
_REGISTRY_CONFIG_ATTR = "_veadk_a2a_registry_config"


def _tool_name(tool: object) -> str | None:
    name = getattr(tool, "__name__", None) or getattr(tool, "name", None)
    return str(name) if name else None


def _content_text(content: object) -> str:
    parts = getattr(content, "parts", None) or []
    texts: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            texts.append(str(text))
    return "\n".join(texts)


def _has_a2a_registry_config(agent: object) -> bool:
    if getattr(agent, _REGISTRY_CONFIG_ATTR, None) is not None:
        return True
    return any(
        _has_a2a_registry_config(child)
        for child in getattr(agent, "sub_agents", []) or []
    )


def _add_dynamic_a2a_agent_tools(agent: object, prompt: str) -> int:
    attached = 0
    registry_config = getattr(agent, _REGISTRY_CONFIG_ATTR, None)
    prompt = prompt.strip()
    if registry_config is not None and prompt:
        from veadk.tools.builtin_tools.a2a_registry import build_remote_a2a_agent_tools

        dynamic_tools = build_remote_a2a_agent_tools(prompt, registry_config)
        existing = {
            name
            for tool in getattr(agent, "tools", []) or []
            if (name := _tool_name(tool))
        }
        for tool in dynamic_tools:
            name = _tool_name(tool)
            if not name or name in existing:
                continue
            getattr(agent, "tools").append(tool)
            existing.add(name)
            attached += 1

    for child in getattr(agent, "sub_agents", []) or []:
        attached += _add_dynamic_a2a_agent_tools(child, prompt)
    return attached


def _spawn_dynamic_a2a_agent(base_agent: BaseAgent, prompt: str) -> BaseAgent:
    cloned = base_agent.clone(update={})
    attached = _add_dynamic_a2a_agent_tools(cloned, prompt)
    if _has_a2a_registry_config(cloned):
        print(
            f"dynamic A2A tool assembly completed for this turn: attached={attached}",
            flush=True,
        )
    return cloned


def _promote_route(app: FastAPI, endpoint) -> None:
    routes = app.router.routes
    for index, route in enumerate(routes):
        if getattr(route, "endpoint", None) == endpoint:
            routes.insert(0, routes.pop(index))
            return


def _has_dynamic_a2a_routes(app: FastAPI) -> bool:
    expected = {
        ("/run", "run_agent_dynamic"),
        ("/run_sse", "run_agent_sse_dynamic"),
        ("/invoke", "invoke_agent_dynamic"),
    }
    found: set[tuple[str, str]] = set()
    for route in app.router.routes:
        path = getattr(route, "path", None)
        endpoint_name = getattr(getattr(route, "endpoint", None), "__name__", "")
        if (path, endpoint_name) in expected:
            found.add((path, endpoint_name))
    return expected.issubset(found)


class _RuntimeServices:
    def __init__(self, app: FastAPI):
        agent_server = getattr(app.state, _SERVER_STATE_KEY, None)
        if agent_server is not None:
            self._load_from_server(getattr(agent_server, "server", agent_server))
            return

        adk_server = getattr(app.state, _ADK_SERVER_STATE_KEY, None)
        if adk_server is not None:
            self._load_from_server(adk_server)
            return

        attrs = getattr(app, "_tmpl_attrs", {})
        self.default_app_name = attrs.get("app_name")
        self.current_app_name_ref = attrs.get("current_app_name_ref")
        self.artifact_service = attrs.get("artifact_service")
        self.session_service = attrs.get("session_service")
        self.memory_service = attrs.get("memory_service")
        self.credential_service = attrs.get("credential_service")
        self.auto_create_session = bool(attrs.get("auto_create_session", False))

    def _load_from_server(self, server: object) -> None:
        self.default_app_name = getattr(server, "default_app_name", None)
        self.current_app_name_ref = getattr(server, "current_app_name_ref", None)
        self.artifact_service = getattr(server, "artifact_service", None)
        self.session_service = getattr(server, "session_service", None)
        self.memory_service = getattr(server, "memory_service", None)
        self.credential_service = getattr(server, "credential_service", None)
        self.auto_create_session = bool(getattr(server, "auto_create_session", False))


def _dynamic_runner(services: _RuntimeServices, *, app_name: str, root_agent: BaseAgent, prompt: str):
    if services.session_service is None:
        raise RuntimeError("ADK session service is unavailable")
    run_agent = _spawn_dynamic_a2a_agent(root_agent, prompt)
    agent_app = App(
        name=app_name,
        root_agent=run_agent,
        plugins=[FrontendInvocationPlugin()],
    )
    return AdkRunner(
        app=agent_app,
        artifact_service=services.artifact_service,
        session_service=services.session_service,
        memory_service=services.memory_service,
        credential_service=services.credential_service,
        auto_create_session=services.auto_create_session,
    )


def _resolve_run_app_name(services: _RuntimeServices, root_agent: BaseAgent, req: RunAgentRequest) -> str:
    app_name = req.app_name or services.default_app_name
    if not app_name:
        app_name = getattr(root_agent, "name", "") or ""
    if not app_name:
        raise HTTPException(
            status_code=400,
            detail="app_name is required when ADK_DEFAULT_APP_NAME is not set",
        )
    req.app_name = app_name
    if services.current_app_name_ref is not None:
        services.current_app_name_ref.value = app_name
    return app_name


def _run_request_custom_metadata(req: RunAgentRequest) -> dict[str, Any] | None:
    metadata = getattr(req, "custom_metadata", None)
    return metadata if isinstance(metadata, dict) and metadata else None


def _resolve_invoke_app_name(services: _RuntimeServices, root_agent: BaseAgent) -> str:
    app_name = services.default_app_name or getattr(root_agent, "name", "") or ""
    if not app_name:
        raise HTTPException(
            status_code=400,
            detail="app_name is required when ADK_DEFAULT_APP_NAME is not set",
        )
    if services.current_app_name_ref is not None:
        services.current_app_name_ref.value = app_name
    return app_name


async def _invoke_text(request: Request) -> str:
    body = await request.body()
    if not body:
        return ""
    try:
        payload = json.loads(body)
    except Exception:
        return body.decode("utf-8", errors="replace")
    if isinstance(payload, dict):
        text = payload.get("prompt")
        if text is not None:
            return str(text)
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return ""


def enable_dynamic_a2a_tools(app: FastAPI, root_agent: BaseAgent) -> None:
    if _has_dynamic_a2a_routes(app):
        return

    services = _RuntimeServices(app)
    session_service = services.session_service
    if session_service is None:
        return

    @app.post("/run", response_model=None)
    async def run_agent_dynamic(
        req: RunAgentRequest,
        request: Request,
    ) -> list[Any] | Response:
        app_name = _resolve_run_app_name(services, root_agent, req)
        runner = _dynamic_runner(
            services,
            app_name=app_name,
            root_agent=root_agent,
            prompt=_content_text(req.new_message),
        )
        custom_metadata = _run_request_custom_metadata(req)
        run_config = (
            RunConfig(custom_metadata=custom_metadata) if custom_metadata else None
        )

        async def worker() -> list[Any]:
            async with Aclosing(
                runner.run_async(
                    user_id=req.user_id,
                    session_id=req.session_id,
                    new_message=req.new_message,
                    state_delta=req.state_delta,
                    invocation_id=req.invocation_id,
                    run_config=run_config,
                )
            ) as agen:
                return [event async for event in agen]

        worker_task = asyncio.create_task(worker())

        async def monitor() -> None:
            try:
                while True:
                    message = await request.receive()
                    if message.get("type") == "http.disconnect":
                        worker_task.cancel()
                        break
            except asyncio.CancelledError:
                pass

        monitor_task = asyncio.create_task(monitor())
        try:
            return await worker_task
        except asyncio.CancelledError:
            if await request.is_disconnected():
                return Response(status_code=499)
            raise
        finally:
            monitor_task.cancel()

    @app.post("/run_sse")
    async def run_agent_sse_dynamic(req: RunAgentRequest) -> StreamingResponse:
        app_name = _resolve_run_app_name(services, root_agent, req)
        runner = _dynamic_runner(
            services,
            app_name=app_name,
            root_agent=root_agent,
            prompt=_content_text(req.new_message),
        )
        stream_mode = StreamingMode.SSE if req.streaming else StreamingMode.NONE
        custom_metadata = _run_request_custom_metadata(req)

        if not runner.auto_create_session:
            session = await session_service.get_session(
                app_name=app_name,
                user_id=req.user_id,
                session_id=req.session_id,
            )
            if not session:
                await session_service.create_session(
                    app_name=app_name,
                    user_id=req.user_id,
                    session_id=req.session_id,
                )

        async def event_generator():
            try:
                async with Aclosing(
                    runner.run_async(
                        user_id=req.user_id,
                        session_id=req.session_id,
                        new_message=req.new_message,
                        state_delta=req.state_delta,
                        run_config=RunConfig(
                            streaming_mode=stream_mode,
                            custom_metadata=custom_metadata,
                        ),
                        invocation_id=req.invocation_id,
                    )
                ) as agen:
                    async for event in agen:
                        events_to_stream = [event]
                        if (
                            not req.function_call_event_id
                            and event.actions.artifact_delta
                            and event.content
                            and event.content.parts
                        ):
                            content_event = event.model_copy(deep=True)
                            content_event.actions.artifact_delta = {}
                            artifact_event = event.model_copy(deep=True)
                            artifact_event.content = None
                            events_to_stream = [content_event, artifact_event]

                        for event_to_stream in events_to_stream:
                            yield (
                                "data: "
                                + event_to_stream.model_dump_json(
                                    exclude_none=True,
                                    by_alias=True,
                                )
                                + "\n\n"
                            )
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.post("/invoke")
    async def invoke_agent_dynamic(request: Request) -> StreamingResponse:
        app_name = _resolve_invoke_app_name(services, root_agent)
        user_id = request.headers.get("user_id") or "agentkit_user"
        session_id = request.headers.get("session_id") or ""
        prompt = await _invoke_text(request)
        content = types.UserContent(parts=[types.Part(text=prompt or "")])

        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        if not session:
            await session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
            )

        runner = _dynamic_runner(
            services,
            app_name=app_name,
            root_agent=root_agent,
            prompt=prompt,
        )

        async def event_generator():
            try:
                async with Aclosing(
                    runner.run_async(
                        user_id=user_id,
                        session_id=session_id,
                        new_message=content,
                        run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                    )
                ) as agen:
                    async for event in agen:
                        yield (
                            "data: "
                            + event.model_dump_json(
                                exclude_none=True,
                                by_alias=True,
                            )
                            + "\n\n"
                        )
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    _promote_route(app, run_agent_dynamic)
    _promote_route(app, run_agent_sse_dynamic)
    _promote_route(app, invoke_agent_dynamic)
    setattr(app.state, _DYNAMIC_A2A_ROUTES_ENABLED_STATE_KEY, True)
"""
    )


def _a2a_registry_env_values(draft: AgentDraft) -> dict[str, str]:
    defaults = {
        item.key: item.placeholder
        for item in a2a_registry_env_for_provider(draft.cloudProvider)
    }
    if draft.a2aRegistry.enabled:
        registry = draft.a2aRegistry
        return {
            "REGISTRY_SPACE_ID": registry.registrySpaceId.strip(),
            "REGISTRY_TOP_K": registry.registryTopK.strip()
            or defaults["REGISTRY_TOP_K"],
            "REGISTRY_REGION": registry.registryRegion.strip()
            or defaults["REGISTRY_REGION"],
            "REGISTRY_ENDPOINT": registry.registryEndpoint.strip()
            or defaults["REGISTRY_ENDPOINT"],
        }
    for sub_agent in draft.subAgents:
        values = _a2a_registry_env_values(
            sub_agent.model_copy(update={"cloudProvider": draft.cloudProvider})
        )
        if values:
            return values
    return {}


def debug_runtime_env_from_draft(draft: AgentDraft) -> dict[str, str]:
    """Return runtime env values allowed by active components in a debug draft."""
    draft = prepare_mcp_auth(draft)
    allowed_keys: set[str] = set()
    fixed_values: dict[str, str] = {}
    uses_ark_model = False
    ark_model_name = ""

    def allow_env(items: tuple[EnvVar, ...]) -> None:
        allowed_keys.update(item.key for item in items)

    def visit(node: AgentDraft) -> None:
        nonlocal ark_model_name, uses_ark_model
        is_custom_model = node.modelSource == "custom" or (
            node.modelSource is None
            and bool(node.modelApiBase.strip())
            and not is_provider_modelark_base_url(
                draft.cloudProvider,
                node.modelApiBase,
            )
        )
        if is_custom_model:
            agent_segment = _env_segment(node.name, "AGENT")
            if node.modelProvider.strip():
                provider_env = _next_env_name(
                    f"CUSTOM_MODEL_{agent_segment}_PROVIDER",
                    allowed_keys,
                )
                allowed_keys.add(provider_env)
                fixed_values[provider_env] = node.modelProvider.strip()
            if node.modelApiBase.strip():
                api_base_env = _next_env_name(
                    f"CUSTOM_MODEL_{agent_segment}_API_BASE",
                    allowed_keys,
                )
                allowed_keys.add(api_base_env)
                fixed_values[api_base_env] = node.modelApiBase.strip()
            api_key_env = _next_env_name(
                f"CUSTOM_MODEL_{agent_segment}_API_KEY",
                allowed_keys,
            )
            allowed_keys.add(api_key_env)
        elif node.agentType == "llm":
            uses_ark_model = True
            if not ark_model_name:
                ark_model_name = node.modelName.strip()
        for tool_id in node.builtinTools:
            tool = TOOL_BY_ID.get(tool_id)
            if tool:
                allow_env(tool.env)
        for mcp_tool in node.mcpTools:
            if mcp_tool.authTokenEnv:
                allowed_keys.add(mcp_tool.authTokenEnv)
        if node.a2aRegistry.enabled:
            registry = node.a2aRegistry
            defaults = {
                item.key: item.placeholder
                for item in a2a_registry_env_for_provider(draft.cloudProvider)
            }
            fixed_values.update(
                {
                    "REGISTRY_SPACE_ID": registry.registrySpaceId.strip(),
                    "REGISTRY_TOP_K": registry.registryTopK.strip()
                    or defaults["REGISTRY_TOP_K"],
                    "REGISTRY_REGION": registry.registryRegion.strip()
                    or defaults["REGISTRY_REGION"],
                    "REGISTRY_ENDPOINT": registry.registryEndpoint.strip()
                    or defaults["REGISTRY_ENDPOINT"],
                }
            )
        if node.memory.shortTerm:
            backend = STM_BY_ID.get(node.shortTermBackend)
            if backend:
                allow_env(backend.env)
        if node.memory.longTerm:
            backend = LTM_BY_ID.get(node.longTermBackend)
            if backend:
                allow_env(backend.env)
        if node.knowledgebase:
            backend = KB_BY_ID.get(node.knowledgebaseBackend)
            if backend:
                allow_env(backend.env)
        if node.tracing:
            for exporter_id in node.tracingExporters:
                exporter = EXPORTER_BY_ID.get(exporter_id)
                if exporter:
                    allow_env(exporter.env)
                    fixed_values[exporter.enable_flag] = "true"
        for sub_agent in node.subAgents:
            visit(sub_agent)

    visit(draft)
    if uses_ark_model:
        model_env = {
            item.key: item.placeholder
            for item in model_env_for_provider(draft.cloudProvider)
        }
        fixed_values["MODEL_AGENT_PROVIDER"] = (
            model_env.get("MODEL_AGENT_PROVIDER") or "openai"
        )
        fixed_values["MODEL_AGENT_API_BASE"] = model_env.get("MODEL_AGENT_API_BASE", "")
        selected_model_name = ark_model_name or model_env.get("MODEL_AGENT_NAME", "")
        fixed_values["MODEL_AGENT_NAME"] = selected_model_name
        # The managed Sidecar runtime still reads the legacy model-name key.
        fixed_values["MODEL_NAME"] = selected_model_name
    if draft.deployment.modelApiKeyId.strip():
        fixed_values["MODEL_AGENT_API_KEY_ID"] = draft.deployment.modelApiKeyId.strip()
    if draft.deployment.modelApiKeyName.strip():
        fixed_values["MODEL_AGENT_API_KEY_NAME"] = (
            draft.deployment.modelApiKeyName.strip()
        )
    env = {
        key: value
        for key, value in draft.deployment.envValues.items()
        if key in allowed_keys and value.strip()
    }
    env.update(fixed_values)
    return env


def _materialize_a2a_registry_env(env: list[EnvVar], draft: AgentDraft) -> list[EnvVar]:
    values = _a2a_registry_env_values(draft)
    if not values:
        return env
    return [
        EnvVar(
            item.key,
            item.required,
            values.get(item.key, item.placeholder),
            item.comment,
            item.hidden,
        )
        for item in env
    ]


def _render_cli_install(
    *,
    asset_name: str,
    version: str,
    checksums: dict[str, str],
    download_urls: list[str],
    archive_member: str,
    install_source: str,
    cleanup_source: str,
    binary_name: str,
) -> str:
    quoted_download_urls = " ".join(f'"{url}"' for url in download_urls)
    return "\n".join(
        [
            "RUN set -eux; \\",
            '    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \\',
            '    case "$arch" in \\',
            f'      amd64) checksum="{checksums["amd64"]}" ;; \\',
            f'      arm64) checksum="{checksums["arm64"]}" ;; \\',
            '      *) echo "Unsupported architecture: $arch" >&2; exit 1 ;; \\',
            "    esac; \\",
            f'    asset="{asset_name}"; \\',
            "    downloaded=0; \\",
            f"    for base_url in {quoted_download_urls}; do \\",
            (
                "      if curl -fLSs --connect-timeout 10 --max-time 180 "
                '--retry 1 --retry-delay 1 -o "/tmp/${asset}" \\'
            ),
            f'        "${{base_url}}/v{version}/${{asset}}"; then downloaded=1; break; fi; \\',
            "    done; \\",
            '    test "$downloaded" = 1; \\',
            '    echo "${checksum}  /tmp/${asset}" | sha256sum -c -; \\',
            f'    tar -xzf "/tmp/${{asset}}" -C /tmp "{archive_member}"; \\',
            f'    install -m 0755 "{install_source}" "/usr/local/bin/{binary_name}"; \\',
            f'    rm -rf "/tmp/${{asset}}" "{cleanup_source}"',
        ]
    )


def _github_release_urls(cloud_provider: str, repository: str) -> list[str]:
    official = f"https://github.com/{repository}/releases/download"
    mirror = f"https://ghfast.top/{official}"
    return [mirror, official] if cloud_provider == "volcengine" else [official, mirror]


def render_cloud_environment_dockerfile(draft: AgentDraft) -> str | None:
    """Render the custom image or an AgentKit-compatible image for selected CLIs."""
    if draft.cloudEnvironment.resolvedImage:
        return "\n".join(
            [
                f"FROM {draft.cloudEnvironment.resolvedImage}",
                "",
                "# The selected environment already contains VeADK and runtime dependencies.",
                "# Keep the application layer limited to user-authored Agent code.",
                "WORKDIR /app",
                "COPY . .",
                "EXPOSE 8000",
                'CMD ["python", "-m", "app"]',
                "",
            ]
        )
    if draft.cloudEnvironment.dockerfile is not None:
        return draft.cloudEnvironment.dockerfile

    selected = set(draft.cloudEnvironment.cliTools)
    if not selected and not draft.dynamicAgentDelegation:
        return None

    system_packages = ["ca-certificates", "curl"]
    if "github-cli" in selected:
        system_packages.append("git")
    if "pandoc" in selected:
        system_packages.append("pandoc")
    blocks = [
        f"FROM {_AGENTKIT_BASE_IMAGES[draft.cloudProvider]}",
        "",
        "# Configure AgentKit runtime defaults.",
        "ENV UV_SYSTEM_PYTHON=1 UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 DOCKER_CONTAINER=1",
        "ARG TARGETARCH",
        "",
        "# Install system dependencies required by the selected tools.",
        (
            "RUN apt-get update && apt-get install -y --no-install-recommends "
            f"{' '.join(system_packages)} && rm -rf /var/lib/apt/lists/*"
        ),
    ]
    if "lark-cli" in selected:
        blocks.extend(
            [
                "",
                "# Install Lark CLI from the official release archive.",
                _render_cli_install(
                    asset_name=(f"lark-cli-{_LARK_CLI_VERSION}-linux-${{arch}}.tar.gz"),
                    version=_LARK_CLI_VERSION,
                    checksums=_LARK_CLI_SHA256,
                    download_urls=_github_release_urls(
                        draft.cloudProvider,
                        "larksuite/cli",
                    ),
                    archive_member="lark-cli",
                    install_source="/tmp/lark-cli",
                    cleanup_source="/tmp/lark-cli",
                    binary_name="lark-cli",
                ),
            ]
        )
    if "github-cli" in selected:
        blocks.extend(
            [
                "",
                "# Install GitHub CLI (gh) from the official release archive.",
                _render_cli_install(
                    asset_name=f"gh_{_GITHUB_CLI_VERSION}_linux_${{arch}}.tar.gz",
                    version=_GITHUB_CLI_VERSION,
                    checksums=_GITHUB_CLI_SHA256,
                    download_urls=_github_release_urls(
                        draft.cloudProvider,
                        "cli/cli",
                    ),
                    archive_member=(f"gh_{_GITHUB_CLI_VERSION}_linux_${{arch}}/bin/gh"),
                    install_source=(
                        f"/tmp/gh_{_GITHUB_CLI_VERSION}_linux_${{arch}}/bin/gh"
                    ),
                    cleanup_source=(f"/tmp/gh_{_GITHUB_CLI_VERSION}_linux_${{arch}}"),
                    binary_name="gh",
                ),
            ]
        )
    blocks.extend(
        [
            "",
            "# Install Python dependencies before copying the source for better layer caching.",
            "COPY requirements.txt requirements.txt",
            (
                "RUN uv pip install -r requirements.txt || \\\n"
                f"    uv pip install --index-url {_PYPI_FALLBACK_INDEX} "
                "-r requirements.txt"
            ),
            "",
            "# Copy the Agent application and configure its runtime entrypoint.",
            "EXPOSE 8000",
            "",
            "WORKDIR /app",
            "COPY . .",
            "",
            'CMD ["python", "-m", "app"]',
            "",
        ]
    )
    return "\n".join(blocks)


def generate_project_from_draft(draft: AgentDraft) -> GeneratedProject:
    if draft.agentType == "a2a":
        raise ValueError("Remote Agent cannot be the root Agent.")

    draft = _normalize_harness_sidecar_draft(draft)
    draft = prepare_mcp_auth(draft)
    pkg = ident(draft.name, "my_agent")
    harness_sidecar_enabled = bool(
        draft.harnessSidecar and draft.harnessSidecar.enabled
    )
    managed_mcp_gateway = bool(
        harness_sidecar_enabled
        and draft.harnessSidecar
        and draft.harnessSidecar.componentOverrides.get("mcp_resilience")
    )
    acc = _Acc(
        draft.cloudProvider,
        managed_mcp_gateway=managed_mcp_gateway,
    )
    acc.environment_skills = list(draft.cloudEnvironment.environmentSkills)
    feishu_channel_enabled = bool(draft.deployment.feishuEnabled)
    if feishu_channel_enabled:
        acc.env.extend(
            [
                EnvVar(
                    "FEISHU_APP_ID",
                    False,
                    "cli_xxx",
                    "飞书机器人 App ID（前端部署时填写）",
                ),
                EnvVar(
                    "FEISHU_APP_SECRET",
                    False,
                    "your-feishu-app-secret",
                    "飞书机器人 App Secret（前端部署时填写）",
                ),
            ]
        )
    if harness_sidecar_enabled:
        acc.extras.add("harness-sidecar")
        for key, value in studio_harness_env_example(draft.harnessSidecar).items():
            acc.env.append(
                EnvVar(
                    key,
                    False,
                    value,
                    "Harness Sidecar 公有运行配置",
                )
            )

    _build_agent(acc, draft, "agent")
    if harness_sidecar_enabled:
        _add_import(acc, "from google.adk.apps.app import App")
        _add_import(acc, "from veadk.extensions.harness import HarnessExtension")
    if acc.managed_mcp_http_count:
        _add_import(acc, "import os")
        _add_import(
            acc,
            "from veadk.extensions.harness.sidecar_runtime.mcp_client import "
            "managed_mcp_http_client_factory",
        )
        acc.env.extend(
            [
                EnvVar(
                    "MCP_URLS",
                    True,
                    "https://example.com/mcp",
                    "MCP upstream URLs, separated by commas",
                ),
                EnvVar(
                    "MCP_API_KEY",
                    True,
                    "replace-with-your-mcp-api-key",
                    "Shared MCP upstream API key",
                ),
            ]
        )

    import_block = "\n".join(["from veadk import Agent", *_dedupe_imports(acc.imports)])
    harness_bootstrap = ""
    managed_mcp_bootstrap = ""
    if harness_sidecar_enabled:
        harness_bootstrap = "harness_extension = HarnessExtension.from_env()\n"
    if acc.managed_mcp_http_count:
        managed_mcp_bootstrap = (
            "\n_managed_mcp_urls = [\n"
            '    value.strip() for value in os.environ.get("MCP_URLS", "").split(",")\n'
            "    if value.strip()\n"
            "]\n"
            f"if len(_managed_mcp_urls) != {acc.managed_mcp_http_count}:\n"
            '    raise RuntimeError("Harness Sidecar MCP gateway endpoint count does not match configured HTTP MCP tools")\n'
            '_managed_mcp_api_key = os.environ.get("MCP_API_KEY", "").strip()\n'
            "if not _managed_mcp_api_key:\n"
            '    raise RuntimeError("Harness Sidecar MCP gateway API key is missing")\n'
            "\n"
            "def _managed_mcp_connection(index: int):\n"
            "    return StreamableHTTPConnectionParams(\n"
            "        url=_managed_mcp_urls[index],\n"
            '        headers={"Authorization": f"Bearer {_managed_mcp_api_key}"},\n'
            "        timeout=30.0,\n"
            "        sse_read_timeout=300.0,\n"
            "        httpx_client_factory=managed_mcp_http_client_factory,\n"
            "    )\n"
        )
    harness_definition = ""
    if harness_sidecar_enabled:
        harness_definition = (
            "\n"
            "app = App(\n"
            '    name=__package__.split(".")[-1],\n'
            "    root_agent=root_agent,\n"
            "    plugins=harness_extension.plugins(),\n"
            ")\n"
        )
    agent_definition = (
        harness_bootstrap
        + managed_mcp_bootstrap
        + ("\n" if harness_bootstrap or managed_mcp_bootstrap else "")
        + "\n\n".join(acc.pre_lines)
        + f"\n\nAGENT_DISPLAY_NAMES = {acc.agent_display_names!r}\n"
        + f"AGENT_DRAFT = {_safe_draft_payload(draft)!r}\n"
        + "\n# ADK 加载器要求：顶层 agent 必须命名为 root_agent\nroot_agent = agent\n"
        + harness_definition
    )
    agent_py = f"{_PYTHON_LICENSE_HEADER}\n{import_block}\n\n{agent_definition}"

    app_py = _render_app_py(
        pkg,
        feishu_channel_enabled,
        harness_sidecar_enabled,
    )
    files = [
        GeneratedFile(path="app.py", content=app_py),
        # Top-level agents package marker so `from agents.<pkg>.agent import
        # root_agent` resolves when the container runs `python -m app`.
        GeneratedFile(path="agents/__init__.py", content=_PYTHON_LICENSE_HEADER),
        GeneratedFile(path=f"agents/{pkg}/agent.py", content=agent_py),
        GeneratedFile(
            path=f"agents/{pkg}/__init__.py",
            content=(
                f"{_PYTHON_LICENSE_HEADER}\n"
                "from .agent import AGENT_DISPLAY_NAMES, AGENT_DRAFT, root_agent\n\n"
                '__all__ = ["AGENT_DISPLAY_NAMES", "AGENT_DRAFT", "root_agent"]\n'
            ),
        ),
        GeneratedFile(
            path=f"agents/{pkg}/dynamic_a2a.py",
            content=_render_dynamic_a2a_py(),
        ),
        GeneratedFile(
            path=".env.example",
            content=render_env_example(
                _materialize_a2a_registry_env(_dedupe_env(acc.env), draft)
            ),
        ),
        GeneratedFile(
            path="requirements.txt",
            content=render_requirements(
                acc.extras,
                feishu_channel_enabled,
                dynamic_agent_delegation=draft.dynamicAgentDelegation,
            ),
        ),
        GeneratedFile(path="README.md", content=render_readme(pkg, draft)),
    ]
    if draft.dynamicAgentDelegation:
        files.insert(
            4,
            GeneratedFile(
                path=f"agents/{pkg}/quick_mode_compat.py",
                content=_render_quick_mode_compat_py(),
            ),
        )
    dockerfile = render_cloud_environment_dockerfile(draft)
    if dockerfile is not None:
        files.append(GeneratedFile(path="Dockerfile", content=dockerfile))
    if harness_sidecar_enabled:
        files.insert(
            1, GeneratedFile(path="main.py", content=_render_managed_main_py())
        )
    return GeneratedProject(name=pkg, files=files)


def _normalize_harness_sidecar_draft(draft: AgentDraft) -> AgentDraft:
    for sub_agent in draft.subAgents:
        if sub_agent.harnessSidecar and sub_agent.harnessSidecar.enabled:
            raise ValueError("Harness Sidecar can only be configured on the root Agent")
    if not draft.harnessSidecar:
        return draft
    intent = normalize_studio_harness_intent(draft.harnessSidecar)
    if not intent.enabled:
        return draft.model_copy(update={"harnessSidecar": None})
    metadata = studio_harness_intent_payload(intent)
    metadata.pop("catalogVersion", None)
    metadata.pop("planHash", None)
    normalized = HarnessSidecarIntent.model_validate(metadata)
    return draft.model_copy(update={"harnessSidecar": normalized})
