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

"""Public Harness plugin entry points."""

from veadk.extensions.harness.plugins.builder import build_harness_plugins
from veadk.extensions.harness.plugins.compactor import HarnessCompressPlugin
from veadk.extensions.harness.plugins.invocation_context import (
    HarnessInvocationContextPlugin,
)
from veadk.extensions.harness.plugins.long_run_control import (
    HarnessLongRunControlPlugin,
)
from veadk.extensions.harness.plugins.response_verification import (
    HarnessResponseVerificationPlugin,
)

HarnessContextPlugin = HarnessInvocationContextPlugin
HarnessHallucinationPlugin = HarnessResponseVerificationPlugin

__all__ = [
    "HarnessCompressPlugin",
    "HarnessContextPlugin",
    "HarnessHallucinationPlugin",
    "HarnessInvocationContextPlugin",
    "HarnessLongRunControlPlugin",
    "HarnessResponseVerificationPlugin",
    "build_harness_plugins",
]
