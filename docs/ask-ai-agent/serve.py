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

"""Serve the docs assistant as an A2A application (local dev + VeFaaS).

The deployed VeFaaS function (via `veadk deploy`) serves the same A2A protocol,
so the docs frontend talks to one protocol everywhere. CORS is enabled so the
static docs site can call this endpoint cross-origin.

    python serve.py            # http://localhost:8000
"""

import os

# Load .env before importing the agent so model credentials are picked up.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from starlette.middleware.cors import CORSMiddleware

from veadk.a2a.utils.agent_to_a2a import to_a2a

from agent import agent

HOST = os.getenv("ASK_AI_HOST", "0.0.0.0")
PORT = int(os.getenv("ASK_AI_PORT", os.getenv("PORT", "8000")))
# Comma-separated allowed origins for the browser (docs site). "*" by default.
ALLOW_ORIGINS = [
    o.strip() for o in os.getenv("ASK_AI_ALLOW_ORIGINS", "*").split(",") if o.strip()
]

app = to_a2a(agent, host=HOST, port=PORT)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
