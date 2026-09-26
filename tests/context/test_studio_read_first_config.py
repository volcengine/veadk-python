"""Preserve explicit source checks through generated root and nested Agents."""

import ast
import pytest
from pydantic import ValidationError
from veadk.cli.generated_agent_codegen import AgentDraft, generate_project_from_draft


def policies(draft):
    project = generate_project_from_draft(AgentDraft.model_validate(draft))
    source = next(f.content for f in project.files if f.path.endswith("/agent.py"))
    compile(source, "generated_agent.py", "exec")
    tree = ast.parse(source)
    return {
        ast.literal_eval(
            next(k.value for k in n.keywords if k.arg == "name")
        ): ast.literal_eval(
            next(k.value for k in n.keywords if k.arg == "context_compression")
        )
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "Agent"
    }


@pytest.mark.parametrize("enabled", [True, False])
def test_explicit_choice_reaches_root_and_nested_codegen(enabled):
    values = policies(
        {
            "name": "root",
            "contextCompression": {"mode": "auto", "verify_sources": enabled},
            "subAgents": [
                {
                    "name": "child",
                    "contextCompression": {
                        "mode": "auto",
                        "verify_sources": not enabled,
                    },
                }
            ],
        }
    )
    assert values["root"] == {"mode": "auto", "verify_sources": enabled}
    assert values["child"] == {"mode": "auto", "verify_sources": not enabled}


def test_missing_and_null_do_not_override_sdk_policy_or_legacy_mode():
    assert policies({"name": "legacy"})["legacy"] == {"mode": "auto"}
    for value in ({"mode": "auto"}, {"mode": "auto", "verify_sources": None}):
        assert policies({"name": "fresh", "contextCompression": value})["fresh"] == {
            "mode": "auto"
        }


@pytest.mark.parametrize("value", ["true", "false", 1, 0, [], {}])
def test_invalid_source_check_setting_is_rejected(value):
    with pytest.raises(ValidationError):
        AgentDraft.model_validate(
            {"contextCompression": {"mode": "auto", "verify_sources": value}}
        )
