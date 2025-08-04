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

from config import AGENT, APP_NAME, SHORT_TERM_MEMORY, TRACERS

from veadk.a2a.ve_a2a_server import init_app

SERVER_HOST = os.getenv("SERVER_HOST")

AGENT.tracers = TRACERS

app = init_app(
    server_url=SERVER_HOST,
    app_name=APP_NAME,
    agent=AGENT,
    short_term_memory=SHORT_TERM_MEMORY,
)
