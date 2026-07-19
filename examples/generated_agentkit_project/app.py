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

from agents.customer_support.agent import AGENT_DISPLAY_NAMES, root_agent
from veadk.integrations.agentkit import create_agentkit_app, run_agentkit_app

app = create_agentkit_app(
    root_agent,
    AGENT_DISPLAY_NAMES,
    enable_feishu=False,
)

if __name__ == "__main__":
    run_agentkit_app(app)
