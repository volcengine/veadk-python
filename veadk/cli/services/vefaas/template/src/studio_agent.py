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
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from veadk.cli.studio.fast_api import get_fast_api_app

path = Path(__file__).parent.resolve()

agent_py_path = os.path.join(path, "agent.py")
if not os.path.exists(agent_py_path):
    raise FileNotFoundError(f"agent.py not found in {path}")

spec = spec_from_file_location("agent", agent_py_path)
if spec is None:
    raise ImportError(f"Could not load spec for agent from {agent_py_path}")

module = module_from_spec(spec)

try:
    spec.loader.exec_module(module)
except Exception as e:
    raise ImportError(f"Failed to execute agent.py: {e}")

agent = None
short_term_memory = None
try:
    agent = module.agent
    short_term_memory = module.short_term_memory
except AttributeError as e:
    missing = str(e).split("'")[1] if "'" in str(e) else "unknown"
    raise AttributeError(f"agent.py is missing required variable: {missing}")

app = get_fast_api_app(agent, short_term_memory)
