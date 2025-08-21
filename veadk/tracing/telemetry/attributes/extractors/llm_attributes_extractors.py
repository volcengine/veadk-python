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
    return "<no_stop_reason_provided>"


def llm_gen_ai_response_finish_reason(params: LLMAttributesParams) -> str | None:
    # TODO: update to google-adk v1.12.0
    return None


def llm_gen_ai_usage_input_tokens(params: LLMAttributesParams) -> int | None:
    if params.llm_response.usage_metadata:
        return params.llm_response.usage_metadata.prompt_token_count
    return None


def llm_gen_ai_usage_output_tokens(params: LLMAttributesParams) -> int | None:
    if params.llm_response.usage_metadata:
        return params.llm_response.usage_metadata.candidates_token_count
    return None


def llm_gen_ai_usage_total_tokens(params: LLMAttributesParams) -> int | None:
    if params.llm_response.usage_metadata:
        return params.llm_response.usage_metadata.total_token_count
    return None


def llm_gen_ai_usage_cache_creation_input_tokens(
    params: LLMAttributesParams,
) -> int | None:
    if params.llm_response.usage_metadata:
        return None
        # return params.llm_response.usage_metadata.cached_content_token_count
    return None


def llm_gen_ai_usage_cache_read_input_tokens(params: LLMAttributesParams) -> int | None:
    if params.llm_response.usage_metadata:
        return None
        # return params.llm_response.usage_metadata.prompt_token_count
    return None


def llm_gen_ai_is_streaming(params: LLMAttributesParams) -> bool | None:
    # return params.llm_request.stream
    return None


LLM_ATTRIBUTES = {
    "gen_ai.request.model": llm_gen_ai_request_model,
    "gen_ai.request.type": llm_gen_ai_request_type,
    "gen_ai.response.model": llm_gen_ai_response_model,
    "gen_ai.request.max_tokens": llm_gen_ai_request_max_tokens,
    "gen_ai.request.temperature": llm_gen_ai_request_temperature,
    "gen_ai.request.top_p": llm_gen_ai_request_top_p,
    "gen_ai.prompt": llm_gen_ai_prompt,
    "gen_ai.completion": llm_gen_ai_completion,
    "gen_ai.response.stop_reason": llm_gen_ai_response_stop_reason,
    "gen_ai.response.finish_reason": llm_gen_ai_response_finish_reason,
    "gen_ai.usage.input_tokens": llm_gen_ai_usage_input_tokens,
    "gen_ai.usage.output_tokens": llm_gen_ai_usage_output_tokens,
    "gen_ai.usage.total_tokens": llm_gen_ai_usage_total_tokens,
    "gen_ai.usage.cache_creation_input_tokens": llm_gen_ai_usage_cache_creation_input_tokens,
    "gen_ai.usage.cache_read_input_tokens": llm_gen_ai_usage_cache_read_input_tokens,
    "gen_ai.is_streaming": llm_gen_ai_is_streaming,
}
