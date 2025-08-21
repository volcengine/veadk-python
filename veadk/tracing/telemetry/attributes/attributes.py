from veadk.tracing.telemetry.attributes.extractors.common_attributes_extractors import (
    common_gen_ai_app_name,
    common_gen_ai_session_id,
    common_gen_ai_system,
    common_gen_ai_system_version,
    common_gen_ai_user_id,
)
from veadk.tracing.telemetry.attributes.extractors.llm_attributes_extrators import (
    LLM_ATTRIBUTES,
)

ATTRIBUTES = {
    "common": {
        "gen_ai.system": common_gen_ai_system,
        "gen_ai.system_version": common_gen_ai_system_version,
        "gen_ai.app.name": common_gen_ai_app_name,
        "gen_ai.user.id": common_gen_ai_user_id,
        "gen_ai.session.id": common_gen_ai_session_id,
    },
    "llm": LLM_ATTRIBUTES,
    "tool": ...,
}
