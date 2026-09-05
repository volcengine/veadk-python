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

"""Backend catalog for generated-agent project codegen.

Keep this aligned with ``frontend/src/create/veadkCatalog.ts``. The backend is
the trusted codegen source for generated projects and debug runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from veadk.cli.studio_model_catalog import provider_env_placeholders


@dataclass(frozen=True)
class EnvVar:
    key: str
    required: bool
    placeholder: str = ""
    comment: str = ""
    hidden: bool = False


@dataclass(frozen=True)
class ToolOption:
    id: str
    import_line: str
    tool_names: tuple[str, ...]
    env: tuple[EnvVar, ...] = ()
    pip_extra: str = ""


@dataclass(frozen=True)
class BackendOption:
    id: str
    extra_args: str = ""
    env: tuple[EnvVar, ...] = ()
    pip_extra: str = ""


@dataclass(frozen=True)
class ExporterOption:
    id: str
    label: str
    enable_flag: str
    env: tuple[EnvVar, ...] = ()


VOLCENGINE_MODELARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/"
BYTEPLUS_MODELARK_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"
VOLCENGINE_DEFAULT_MODEL_NAME = "doubao-seed-1-6-250615"
BYTEPLUS_DEFAULT_MODEL_NAME = "seed-2-0-lite-260228"
VOLCENGINE_DEFAULT_EMBEDDING_NAME = "doubao-embedding-vision-250615"
BYTEPLUS_DEFAULT_EMBEDDING_NAME = "skylark-embedding-vision-250615"

MODEL_ENV = (
    EnvVar("MODEL_AGENT_NAME", False, VOLCENGINE_DEFAULT_MODEL_NAME, "模型名称"),
    EnvVar("MODEL_AGENT_PROVIDER", False, "openai"),
    EnvVar("MODEL_AGENT_API_BASE", False, VOLCENGINE_MODELARK_BASE_URL),
)

EMBEDDING_ENV = (
    EnvVar(
        "MODEL_EMBEDDING_NAME",
        False,
        VOLCENGINE_DEFAULT_EMBEDDING_NAME,
        "向量化模型（记忆/知识库需要）",
    ),
    EnvVar("MODEL_EMBEDDING_DIM", False, "2048"),
    EnvVar("MODEL_EMBEDDING_API_BASE", False, VOLCENGINE_MODELARK_BASE_URL),
)


def model_env_for_provider(provider: str) -> tuple[EnvVar, ...]:
    """Return base model env placeholders for generated projects."""
    if provider == "byteplus":
        return (
            EnvVar(
                "MODEL_AGENT_NAME",
                False,
                BYTEPLUS_DEFAULT_MODEL_NAME,
                "模型名称",
            ),
            EnvVar("MODEL_AGENT_PROVIDER", False, "openai"),
            EnvVar("MODEL_AGENT_API_BASE", False, BYTEPLUS_MODELARK_BASE_URL),
        )
    return MODEL_ENV


def embedding_env_for_provider(provider: str) -> tuple[EnvVar, ...]:
    """Return embedding env placeholders for generated projects."""
    if provider == "byteplus":
        return (
            EnvVar(
                "MODEL_EMBEDDING_NAME",
                False,
                BYTEPLUS_DEFAULT_EMBEDDING_NAME,
                "向量化模型（记忆/知识库需要）",
            ),
            EnvVar("MODEL_EMBEDDING_DIM", False, "2048"),
            EnvVar("MODEL_EMBEDDING_API_BASE", False, BYTEPLUS_MODELARK_BASE_URL),
        )
    return EMBEDDING_ENV


def env_for_provider(provider: str, env: tuple[EnvVar, ...]) -> tuple[EnvVar, ...]:
    """Return provider-native placeholders for active runtime env specs."""
    provider_id = provider.strip().lower()
    if provider_id != "byteplus":
        return env
    placeholders = provider_env_placeholders(provider_id)
    return tuple(
        EnvVar(
            item.key,
            item.required,
            placeholders.get(item.key, item.placeholder),
            item.comment,
            item.hidden,
        )
        for item in env
    )


# Studio owns the Volcengine credential chain and forwards it to debug runs and
# AgentKit runtimes. Components must not ask users to duplicate AK/SK settings.
VOLC_ENV: tuple[EnvVar, ...] = ()
VIKING_KB_ENV = (
    EnvVar("DATABASE_VIKING_PROJECT", False, "default"),
    EnvVar("DATABASE_VIKING_REGION", False),
    EnvVar("DATABASE_VIKING_COLLECTION_KIND", False),
    EnvVar("DATABASE_VIKING_RESOURCE_ID", False),
)
VIKING_MEMORY_ENV = (
    EnvVar(
        "DATABASE_VIKINGMEM_PROJECT",
        False,
        "default",
        "VikingDB 记忆库项目",
        hidden=True,
    ),
    EnvVar(
        "DATABASE_VIKING_REGION",
        False,
        None,
        "VikingDB 记忆库地域",
        hidden=True,
    ),
    EnvVar(
        "DATABASE_VIKINGMEM_MEMORY_TYPE",
        False,
        "sys_event_v1,sys_profile_v1",
        "记忆类型",
        hidden=True,
    ),
)

A2A_REGISTRY_ENV = (
    EnvVar(
        "REGISTRY_SPACE_ID",
        True,
        "your-agentkit-center-id",
        "AgentKit 智能体中心 ID",
    ),
    EnvVar("REGISTRY_TOP_K", False, "3", "召回 Agent 数量"),
    EnvVar("REGISTRY_REGION", False, "cn-beijing", "AgentKit 智能体中心地域"),
    EnvVar(
        "REGISTRY_ENDPOINT",
        False,
        "https://open.volcengineapi.com/",
        "AgentKit 智能体中心 OpenAPI 地址",
    ),
)


def a2a_registry_env_for_provider(provider: str) -> tuple[EnvVar, ...]:
    """Return provider-native AgentKit A2A registry placeholders."""
    if provider.strip().lower() != "byteplus":
        return A2A_REGISTRY_ENV
    region = "ap-southeast-1"
    replacements = {
        "REGISTRY_REGION": region,
        "REGISTRY_ENDPOINT": f"https://agentkit.{region}.byteplusapi.com/",
    }
    return tuple(
        EnvVar(
            item.key,
            item.required,
            replacements.get(item.key, item.placeholder),
            item.comment,
            item.hidden,
        )
        for item in A2A_REGISTRY_ENV
    )


BUILTIN_TOOLS = (
    ToolOption(
        id="web_search",
        import_line="from veadk.tools.builtin_tools.web_search import web_search",
        tool_names=("web_search",),
        env=VOLC_ENV,
    ),
    ToolOption(
        id="parallel_web_search",
        import_line=(
            "from veadk.tools.builtin_tools.parallel_web_search import "
            "parallel_web_search"
        ),
        tool_names=("parallel_web_search",),
        env=VOLC_ENV,
    ),
    ToolOption(
        id="link_reader",
        import_line="from veadk.tools.builtin_tools.link_reader import link_reader",
        tool_names=("link_reader",),
    ),
    ToolOption(
        id="web_scraper",
        import_line="from veadk.tools.builtin_tools.web_scraper import web_scraper",
        tool_names=("web_scraper",),
        env=(
            EnvVar("TOOL_WEB_SCRAPER_ENDPOINT", True),
            EnvVar("TOOL_WEB_SCRAPER_API_KEY", True),
        ),
    ),
    ToolOption(
        id="image_generate",
        import_line=(
            "from veadk.tools.builtin_tools.image_generate import image_generate"
        ),
        tool_names=("image_generate",),
        env=(EnvVar("MODEL_IMAGE_NAME", False, "doubao-seedream-5-0-260128"),),
    ),
    ToolOption(
        id="image_edit",
        import_line="from veadk.tools.builtin_tools.image_edit import image_edit",
        tool_names=("image_edit",),
        env=(EnvVar("MODEL_EDIT_NAME", False, "doubao-seededit-3-0-i2i-250628"),),
    ),
    ToolOption(
        id="video_generate",
        import_line=(
            "from veadk.tools.builtin_tools.video_generate import "
            "video_generate, video_task_query"
        ),
        tool_names=("video_generate", "video_task_query"),
        env=(EnvVar("MODEL_VIDEO_NAME", False, "doubao-seedance-2-0-260128"),),
    ),
    ToolOption(
        id="text_to_speech",
        import_line="from veadk.tools.builtin_tools.tts import text_to_speech",
        tool_names=("text_to_speech",),
        env=(
            EnvVar("TOOL_VESPEECH_APP_ID", True),
            EnvVar("TOOL_VESPEECH_SPEAKER", False, "zh_female_vv_uranus_bigtts"),
        ),
    ),
    ToolOption(
        id="run_code",
        import_line="from veadk.tools.builtin_tools.run_code import run_code",
        tool_names=("run_code",),
        env=(
            EnvVar("AGENTKIT_TOOL_ID", True, "", "代码执行沙箱 ID"),
            EnvVar("AGENTKIT_TOOL_REGION", False, "cn-beijing", "AgentKit Tools 地域"),
        ),
    ),
    ToolOption(
        id="vesearch",
        import_line="from veadk.tools.builtin_tools.vesearch import vesearch",
        tool_names=("vesearch",),
        env=(EnvVar("TOOL_VESEARCH_ENDPOINT", True, "", "VeSearch bot_id"),),
    ),
)

STM_BACKENDS = (
    BackendOption("local"),
    BackendOption("sqlite", 'local_database_path="./short_term_memory.db"'),
    BackendOption(
        "mysql",
        env=(
            EnvVar("DATABASE_MYSQL_HOST", True),
            EnvVar("DATABASE_MYSQL_USER", True),
            EnvVar("DATABASE_MYSQL_PASSWORD", True),
            EnvVar("DATABASE_MYSQL_DATABASE", True),
        ),
    ),
    BackendOption(
        "postgresql",
        env=(
            EnvVar("DATABASE_POSTGRESQL_HOST", True),
            EnvVar("DATABASE_POSTGRESQL_PORT", False, "5432"),
            EnvVar("DATABASE_POSTGRESQL_USER", True),
            EnvVar("DATABASE_POSTGRESQL_PASSWORD", True),
            EnvVar("DATABASE_POSTGRESQL_DATABASE", True),
        ),
    ),
)

LTM_BACKENDS = (
    BackendOption("local", env=EMBEDDING_ENV, pip_extra="extensions"),
    BackendOption(
        "opensearch",
        env=(
            EnvVar("DATABASE_OPENSEARCH_HOST", True),
            EnvVar("DATABASE_OPENSEARCH_PORT", False, "9200"),
            EnvVar("DATABASE_OPENSEARCH_USERNAME", True),
            EnvVar("DATABASE_OPENSEARCH_PASSWORD", True),
            *EMBEDDING_ENV,
        ),
        pip_extra="extensions",
    ),
    BackendOption(
        "redis",
        env=(
            EnvVar("DATABASE_REDIS_HOST", True),
            EnvVar("DATABASE_REDIS_PORT", False, "6379"),
            EnvVar("DATABASE_REDIS_PASSWORD", False),
            *EMBEDDING_ENV,
        ),
        pip_extra="extensions",
    ),
    BackendOption("viking", env=VIKING_KB_ENV),
    BackendOption(
        "openviking",
        env=(
            EnvVar(
                "DATABASE_OPENVIKING_URL",
                True,
                "https://api.vikingdb.cn-beijing.volces.com/openviking",
                "OpenViking 服务地址",
            ),
            EnvVar(
                "DATABASE_OPENVIKING_API_KEY",
                True,
                "",
                "OpenViking API Key",
            ),
            EnvVar(
                "DATABASE_OPENVIKING_USER_ID",
                False,
                "default",
                "记忆归属 ID；对应 viking://user/<此值>/peers/<请求用户>/memories，"
                "默认 default",
            ),
            EnvVar(
                "DATABASE_OPENVIKING_MEMORY_POLICY",
                False,
                "",
                "记忆策略；不填写时使用官方默认策略，可指定记忆的抽取策略和隔离策略",
            ),
        ),
    ),
    BackendOption(
        "mem0",
        env=(
            EnvVar("DATABASE_MEM0_API_KEY", True),
            EnvVar("DATABASE_MEM0_BASE_URL", False),
        ),
        pip_extra="database",
    ),
)

KB_BACKENDS = (
    BackendOption("local", env=EMBEDDING_ENV, pip_extra="extensions"),
    BackendOption(
        "opensearch",
        env=(
            EnvVar("DATABASE_OPENSEARCH_HOST", True),
            EnvVar("DATABASE_OPENSEARCH_PORT", False, "9200"),
            EnvVar("DATABASE_OPENSEARCH_USERNAME", True),
            EnvVar("DATABASE_OPENSEARCH_PASSWORD", True),
            *EMBEDDING_ENV,
        ),
        pip_extra="extensions",
    ),
    BackendOption("viking", env=VIKING_MEMORY_ENV),
    BackendOption(
        "context_search",
        env=(
            *VOLC_ENV,
            EnvVar("DATABASE_CONTEXT_SEARCH_ENGINE_ID", True),
            EnvVar("DATABASE_CONTEXT_SEARCH_ENGINE_ENDPOINT", True),
            EnvVar("DATABASE_CONTEXT_SEARCH_ENGINE_APIKEY", True),
        ),
    ),
    BackendOption(
        "openviking",
        env=(
            EnvVar(
                "DATABASE_OPENVIKING_URL",
                True,
                "https://api.vikingdb.cn-beijing.volces.com/openviking",
                "OpenViking 服务地址",
            ),
            EnvVar(
                "DATABASE_OPENVIKING_API_KEY",
                True,
                "",
                "OpenViking API Key",
            ),
            EnvVar(
                "DATABASE_OPENVIKING_USER_ID",
                False,
                "default",
                "知识库归属 ID；未配置资源目录时用于默认路径 "
                "viking://user/<此值>/resources/<知识库索引>/，默认 default",
            ),
            EnvVar(
                "DATABASE_OPENVIKING_TARGET_URI",
                False,
                "",
                "知识库资源目录；留空时由 DATABASE_OPENVIKING_USER_ID、 index 自动生成",
            ),
        ),
    ),
)

TRACING_EXPORTERS = (
    ExporterOption(
        "apmplus",
        "APMPlus",
        "ENABLE_APMPLUS",
        (EnvVar("OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME", False),),
    ),
    ExporterOption(
        "cozeloop",
        "CozeLoop",
        "ENABLE_COZELOOP",
        (
            EnvVar("OBSERVABILITY_OPENTELEMETRY_COZELOOP_API_KEY", True),
            EnvVar(
                "OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME",
                False,
                "",
                "CozeLoop space_id",
            ),
        ),
    ),
    ExporterOption(
        "tls",
        "TLS (日志服务)",
        "ENABLE_TLS",
        (
            *VOLC_ENV,
            EnvVar(
                "OBSERVABILITY_OPENTELEMETRY_TLS_SERVICE_NAME",
                False,
                "",
                "TLS topic_id，留空自动创建",
            ),
        ),
    ),
)


TOOL_BY_ID = {tool.id: tool for tool in BUILTIN_TOOLS}
STM_BY_ID = {backend.id: backend for backend in STM_BACKENDS}
LTM_BY_ID = {backend.id: backend for backend in LTM_BACKENDS}
KB_BY_ID = {backend.id: backend for backend in KB_BACKENDS}
EXPORTER_BY_ID = {exporter.id: exporter for exporter in TRACING_EXPORTERS}
