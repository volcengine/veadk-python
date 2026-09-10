"""Serve the remote sandbox agent through AgentKit's HTTP/SSE APIs."""

import argparse

from pathlib import Path

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    from agent import root_agent
    from agentkit.apps import AgentkitAgentServerApp

    server = AgentkitAgentServerApp(agent=root_agent)
    server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
