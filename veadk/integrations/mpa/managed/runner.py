"""Fixed Studio child-process entry point; never forward SDK logs to the UI."""

import asyncio
import json
import sys

from .config import load_profile
from .service import provision


def emit(**event):
    print("MPA_EVENT " + json.dumps(event), flush=True)


def main():
    try:
        data = json.loads(sys.stdin.read(16384))
        profile = load_profile(data["config"], region=data["region"])
        result = asyncio.run(
            asyncio.wait_for(
                provision(
                    profile,
                    agent_id=data["agentId"],
                    owner=data["owner"],
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
    except Exception:
        # Error text can contain SDK request payloads, URLs and credentials.
        emit(error="creationFailed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
