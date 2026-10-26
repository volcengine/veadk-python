"""Run the packaged self-hosted Managed Agents worker or demo."""

import asyncio
from pathlib import Path

from dotenv import load_dotenv


async def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    from veadk.runtime.managed_agents.worker import main as run

    await run()


if __name__ == "__main__":
    asyncio.run(main())
