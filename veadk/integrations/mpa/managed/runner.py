"""Fixed Studio child-process entry point; never forward SDK logs to the UI."""

import asyncio
import json
import sys

from .config import load_profile, with_creation_images
from .service import provision
from .diagnostics import classify_error, diagnostic_scope, report


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
    except Exception as error:
        report("provision", classify_error(error))
        # Error text can contain SDK request payloads, URLs and credentials.
        emit(error="creationFailed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
