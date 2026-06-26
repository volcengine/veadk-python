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

"""Tool result compactor module exports."""

from veadk.extensions.harness.modules.tool_result_compactor.builtin_provider import (
    BuiltinCompressionProvider,
)
from veadk.extensions.harness.modules.tool_result_compactor.compactor import (
    ContextCompactionPolicy,
    ContextCompressionPolicy,
    ToolResultCompactor,
    ToolResultCompactorConfig,
    ToolResultCompressor,
    ToolResultCompressorConfig,
)
from veadk.extensions.harness.modules.tool_result_compactor.headroom_provider import (
    HeadroomCompressionProvider,
)

__all__ = [
    "BuiltinCompressionProvider",
    "ContextCompactionPolicy",
    "ContextCompressionPolicy",
    "HeadroomCompressionProvider",
    "ToolResultCompactor",
    "ToolResultCompactorConfig",
    "ToolResultCompressor",
    "ToolResultCompressorConfig",
]
