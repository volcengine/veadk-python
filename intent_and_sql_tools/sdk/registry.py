class ToolRegistry:
    _intent_map: dict[str, str] = {}

    @classmethod
    def register(cls, intent: str, tool_name: str):
        def decorator(func):
            cls._intent_map[intent] = tool_name
            return func

        return decorator

    @classmethod
    def get_tool_name(cls, intent: str) -> str:
        return cls._intent_map.get(intent, "unknown_tool")
