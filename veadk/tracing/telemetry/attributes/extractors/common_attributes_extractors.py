from veadk.version import VERSION


def common_gen_ai_system() -> str:
    return "veadk"


def common_gen_ai_system_version() -> str:
    return VERSION


def common_gen_ai_app_name(**kwargs) -> str:
    return kwargs.get("app_name", "<unknown_app_name>")


def common_gen_ai_user_id(**kwargs) -> str:
    return kwargs.get("user_id", "")


def common_gen_ai_session_id(**kwargs) -> str:
    return kwargs.get("session_id", "<unknown_session_id>")
