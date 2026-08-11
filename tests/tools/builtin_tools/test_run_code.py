from types import SimpleNamespace
from unittest.mock import patch

import pytest
from google.adk.tools import FunctionTool

from veadk.tools.builtin_tools.execute_skills import execute_skills
from veadk.tools.builtin_tools import run_code as run_code_module


def _tool_context():
    return SimpleNamespace(
        state={},
        _invocation_context=SimpleNamespace(
            session=SimpleNamespace(id="session-id"),
            agent=SimpleNamespace(name="agent-name"),
            user_id="user-id",
        ),
    )


@pytest.mark.parametrize(
    ("function", "maximum", "range_text"),
    [
        (execute_skills, 900, "between 1 and 900 seconds"),
        (run_code_module.run_code, 300, "between 1 and 300 seconds"),
    ],
)
def test_timeout_is_exposed_in_function_call_declaration(function, maximum, range_text):
    declaration = FunctionTool(function)._get_declaration()

    assert declaration is not None
    assert declaration.parameters_json_schema is not None
    timeout_schema = declaration.parameters_json_schema["properties"]["timeout"]
    assert timeout_schema["default"] == maximum
    assert timeout_schema["type"] == "integer"
    description = " ".join(declaration.description.split())
    assert range_text in description


@pytest.mark.parametrize("timeout", [0, -1, 301, 1.5, True])
def test_run_code_rejects_invalid_timeout(timeout):
    with pytest.raises(
        ValueError,
        match=r"timeout must be an integer between 1 and 300 seconds",
    ):
        run_code_module.run_code(
            "print('hello')",
            "python3",
            _tool_context(),
            timeout=timeout,
        )


@pytest.mark.parametrize("hard_timeout", [0, -1, 301, 1.5, True])
def test_run_code_rejects_invalid_hard_timeout(hard_timeout):
    with pytest.raises(
        ValueError,
        match=r"hard_timeout must be an integer between 1 and 300 seconds",
    ):
        run_code_module.run_code(
            "echo hello",
            "bash",
            _tool_context(),
            hard_timeout=hard_timeout,
        )


def test_run_code_uses_default_timeout_for_python():
    with (
        patch.object(run_code_module, "resolve_agentkit_tool_id", return_value="tool"),
        patch.object(
            run_code_module,
            "get_agentkit_endpoint_config",
            return_value=("service", "region", "host", "https"),
        ),
        patch.object(
            run_code_module,
            "invoke_agentkit_run_code",
            return_value={"Result": {"Result": "ok"}},
        ) as invoke,
    ):
        result = run_code_module.run_code(
            "print('hello')",
            "python3",
            _tool_context(),
        )

    assert result == "ok"
    assert invoke.call_args.kwargs["timeout"] == 300


def test_run_code_forwards_custom_timeouts_for_bash():
    with (
        patch.object(run_code_module, "resolve_agentkit_tool_id", return_value="tool"),
        patch.object(
            run_code_module,
            "get_agentkit_endpoint_config",
            return_value=("service", "region", "host", "https"),
        ),
        patch.object(
            run_code_module,
            "invoke_agentkit_exec_bash",
            return_value={"Result": {"Result": "ok"}},
        ) as invoke,
    ):
        result = run_code_module.run_code(
            "echo hello",
            "bash",
            _tool_context(),
            timeout=120,
            hard_timeout=180,
        )

    assert result == "ok"
    assert invoke.call_args.kwargs["timeout"] == 120
    assert invoke.call_args.kwargs["hard_timeout"] == 180
