from attr import dataclass
from google.adk.agents.invocation_context import InvocationContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse


@dataclass
class LLMAttributesParams:
    invocation_context: InvocationContext
    event_id: str
    llm_request: LlmRequest
    llm_response: LlmResponse


def llm_gen_ai_request_model(params: LLMAttributesParams) -> str:
    return params.llm_request.model or "<unknown_model_name>"


def llm_gen_ai_request_type(params: LLMAttributesParams) -> str | list[str]:
    type = "completion"
    return type or "<unknown_type>"


def llm_gen_ai_response_model(params: LLMAttributesParams) -> str:
    return params.llm_request.model or "<unknown_model_name>"


def llm_gen_ai_request_max_tokens(params: LLMAttributesParams) -> int | None:
    return params.llm_request.config.max_output_tokens


def llm_gen_ai_request_temperature(params: LLMAttributesParams) -> float | None:
    return params.llm_request.config.temperature


def llm_gen_ai_request_top_p(params: LLMAttributesParams) -> float | None:
    return params.llm_request.config.top_p


def llm_gen_ai_prompt(params: LLMAttributesParams) -> list[dict]:
    ret = []
    for idx, content in enumerate(params.llm_request.contents):
        if content.parts:
            role = content.role
            parts = [part for part in content.parts if not part.inline_data]
        ret.append({f".{idx}.role": role, f".{idx}.content": str(parts)})
    return ret


def llm_gen_ai_completion(params: LLMAttributesParams) -> list[dict] | None:
    ret = []

    content = params.llm_response.content
    if content and content.parts:
        parts = [part for part in content.parts if not part.inline_data]
        ret.append({f".{0}.role": content.role, f".{0}.content": str(parts)})
        return ret


def llm_gen_ai_response_stop_reason(params: LLMAttributesParams) -> str | None:
    return params.llm_response.stop_reason


def llm_gen_ai_response_finish_reason(params: LLMAttributesParams) -> str | None:
    return params.llm_response.finish_reason
