from __future__ import annotations

from types import SimpleNamespace

import pytest

from veadk.cli.agentkit_session_metadata import (
    SESSION_SCHEMA_VERSION_METADATA_KEY,
    SESSION_WORKLOAD_METADATA_KEY,
    build_create_session_request,
    session_metadata_value,
)


def _dump(request) -> dict[str, object]:
    return request.model_dump(by_alias=True, exclude_none=True)


def test_create_session_request_includes_bounded_extra_metadata() -> None:
    request = build_create_session_request(
        tool_id="tool",
        ttl_seconds=28_800,
        user_session_id="vt-task",
        display_name="Vibe Task",
        username="owner",
        extra_metadata={
            SESSION_WORKLOAD_METADATA_KEY: "vibe-task",
            SESSION_SCHEMA_VERSION_METADATA_KEY: "1",
        },
    )
    payload = _dump(request)
    metadata = {item["Key"]: item["Value"] for item in payload["Metadata"]}
    assert payload["Ttl"] == 28_800
    assert metadata[SESSION_WORKLOAD_METADATA_KEY] == "vibe-task"
    assert metadata[SESSION_SCHEMA_VERSION_METADATA_KEY] == "1"


@pytest.mark.parametrize(
    "metadata",
    [
        {"": "value"},
        {"x" * 65: "value"},
        {"custom": "x" * 257},
        {"Username": "other"},
    ],
)
def test_create_session_request_rejects_unsafe_extra_metadata(metadata) -> None:
    with pytest.raises(ValueError, match="invalid extra Session metadata"):
        build_create_session_request(
            tool_id="tool",
            ttl_seconds=28_800,
            user_session_id="vt-task",
            display_name="Vibe Task",
            extra_metadata=metadata,
        )


def test_session_metadata_value_handles_models_and_dicts() -> None:
    model = SimpleNamespace(
        metadata=[SimpleNamespace(key="custom", value=" value ")]
    )
    mapping = SimpleNamespace(metadata=[{"Key": "custom", "Value": "other"}])
    assert session_metadata_value(model, "custom") == "value"
    assert session_metadata_value(mapping, "custom") == "other"
    assert session_metadata_value(SimpleNamespace(metadata=None), "custom") == ""
