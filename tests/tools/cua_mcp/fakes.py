"""Cloud-free platform contract fixtures for the installed MCP distribution."""

from datetime import datetime, timedelta, timezone

from agentkit_cua_mcp.service import CuaError


class Platform:
    def __init__(self):
        self.sessions = {}
        self.created = 0
        self.fail = False
        self.envs = [{"Key": "ENABLE_COMPUTER", "Value": "true"}]

    async def request(self, action, body):
        if self.fail:
            raise CuaError("PLATFORM_UNAVAILABLE")
        if action == "GetTool":
            return {"ToolId": "t-example", "Status": "Ready", "Envs": self.envs}
        if action == "ListSessions":
            assert body["Filters"] == [
                {"Name": "UserSessionId", "Values": [body["Filters"][0]["Values"][0]]}
            ]
            return {"SessionInfos": list(self.sessions.values())}
        if action == "CreateSession":
            self.created += 1
            sid = f"s-{self.created}"
            self.sessions[sid] = {
                "SessionId": sid,
                "UserSessionId": body["UserSessionId"],
                "Status": "Ready",
                "Endpoint": "https://sandbox.example.test",
                "ExpireAt": (
                    datetime.now(timezone.utc) + timedelta(minutes=20)
                ).isoformat(),
            }
            return self.sessions[sid]
        if action == "GetSession":
            if body["SessionId"] not in self.sessions:
                raise CuaError("SESSION_NOT_FOUND")
            return self.sessions[body["SessionId"]]
        raise AssertionError(action)


class Desktop:
    enabled = True
    ready = True
    called = []

    def __init__(self, endpoint):
        self.endpoint = endpoint

    async def computer_capability(self):
        return {
            "enabled": self.enabled,
            "ready": self.ready,
            "state": "disabled"
            if not self.enabled
            else ("ready" if self.ready else "starting"),
            "features": [],
        }

    async def call(self, name, arguments):
        self.called.append((name, arguments))
        return {"success": True}
