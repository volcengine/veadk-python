from veadk.version import VERSION


def common_gen_ai_system(**kwargs) -> str:
    return "veadk"


def common_gen_ai_system_version(**kwargs) -> str:
    return VERSION


def common_gen_ai_app_name(**kwargs) -> str:
    app_name = kwargs.get("app_name")
    return app_name or "<unknown_app_name>"


def common_gen_ai_agent_name(**kwargs) -> str:
    agent_name = kwargs.get("agent_name")
    return agent_name or "<unknown_agent_name>"


def common_gen_ai_user_id(**kwargs) -> str:
    user_id = kwargs.get("user_id")
    return user_id or "<unknown_user_id>"


def common_gen_ai_session_id(**kwargs) -> str:
    session_id = kwargs.get("session_id")
    return session_id or "<unknown_session_id>"


COMMON_ATTRIBUTES = {
    "gen_ai.system": common_gen_ai_system,
    "gen_ai.system.version": common_gen_ai_system_version,
    "gen_ai.app.name": common_gen_ai_app_name,
    "gen_ai.agent.name": common_gen_ai_agent_name,
    "gen_ai.user.id": common_gen_ai_user_id,
    "gen_ai.session.id": common_gen_ai_session_id,
}
