import os

from dotenv import find_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from yaml import safe_load

from veadk.auth.veauth.apmplus_veauth import APMPlusVeAuth
from veadk.auth.veauth.ark_veauth import ARKVeAuth
from veadk.auth.veauth.base_veauth import veauth
from veadk.auth.veauth.prompt_pilot_veauth import PromptPilotVeAuth
from veadk.auth.veauth.vesearch_veauth import VesearchVeAuth
from veadk.consts import (
    DEFAULT_APMPLUS_OTEL_EXPORTER_ENDPOINT,
    DEFAULT_APMPLUS_OTEL_EXPORTER_SERVICE_NAME,
    DEFAULT_COZELOOP_OTEL_EXPORTER_ENDPOINT,
    DEFAULT_MODEL_AGENT_API_BASE,
    DEFAULT_MODEL_AGENT_NAME,
    DEFAULT_MODEL_AGENT_PROVIDER,
    DEFAULT_TLS_OTEL_EXPORTER_ENDPOINT,
    DEFAULT_TLS_OTEL_EXPORTER_REGION,
    DEFAULT_TOS_BUCKET_NAME,
)
from veadk.integrations.utils import vesource
from veadk.integrations.ve_tls.ve_tls import VeTLS
from veadk.utils.misc import flatten_dict

veadk_environments: dict = {}


def set_envs() -> dict:
    config_yaml_path = find_dotenv(filename="config.yaml", usecwd=True)

    with open(config_yaml_path, "r", encoding="utf-8") as yaml_file:
        config_dict = safe_load(yaml_file)

    flatten_config_dict = flatten_dict(config_dict)

    for k, v in flatten_config_dict.items():
        global veadk_environments

        k = k.upper()
        if k in os.environ:
            veadk_environments[k] = os.environ[k]
            continue
        veadk_environments[k] = str(v)
        os.environ[k] = str(v)

    return config_dict


config_dict = set_envs()


@veauth("api_key", ARKVeAuth)
class ModelConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MODEL_AGENT_")

    name: str = DEFAULT_MODEL_AGENT_NAME
    """Model name for agent reasoning."""

    provider: str = DEFAULT_MODEL_AGENT_PROVIDER
    """Model provider for LiteLLM initialization."""

    api_base: str = DEFAULT_MODEL_AGENT_API_BASE
    """The api base of the model for agent reasoning."""

    api_key: str = ""
    """The api key of the model for agent reasoning."""


@veauth("api_key", PromptPilotVeAuth)
class PromptPilotConfig(BaseModel):
    api_key: str = ""


@veauth("api_key", VesearchVeAuth)
class VeSearchConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOOL_VESEARCH_")

    endpoint: int | str = ""

    api_key: str = ""


class BuiltinToolsConfig(BaseModel):
    vesearch: VeSearchConfig = Field(default_factory=VeSearchConfig)


@veauth("otel_exporter_api_key", APMPlusVeAuth)
class APMPlusConfig(BaseSettings):
    otel_exporter_endpoint: str = Field(
        default=DEFAULT_APMPLUS_OTEL_EXPORTER_ENDPOINT,
        alias="OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT",
    )

    otel_exporter_service_name: str = Field(
        default=DEFAULT_APMPLUS_OTEL_EXPORTER_SERVICE_NAME,
        alias="OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME",
    )

    otel_exporter_api_key: str = Field(
        default="", alias="OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY"
    )


class CozeloopConfig(BaseSettings):
    otel_exporter_endpoint: str = Field(
        default=DEFAULT_COZELOOP_OTEL_EXPORTER_ENDPOINT,
        alias="OBSERVABILITY_OPENTELEMETRY_COZELOOP_ENDPOINT",
    )

    otel_exporter_api_key: str = Field(
        default="", alias="OBSERVABILITY_OPENTELEMETRY_COZELOOP_API_KEY"
    )

    otel_exporter_space_id: str = Field(
        default="", alias="OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME"
    )


@vesource(
    "otel_exporter_topic_id",
    lambda: VeTLS().get_trace_topic_id(),
)
class TLSConfig(BaseSettings):
    otel_exporter_endpoint: str = Field(
        default=DEFAULT_TLS_OTEL_EXPORTER_ENDPOINT,
        alias="OBSERVABILITY_OPENTELEMETRY_TLS_ENDPOINT",
    )

    otel_exporter_region: str = Field(
        default=DEFAULT_TLS_OTEL_EXPORTER_REGION,
        alias="OBSERVABILITY_OPENTELEMETRY_TLS_REGION",
    )

    otel_exporter_topic_id: str = Field(
        default="",
        alias="OBSERVABILITY_OPENTELEMETRY_TLS_SERVICE_NAME",
    )


class VikingKnowledgebaseConfig(BaseModel):
    project: str = "default"
    """User project in Volcengine console web."""

    region: str = "cn-beijing"


class TOSConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_TOS_")

    endpoint: str = "tos-cn-beijing.volces.com"

    region: str = "cn-beijing"

    bucket: str = DEFAULT_TOS_BUCKET_NAME


class OpensearchConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_OPENSEARCH_")

    host: str = ""

    port: int = 9200

    username: str = ""

    password: str = ""


class MysqlConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_MYSQL_")

    host: str = ""

    user: str = ""

    password: str = ""

    database: str = ""

    charset: str = "utf8"


class RedisConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_REDIS_")

    host: str = ""

    port: int = 6379

    password: str = ""

    db: int = 0


class PrometheusConfig(BaseSettings):
    pushgateway_url: str = ""

    pushgateway_username: str = ""

    pushgateway_password: str = ""


class VeADKConfig(BaseModel):
    model_agent: ModelConfig = Field(default_factory=ModelConfig)
    """The model config for agent reasoning."""

    tool: BuiltinToolsConfig = Field(default_factory=BuiltinToolsConfig)
    """Builtin tools config"""

    apmplus_config: APMPlusConfig = Field(default_factory=APMPlusConfig)
    cozeloop_config: CozeloopConfig = Field(default_factory=CozeloopConfig)
    tls_config: TLSConfig = Field(default_factory=TLSConfig)

    prometheus_config: PrometheusConfig = Field(default_factory=PrometheusConfig)

    tos: TOSConfig = Field(default_factory=TOSConfig)

    opensearch: OpensearchConfig = Field(default_factory=OpensearchConfig)
    mysql: MysqlConfig = Field(default_factory=MysqlConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    viking_knowledgebase: VikingKnowledgebaseConfig = Field(
        default_factory=VikingKnowledgebaseConfig
    )


settings = VeADKConfig()
