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

from opentelemetry import context as context_api

OVERRIDE_ENABLE_CONTENT_TRACING = "override_enable_content_tracing"
TRACE_CONTENT_ENV_VAR = "OBSERVABILITY_OPENTELEMETRY_TRACE_CONTENT"


def should_trace_content() -> bool:
    """Return whether prompt/completion/tool content should be added to spans."""
    from veadk.config import settings

    trace_content = settings.opentelemetry_config.trace_content
    # VeADK flattens config.yaml into environment variables during startup.
    # Reading the env var here keeps system/.env/config.yaml override behavior
    # aligned with other config fields, and also supports runtime test overrides.
    trace_content = os.getenv(TRACE_CONTENT_ENV_VAR, str(trace_content))
    return str(trace_content).lower() == "true" or bool(
        context_api.get_value(OVERRIDE_ENABLE_CONTENT_TRACING)
    )
