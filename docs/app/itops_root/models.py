from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types as genai_types

class MockPlannerLlm(BaseLlm):
    """A mock planner LLM that routes to sub-agents based on keywords."""

    async def generate_content_async(self, llm_request, stream: bool = False):
        user_queries: list[str] = []
        for content in llm_request.contents:
            if content.role == "user":
                for part in content.parts or []:
                    if getattr(part, "text", None):
                        user_queries.append(part.text)
        query = user_queries[-1] if user_queries else ""

        function_calls = []
        if "网络" in query or "network" in query:
            function_calls.append(
                genai_types.FunctionCall(
                    name="network_agent",
                    args={"prompt": query}
                )
            )
        if "服务器" in query or "主机" in query or "host" in query:
             function_calls.append(
                genai_types.FunctionCall(
                    name="host_agent",
                    args={"prompt": query}
                )
            )
        if "应用" in query or "app" in query:
             function_calls.append(
                genai_types.FunctionCall(
                    name="app_agent",
                    args={"prompt": query}
                )
            )
        if "安全" in query or "sec" in query:
             function_calls.append(
                genai_types.FunctionCall(
                    name="sec_agent",
                    args={"prompt": query}
                )
            )

        if function_calls:
            parts = [genai_types.Part(function_call=call) for call in function_calls]
            response_content = genai_types.Content(
                role="model",
                parts=parts,
            )
        else:
            text = f"抱歉，无法理解您的问题 '{query}'。请说明问题属于 网络/主机/应用/安全 中的哪一类。"
            response_content = genai_types.Content(
                role="model",
                parts=[genai_types.Part.from_text(text=text)],
            )

        yield LlmResponse(content=response_content)

class MockSubAgentLlm(BaseLlm):
    """A mock sub-agent LLM that provides a canned response."""

    async def generate_content_async(self, llm_request, stream: bool = False):
        # Extract the function call from the request
        function_call = None
        for content in llm_request.contents:
            if content.role == "function":
                function_call = content

        if function_call:
            response_text = f"已收到来自 {function_call.parts[0].function_response.name} 的请求"
        else:
            response_text = "已收到请求"


        response_content = genai_types.Content(
            role="model",
            parts=[genai_types.Part.from_text(text=response_text)],
        )

        yield LlmResponse(content=response_content)
