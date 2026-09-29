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

import pytest

from veadk.cli import frontend_apmplus_trace as m


@pytest.mark.parametrize("tag", ["mpa.session.id", "gen_ai.session.id"])
@pytest.mark.parametrize("invocation", ["", "i"])
def test_tagged_root_survives_pagination(monkeypatch, tag, invocation):
    root = {
        "trace_id": "t",
        "span_id": "root",
        "operation_name": "mpa.agent.turn",
        "tags": {tag: "s", "mpa.invocation.id": "i"},
    }
    http = {"trace_id": "http", "span_id": "http", "tags": {tag: "s"}}
    other = {
        "trace_id": "other",
        "span_id": "other",
        "tags": {tag: "s", "runtime.id": "other-runtime"},
    }
    offsets = []

    def query(api, req):
        key = req.filters[0].key
        if key.startswith("tags."):
            return [root, http, other] if key == "tags." + tag else []
        assert req.filters[0].values == ["t"]
        offsets.append(req.offset)
        if req.offset == 0:
            return [{"trace_id": "t", "span_id": f"child-{i}"} for i in range(200)]
        return [root, {"trace_id": "wrong", "span_id": "wrong"}]

    monkeypatch.setattr(m, "_list_spans", query)
    rows = m.load_apmplus_trace(
        access_key="ak",
        secret_key="sk",
        session_token="",
        provider="volcengine",
        region="cn-beijing",
        project_name="default",
        runtime_id="r",
        session_id="s",
        invocation_id=invocation,
        now_ms=1800000000000,
        retry_delays=(),
    )
    assert offsets == [0, 200]
    assert len(rows) == 201
    assert rows[0] == root
    assert all(row["trace_id"] == "t" for row in rows)


def test_trace_limit_is_an_error_not_silent_truncation(monkeypatch):
    monkeypatch.setattr(m, "_MAX_TRACE_PAGES", 1)
    root = {"trace_id": "t", "span_id": "root", "tags": {"mpa.session.id": "s"}}
    monkeypatch.setattr(
        m,
        "_list_spans",
        lambda api, req: (
            [root] if req.filters[0].key.startswith("tags.") else [root] * 200
        ),
    )
    with pytest.raises(RuntimeError, match="span limit"):
        m.load_apmplus_trace(
            access_key="ak",
            secret_key="sk",
            session_token="",
            provider="volcengine",
            region="cn-beijing",
            project_name="default",
            runtime_id="r",
            session_id="s",
            now_ms=1800000000000,
            retry_delays=(),
        )
