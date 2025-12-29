# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from veadk.version import VERSION


def common_gen_ai_system(**kwargs) -> str:
    """Extract the generative AI system provider name.

    This field identifies the model provider and will be parsed as `model_provider`
    in Volcengine CozeLoop platform for system categorization and analysis.

    Args:
        **kwargs: Keyword arguments containing context information.
            Expected to include 'model_provider' key.

    Returns:
        str: Model provider name or placeholder if not available
    """
    model_provider = kwargs.get("model_provider")
    return model_provider or "<unknown_model_provider>"


def common_gen_ai_system_version(**kwargs) -> str:
    """Extract the VeADK system version.

    Provides version information for the VeADK framework being used,
    enabling version-specific analysis and compatibility tracking.

    Args:
        **kwargs: Keyword arguments (unused in this extractor)

    Returns:
        str: Current VeADK version string
    """
    return VERSION


def common_gen_ai_app_name(**kwargs) -> str:
    """Extract the application name from context.

    Provides application-level identification for organizing and
    filtering telemetry data by application or service.

    Args:
        **kwargs: Keyword arguments containing context information.
            Expected to include 'app_name' key.

    Returns:
        str: Application name or placeholder if not available
    """
    app_name = kwargs.get("app_name")
    return app_name or "<unknown_app_name>"


def common_gen_ai_agent_name(**kwargs) -> str:
    """Extract the agent name from context.

    Provides agent-level identification for organizing telemetry data
    by specific agent instances within an application.

    Args:
        **kwargs: Keyword arguments containing context information.
            Expected to include 'agent_name' key.

    Returns:
        str: Agent name or placeholder if not available
    """
    agent_name = kwargs.get("agent_name")
    return agent_name or "<unknown_agent_name>"


def common_gen_ai_user_id(**kwargs) -> str:
    """Extract the user identifier from context.

    Provides user-level identification for organizing telemetry data
    by user sessions and enabling user-specific analytics.

    Args:
        **kwargs: Keyword arguments containing context information.
            Expected to include 'user_id' key.

    Returns:
        str: User identifier or placeholder if not available
    """
    user_id = kwargs.get("user_id")
    return user_id or "<unknown_user_id>"


def common_gen_ai_session_id(**kwargs) -> str:
    """Extract the session identifier from context.

    Provides session-level identification for organizing telemetry data
    by conversation sessions and enabling session-based analysis.

    Args:
        **kwargs: Keyword arguments containing context information.
            Expected to include 'session_id' key.

    Returns:
        str: Session identifier or placeholder if not available
    """
    session_id = kwargs.get("session_id")
    return session_id or "<unknown_session_id>"


def common_gen_ai_invocation_id(**kwargs) -> str:
    """Extract the invocation identifier from context.

    Provides invocation-level identification for organizing telemetry data
    by individual API calls and enabling detailed analysis of each operation.

    Args:
        **kwargs: Keyword arguments containing context information.
            Expected to include 'invocation_id' key.

    Returns:
        str: Invocation identifier or placeholder if not available
    """
    invocation_id = kwargs.get("invocation_id")
    return invocation_id or "<unknown_invocation_id>"


def common_cozeloop_report_source(**kwargs) -> str:
    """Extract the CozeLoop report source identifier.

    Provides a fixed identifier indicating that telemetry data originated
    from the VeADK framework for CozeLoop platform integration.

    Args:
        **kwargs: Keyword arguments (unused in this extractor)

    Returns:
        str: Always returns "veadk" as the report source
    """
    return "veadk"


def common_cozeloop_call_type(**kwargs) -> str:
    """Extract the CozeLoop call type from context.

    Provides call type classification for CozeLoop platform analysis,
    enabling categorization of different operation types.

    Args:
        **kwargs: Keyword arguments containing context information.
            Expected to include 'call_type' key.

    Returns:
        str: Call type identifier or None if not available
    """
    return kwargs.get("call_type")


def llm_openinference_instrumentation_veadk(**kwargs) -> str:
    """Extract the OpenInference instrumentation version for VeADK.

    Provides instrumentation version information following OpenInference
    standards for telemetry framework identification.

    Args:
        **kwargs: Keyword arguments (unused in this extractor)

    Returns:
        str: Current VeADK version as instrumentation identifier
    """
    return VERSION


COMMON_ATTRIBUTES = {
    "gen_ai.system": common_gen_ai_system,
    "gen_ai.system.version": common_gen_ai_system_version,
    "gen_ai.agent.name": common_gen_ai_agent_name,
    "openinference.instrumentation.veadk": llm_openinference_instrumentation_veadk,
    "gen_ai.app.name": common_gen_ai_app_name,  # APMPlus required
    "gen_ai.user.id": common_gen_ai_user_id,  # APMPlus required
    "gen_ai.session.id": common_gen_ai_session_id,  # APMPlus required
    "agent_name": common_gen_ai_agent_name,  # CozeLoop required
    "agent.name": common_gen_ai_agent_name,  # TLS required
    "app_name": common_gen_ai_app_name,  # CozeLoop required
    "app.name": common_gen_ai_app_name,  # TLS required
    "user.id": common_gen_ai_user_id,  # CozeLoop / TLS required
    "session.id": common_gen_ai_session_id,  # CozeLoop / TLS required
    "invocation.id": common_gen_ai_invocation_id,  # CozeLoop required
    "cozeloop.report.source": common_cozeloop_report_source,  # CozeLoop required
    "cozeloop.call_type": common_cozeloop_call_type,  # CozeLoop required
}
