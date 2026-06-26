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

import asyncio
from types import SimpleNamespace

from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

from veadk.extensions.harness.plugins import (
    HarnessCompressPlugin,
    HarnessInvocationContextPlugin,
    HarnessLongRunControlPlugin,
    HarnessResponseVerificationPlugin,
    build_harness_plugins,
)
from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
    FinalResponseVerifierConfig,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    ToolResultCompactor,
    ToolResultCompactorConfig,
)
from veadk.extensions.harness.stores import InMemoryHarnessStore


def _callback_context():
    return SimpleNamespace(
        session=SimpleNamespace(id="s1", app_name="app", user_id="u1"),
        user_id="u1",
        invocation_id="r1",
        user_content=types.Content(
            role="user", parts=[types.Part(text="Create a report")]
        ),
    )


def _tool_context():
    return SimpleNamespace(
        session=SimpleNamespace(id="s1", app_name="app", user_id="u1"),
        user_id="u1",
        invocation_id="r1",
    )


def test_context_plugin_appends_system_instruction():
    plugin = HarnessInvocationContextPlugin(store=InMemoryHarnessStore())
    request = LlmRequest(
        contents=[
            types.Content(role="user", parts=[types.Part(text="Create a report")])
        ]
    )

    asyncio.run(
        plugin.before_model_callback(
            callback_context=_callback_context(),
            llm_request=request,
        )
    )

    assert "[Harness Context]" in str(request.config.system_instruction)


def test_compress_plugin_replaces_large_tool_result():
    plugin = HarnessCompressPlugin(
        compressor=ToolResultCompactor(
            ToolResultCompactorConfig(max_tool_result_chars=1000)
        ),
        store=InMemoryHarnessStore(),
    )

    result = asyncio.run(
        plugin.after_tool_callback(
            tool=SimpleNamespace(name="query_data"),
            tool_args={},
            tool_context=_tool_context(),
            result={"rows": "x" * 8000},
        )
    )

    assert result is not None
    assert result["harness_compressed"] is True
    assert plugin.compaction_reports
    assert plugin.compaction_reports[0].compressed_chars < 8000


def test_compress_plugin_compacts_model_context_function_responses():
    plugin = HarnessCompressPlugin(
        compactor=ToolResultCompactor(
            ToolResultCompactorConfig(max_tool_result_chars=1000)
        ),
        store=InMemoryHarnessStore(),
    )
    request = LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name="run_code",
                        response={
                            "result": (
                                '[{"name":"candidate-b","score":88},'
                                '{"stage":"trace","payload":"' + ("x" * 8000) + '"}]'
                            )
                        },
                    )
                ],
            )
        ]
    )

    asyncio.run(
        plugin.before_model_callback(
            callback_context=_callback_context(),
            llm_request=request,
        )
    )

    response = request.contents[0].parts[0].function_response.response
    summary = str(response["summary"])
    assert response["harness_compressed"] is True
    assert "name=candidate-b" in summary
    assert "score=88" in summary
    assert "payload=<text chars=8000>" in summary
    assert "x" * 100 not in summary
    assert plugin.compaction_reports


def test_compress_plugin_resets_diagnostics():
    plugin = HarnessCompressPlugin(
        compactor=ToolResultCompactor(
            ToolResultCompactorConfig(max_tool_result_chars=1000)
        ),
        store=InMemoryHarnessStore(),
    )

    asyncio.run(
        plugin.after_tool_callback(
            tool=SimpleNamespace(name="query_data"),
            tool_args={},
            tool_context=_tool_context(),
            result={"rows": "x" * 8000},
        )
    )
    plugin.reset_diagnostics()

    assert plugin.compaction_reports == []


def test_response_verification_plugin_blocks_unsupported_completion_claim():
    store = InMemoryHarnessStore()
    plugin = HarnessResponseVerificationPlugin(
        verifier=FinalResponseVerifier(FinalResponseVerifierConfig(mode="block")),
        store=store,
    )
    response = LlmResponse(
        content=types.Content(
            role="model", parts=[types.Part(text="Done, I created it.")]
        )
    )

    blocked = asyncio.run(
        plugin.after_model_callback(
            callback_context=_callback_context(),
            llm_response=response,
        )
    )

    assert blocked is not None
    assert "cannot verify" in blocked.content.parts[0].text


def test_response_verification_plugin_accepts_string_tool_result():
    plugin = HarnessResponseVerificationPlugin(store=InMemoryHarnessStore())

    result = asyncio.run(
        plugin.after_tool_callback(
            tool=SimpleNamespace(name="run_code"),
            tool_args={},
            tool_context=_tool_context(),
            result="chain_1=abc123",
        )
    )

    assert result is None


def test_build_harness_plugins_uses_shared_store_and_aliases():
    plugins = build_harness_plugins(components="context,compress,verifier")

    assert [plugin.name for plugin in plugins] == [
        "harness_invocation_context_plugin",
        "harness_compress_plugin",
        "harness_response_verification_plugin",
    ]


def test_build_harness_plugins_accepts_long_run_control_alias():
    plugins = build_harness_plugins(
        components="context_engine,compressor,verifier,long_run_control"
    )

    assert [plugin.name for plugin in plugins] == [
        "harness_invocation_context_plugin",
        "harness_compress_plugin",
        "harness_response_verification_plugin",
        "harness_long_run_control_plugin",
    ]


def test_long_run_control_injects_guidance_after_threshold():
    plugin = HarnessLongRunControlPlugin(
        store=InMemoryHarnessStore(),
        trigger_after_model_calls=2,
    )
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="Create a chart")])]
    )

    asyncio.run(
        plugin.before_model_callback(
            callback_context=_callback_context(),
            llm_request=request,
        )
    )
    assert "Harness Long Run Control" not in str(request.config.system_instruction)

    asyncio.run(
        plugin.before_model_callback(
            callback_context=_callback_context(),
            llm_request=request,
        )
    )

    instruction = request.config.system_instruction
    assert isinstance(instruction, str)
    assert "[Harness Long Run Control]" in instruction
    assert "model_calls_so_far: 2" in instruction
    assert "generated artifacts" in instruction
