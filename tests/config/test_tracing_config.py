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

import pytest
from pydantic import ValidationError

from veadk.configs.tracing_configs import APMPlusConfig, OpenTelemetryConfig


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


def test_inmemory_defaults_and_environment_overrides(monkeypatch):
    for key in ("ENABLED", "MAX_SPANS", "MAX_BYTES"):
        monkeypatch.delenv(f"OBSERVABILITY_OPENTELEMETRY_INMEMORY_{key}", raising=False)
    defaults = OpenTelemetryConfig()
    assert defaults.inmemory_enabled is True
    assert defaults.inmemory_max_spans == 1024
    assert defaults.inmemory_max_bytes == 16 * 1024 * 1024
    monkeypatch.setenv("OBSERVABILITY_OPENTELEMETRY_INMEMORY_ENABLED", "false")
    monkeypatch.setenv("OBSERVABILITY_OPENTELEMETRY_INMEMORY_MAX_SPANS", "12")
    monkeypatch.setenv("OBSERVABILITY_OPENTELEMETRY_INMEMORY_MAX_BYTES", "8192")
    config = OpenTelemetryConfig()
    assert config.inmemory_enabled is False
    assert config.inmemory_max_spans == 12
    assert config.inmemory_max_bytes == 8192


@pytest.mark.parametrize("key", ["MAX_SPANS", "MAX_BYTES"])
@pytest.mark.parametrize("value", ["-1", "invalid", "1.5"])
def test_inmemory_invalid_limits_fail_configuration(monkeypatch, key, value):
    monkeypatch.setenv(f"OBSERVABILITY_OPENTELEMETRY_INMEMORY_{key}", value)
    with pytest.raises(ValidationError):
        OpenTelemetryConfig()


def test_inmemory_zero_limits_are_valid(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_OPENTELEMETRY_INMEMORY_MAX_SPANS", "0")
    monkeypatch.setenv("OBSERVABILITY_OPENTELEMETRY_INMEMORY_MAX_BYTES", "0")
    config = OpenTelemetryConfig()
    assert config.inmemory_max_spans == config.inmemory_max_bytes == 0


@pytest.mark.parametrize(
    "explicit,tenant,expected",
    [
        (" explicit ", "tenant", "explicit"),
        ("", " tenant ", "tenant"),
        ("  ", "  ", "automatic"),
    ],
)
def test_apmplus_key_precedence_and_cache(monkeypatch, explicit, tenant, expected):
    from unittest.mock import Mock

    lookup = Mock(return_value="automatic")
    monkeypatch.setenv("OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY", explicit)
    monkeypatch.setenv("TENANT_APMPLUS_APPKEY", tenant)
    monkeypatch.setattr("veadk.configs.tracing_configs.get_apmplus_token", lookup)
    config = APMPlusConfig()
    lookup.assert_not_called()
    assert config.otel_exporter_api_key == expected
    assert config.otel_exporter_api_key == expected
    assert lookup.call_count == (1 if expected == "automatic" else 0)


def test_apmplus_failed_lookup_can_retry(monkeypatch):
    from unittest.mock import Mock

    monkeypatch.delenv("OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY", raising=False)
    monkeypatch.delenv("TENANT_APMPLUS_APPKEY", raising=False)
    lookup = Mock(side_effect=[RuntimeError("unavailable"), "recovered"])
    monkeypatch.setattr("veadk.configs.tracing_configs.get_apmplus_token", lookup)
    config = APMPlusConfig()
    with pytest.raises(RuntimeError):
        _ = config.otel_exporter_api_key
    assert config.otel_exporter_api_key == "recovered"
    assert lookup.call_count == 2
