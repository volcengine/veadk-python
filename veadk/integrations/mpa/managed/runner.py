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

"""Fixed Studio child-process entry point; never forward SDK logs to the UI."""

import asyncio
import json
import sys

from .config import (
    load_profile,
    with_creation_images,
    with_creation_resources,
    with_creation_tos,
)
from .diagnostics import classify_error, diagnostic_scope, report
from .service import provision


def emit(**event):
    print("MPA_EVENT " + json.dumps(event), flush=True)


def main():
    with diagnostic_scope(lambda diagnostic: emit(diagnostic=diagnostic)):
        return run()


def run():
    try:
        data = json.loads(sys.stdin.read(16384))
        profile = load_profile(data["config"], region=data["region"])
        profile = with_creation_images(profile, data.get("images", {}))
        profile = with_creation_resources(profile, data.get("resources", {}))
        profile = with_creation_tos(profile, data.get("tos", {}))
        result = asyncio.run(
            asyncio.wait_for(
                provision(
                    profile,
                    agent_id=data["agentId"],
                    runtime_name=data.get("name", ""),
                    owner=data["owner"],
                    studio_runtime_owner=data.get("studioRuntimeOwner"),
                    description=data["description"],
                    progress=lambda stage: emit(stage=stage),
                ),
                timeout=profile.managed.timeout_seconds,
            )
        )
        emit(
            result={
                k: result[k]
                for k in (
                    "runtime_id",
                    "skill_space_id",
                    "gateway_id",
                    "agent_id",
                    "region",
                    "state",
                )
            }
        )
        return 0
    except Exception as error:
        report("provision", classify_error(error))
        # Error text can contain SDK request payloads, URLs and credentials.
        emit(error="creationFailed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
