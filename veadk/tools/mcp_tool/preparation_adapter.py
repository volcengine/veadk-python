"""Observe Agent-owned MCP instances without replacing their lifecycle state."""

from functools import wraps
from types import MethodType

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from veadk.tools.mcp_tool.preparation_tracing import preparation_span
from veadk.tools.mcp_tool.trusted_mcp_toolset import TrustedMcpToolset


def _observe_method(owner, name: str, phase: str) -> None:
    method = getattr(owner, name, None)
    if not isinstance(method, MethodType):
        return
    original = method.__func__
    if getattr(original, "_veadk_preparation_observed", False):
        return

    # Capture the unbound function: deepcopy must rebind to the copied owner,
    # not keep calling the original toolset or its original session manager.
    @wraps(original)
    async def observed(self, *args, **kwargs):
        with preparation_span(phase, self._connection_params):
            return await original(self, *args, **kwargs)

    observed._veadk_preparation_observed = True
    setattr(owner, name, MethodType(observed, owner))


def _is_identity_toolset(toolset) -> bool:
    # Avoid importing optional identity integrations for ordinary tools/Agents.
    if not any(
        cls.__module__ == "veadk.integrations.ve_identity.mcp_toolset"
        for cls in type(toolset).__mro__
    ):
        return False
    from veadk.integrations.ve_identity.mcp_toolset import VeIdentityMcpToolset

    return isinstance(toolset, VeIdentityMcpToolset)


def instrument_mcp_toolsets(toolsets) -> None:
    """Attach preparation observation only to known VeADK-owned instances."""
    for toolset in toolsets:
        # Trusted already observes both boundaries; wrapping again double-counts.
        if isinstance(toolset, TrustedMcpToolset):
            continue
        if not isinstance(toolset, McpToolset) and not _is_identity_toolset(toolset):
            continue
        manager = toolset._mcp_session_manager
        _observe_method(manager, "create_session", "session.acquire")
        _observe_method(toolset, "get_tools", "tools.prepare")
