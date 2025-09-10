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

import time

from veadk.utils.misc import getenv
from veadk.version import VERSION

DEFAULT_AGENT_NAME = "veAgent"

DEFAULT_MODEL_AGENT_NAME = "doubao-seed-1-6-250615"
DEFAULT_MODEL_AGENT_PROVIDER = "openai"
DEFAULT_MODEL_AGENT_API_BASE = "https://ark.cn-beijing.volces.com/api/v3/"
DEFAULT_MODEL_EXTRA_CONFIG = {
    "extra_headers": {
        "x-is-encrypted": getenv("MODEL_AGENT_ENCRYPTED", "true"),
        "veadk-source": "veadk",
        "veadk-version": VERSION,
    },
    "extra_body": {
        "caching": {
            "type": getenv("MODEL_AGENT_CACHING", "enabled"),
        },
        "thinking": {
            "type": "disabled"
        },  # disable thinking for token saving and shorter TTFT by default
        "expire_at": int(time.time()) + 3600,  # expire after 1 hour
    },
}

DEFAULT_APMPLUS_OTEL_EXPORTER_ENDPOINT = "http://apmplus-cn-beijing.volces.com:4317"
DEFAULT_APMPLUS_OTEL_EXPORTER_SERVICE_NAME = "veadk_tracing"

DEFAULT_COZELOOP_OTEL_EXPORTER_ENDPOINT = (
    "https://api.coze.cn/v1/loop/opentelemetry/v1/traces"
)

DEFAULT_TLS_OTEL_EXPORTER_ENDPOINT = "https://tls-cn-beijing.volces.com:4318/v1/traces"
DEFAULT_TLS_OTEL_EXPORTER_REGION = "cn-beijing"

DEFAULT_CR_INSTANCE_NAME = "veadk-user-instance"
DEFAULT_CR_NAMESPACE_NAME = "veadk-user-namespace"
DEFAULT_CR_REPO_NAME = "veadk-user-repo"

DEFAULT_TLS_LOG_PROJECT_NAME = "veadk-logs"
DEFAULT_TLS_TRACING_INSTANCE_NAME = "veadk-tracing"

DEFAULT_TOS_BUCKET_NAME = "veadk-default-bucket"

DEFAULT_COZELOOP_SPACE_NAME = "veadk-space"
