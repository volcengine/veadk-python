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

"""A remote sandbox agent used directly as the application root."""

import os

from veadk import AgentkitRemoteSandboxAgent

root_agent = AgentkitRemoteSandboxAgent(
    name="remote_sandbox_demo",
    description="执行远端技能、Python、命令或文件操作，并直接报告执行过程和结果。",
    tool_id=os.getenv("AGENTKIT_TOOL_ID"),
    tool_type=os.getenv("AGENTKIT_TOOL_TYPE") or None,
    request_timeout=900,
    expiry_buffer=90,
)
