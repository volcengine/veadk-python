"""Extra tool-schema text must not break retention of escaped reader evidence."""

import pytest
from test_native_search_budget import (
    test_native_distinct_searches_stay_within_request_budget as run_scenario,
)
from veadk.context.tool_results import _ContextReader


@pytest.mark.asyncio
@pytest.mark.parametrize("description_bytes", [0, 128, 1024])
async def test_escaped_evidence_retention_with_schema_overhead(
    tmp_path, monkeypatch, description_bytes
):
    original = _ContextReader._get_declaration

    def declare(self):
        value = original(self)
        value.description += "x" * description_bytes
        return value

    monkeypatch.setattr(_ContextReader, "_get_declaration", declare)
    await run_scenario(tmp_path, escaped=True, parallel=False)
