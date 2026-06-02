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

from types import SimpleNamespace

from veadk.memory.short_term_memory_backends.mysql_backend import MysqlSTMBackend
from veadk.memory.short_term_memory_backends.postgresql_backend import (
    PostgreSqlSTMBackend,
)
from veadk.memory.short_term_memory_backends.sqlite_backend import SQLiteSTMBackend
from veadk.tracing.telemetry.attributes.extractors.tool_attributes_extractors import (
    tool_gen_ai_tool_output,
)
from veadk.tracing.telemetry.attributes.extractors.types import ToolAttributesParams
import veadk.utils.adk_compat as adk_compat


def test_get_previous_interaction_id_missing_field():
    llm_request = SimpleNamespace()
    assert adk_compat.get_previous_interaction_id(llm_request) is None


def test_get_previous_interaction_id_with_field():
    llm_request = SimpleNamespace(previous_interaction_id="interaction_123")
    assert adk_compat.get_previous_interaction_id(llm_request) == "interaction_123"


def test_get_event_function_calls_from_getter():
    expected_calls = [SimpleNamespace(name="tool_a")]

    class Event:
        def get_function_calls(self):
            return expected_calls

    calls = adk_compat.get_event_function_calls(Event())
    assert calls == expected_calls


def test_get_event_function_calls_fallback_to_parts():
    part1 = SimpleNamespace(function_call=SimpleNamespace(name="tool_1"))
    part2 = SimpleNamespace(function_call=None)
    event = SimpleNamespace(content=SimpleNamespace(parts=[part1, part2]))

    calls = adk_compat.get_event_function_calls(event)
    assert len(calls) == 1
    assert calls[0].name == "tool_1"


def test_get_event_function_calls_getter_error_fallback_to_parts():
    class Event:
        content = SimpleNamespace(
            parts=[SimpleNamespace(function_call="fallback_call")]
        )

        def get_function_calls(self):
            raise RuntimeError("broken getter")

    calls = adk_compat.get_event_function_calls(Event())
    assert calls == ["fallback_call"]


def test_get_event_function_responses_fallback_to_parts():
    part = SimpleNamespace(function_response=SimpleNamespace(name="tool_resp"))
    event = SimpleNamespace(content=SimpleNamespace(parts=[part]))

    responses = adk_compat.get_event_function_responses(event)
    assert len(responses) == 1
    assert responses[0].name == "tool_resp"


def test_mysql_backend_url_respects_async_driver_flag(monkeypatch):
    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.mysql_backend.should_use_async_db_drivers",
        lambda: True,
    )
    backend = MysqlSTMBackend()
    assert backend._db_url.startswith("mysql+aiomysql://")

    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.mysql_backend.should_use_async_db_drivers",
        lambda: False,
    )
    backend = MysqlSTMBackend()
    assert backend._db_url.startswith("mysql+pymysql://")


def test_postgresql_backend_url_respects_async_driver_flag(monkeypatch):
    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.postgresql_backend.should_use_async_db_drivers",
        lambda: True,
    )
    backend = PostgreSqlSTMBackend()
    assert backend._db_url.startswith("postgresql+asyncpg://")

    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.postgresql_backend.should_use_async_db_drivers",
        lambda: False,
    )
    backend = PostgreSqlSTMBackend()
    assert backend._db_url.startswith("postgresql://")


def test_sqlite_backend_url_respects_async_driver_flag(monkeypatch, tmp_path):
    db_file = tmp_path / "compat-test.db"

    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.sqlite_backend.should_use_async_db_drivers",
        lambda: True,
    )
    backend = SQLiteSTMBackend(local_path=str(db_file))
    assert backend._db_url.startswith("sqlite+aiosqlite:///")

    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.sqlite_backend.should_use_async_db_drivers",
        lambda: False,
    )
    backend = SQLiteSTMBackend(local_path=str(db_file))
    assert backend._db_url.startswith("sqlite:///")


def test_tool_output_extractor_accepts_dict_response():
    function_response_event = SimpleNamespace(
        content=SimpleNamespace(
            parts=[
                SimpleNamespace(
                    function_response={
                        "id": "id_1",
                        "name": "tool_name",
                        "response": {"ok": True},
                    }
                )
            ]
        )
    )
    params = ToolAttributesParams(
        tool=SimpleNamespace(name="tool_name"),
        args={},
        function_response_event=function_response_event,
    )

    response = tool_gen_ai_tool_output(params)
    assert '"name": "tool_name"' in response.content


def test_tool_output_extractor_accepts_object_response():
    function_response_event = SimpleNamespace(
        content=SimpleNamespace(
            parts=[
                SimpleNamespace(
                    function_response=SimpleNamespace(
                        id="id_2",
                        name="tool_obj",
                        response={"status": "done"},
                    )
                )
            ]
        )
    )
    params = ToolAttributesParams(
        tool=SimpleNamespace(name="tool_obj"),
        args={},
        function_response_event=function_response_event,
    )

    response = tool_gen_ai_tool_output(params)
    assert '"name": "tool_obj"' in response.content
