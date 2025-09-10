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

import os
from functools import cached_property

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from veadk.auth.veauth.apmplus_veauth import APMPlusVeAuth
from veadk.consts import (
    DEFAULT_APMPLUS_OTEL_EXPORTER_ENDPOINT,
    DEFAULT_APMPLUS_OTEL_EXPORTER_SERVICE_NAME,
    DEFAULT_COZELOOP_OTEL_EXPORTER_ENDPOINT,
    DEFAULT_TLS_OTEL_EXPORTER_ENDPOINT,
    DEFAULT_TLS_OTEL_EXPORTER_REGION,
)
from veadk.integrations.ve_tls.ve_tls import VeTLS


class APMPlusConfig(BaseSettings):
    otel_exporter_endpoint: str = Field(
        default=DEFAULT_APMPLUS_OTEL_EXPORTER_ENDPOINT,
        alias="OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT",
    )

    otel_exporter_service_name: str = Field(
        default=DEFAULT_APMPLUS_OTEL_EXPORTER_SERVICE_NAME,
        alias="OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME",
    )

    @cached_property
    def otel_exporter_api_key(self) -> str:
        return (
            os.getenv("OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY")
            or APMPlusVeAuth().token
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


class TLSConfig(BaseSettings):
    otel_exporter_endpoint: str = Field(
        default=DEFAULT_TLS_OTEL_EXPORTER_ENDPOINT,
        alias="OBSERVABILITY_OPENTELEMETRY_TLS_ENDPOINT",
    )

    otel_exporter_region: str = Field(
        default=DEFAULT_TLS_OTEL_EXPORTER_REGION,
        alias="OBSERVABILITY_OPENTELEMETRY_TLS_REGION",
    )

    @cached_property
    def otel_exporter_topic_id(self) -> str:
        _topic_id = (
            os.getenv("OBSERVABILITY_OPENTELEMETRY_TLS_SERVICE_NAME")
            or VeTLS().get_trace_topic_id()
        )
        return _topic_id


class PrometheusConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OBSERVABILITY_PROMETHEUS_")

    pushgateway_url: str = ""

    pushgateway_username: str = ""

    pushgateway_password: str = ""
