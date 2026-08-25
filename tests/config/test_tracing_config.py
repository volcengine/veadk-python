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

from veadk.configs.tracing_configs import APMPlusConfig


def test_apmplus_endpoint_defaults_to_volcengine_region(monkeypatch):
    monkeypatch.delenv("AGENTKIT_CLOUD_PROVIDER", raising=False)
    monkeypatch.delenv("CLOUD_PROVIDER", raising=False)
    monkeypatch.delenv("REGION", raising=False)
    monkeypatch.delenv("OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT", raising=False)

    assert (
        APMPlusConfig().otel_exporter_endpoint
        == "http://apmplus-cn-beijing.volces.com:4317"
    )


def test_apmplus_endpoint_defaults_to_byteplus_region(monkeypatch):
    monkeypatch.delenv("AGENTKIT_CLOUD_PROVIDER", raising=False)
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.delenv("BYTEPLUS_REGION", raising=False)
    monkeypatch.delenv("OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT", raising=False)

    assert (
        APMPlusConfig().otel_exporter_endpoint
        == "http://apmplus-ap-southeast-1.volces.com:4317"
    )


def test_apmplus_endpoint_environment_override_takes_precedence(monkeypatch):
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv(
        "OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT",
        "http://custom-apmplus.example.com:4317",
    )

    assert (
        APMPlusConfig().otel_exporter_endpoint
        == "http://custom-apmplus.example.com:4317"
    )
