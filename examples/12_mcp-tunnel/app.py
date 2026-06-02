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

"""Cloud side: the ADK agent server + tunnel routes, in one process.

`mount_tunnel_if_enabled` adds the tunnel routes only because `ops_agent` has
`enable_tunnel=True`. The connector token comes from `TUNNEL_TOKEN`.
Run: `python app.py` (then run a connector from the enterprise side).
"""

import os
import sys
from pathlib import Path

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

from veadk.tunnel import mount_tunnel_if_enabled

AGENTS_DIR = str(Path(__file__).resolve().parent / "agents")
sys.path.insert(0, AGENTS_DIR)
from ops_agent.agent import root_agent  # noqa: E402

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

app = get_fast_api_app(agents_dir=AGENTS_DIR, web=False)

# Mounts /tunnel/* only if some agent enabled the tunnel. The token is the
# tunnel-layer auth a connector must present.
mount_tunnel_if_enabled(app, agents=[root_agent], token=os.getenv("TUNNEL_TOKEN"))


@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
