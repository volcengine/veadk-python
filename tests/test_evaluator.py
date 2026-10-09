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

import json
import os

from veadk.evaluation.base_evaluator import BaseEvaluator

EVAL_SET_DATA = {
    "eval_set_id": "home_automation_agent_light_on_off_set",
    "name": "",
    "description": "This is an eval set that is used for unit testing `x` behavior of the Agent",
    "eval_cases": [
        {
            "eval_id": "eval_case_id",
            "conversation": [
                {
                    "invocation_id": "b7982664-0ab6-47cc-ab13-326656afdf75",  # Unique identifier for the invocation.
                    "user_content": {  # Content provided by the user in this invocation. This is the query.
                        "parts": [{"text": "Turn off device_2 in the Bedroom."}],
                        "role": "user",
                    },
                    "final_response": {  # Final response from the agent that acts as a reference of benchmark.
                        "parts": [{"text": "I have set the device_2 status to off."}],
                        "role": "model",
                    },
                    "intermediate_data": {
                        "tool_uses": [  # Tool use trajectory in chronological order.
                            {
                                "args": {
                                    "location": "Bedroom",
                                    "device_id": "device_2",
                                    "status": "OFF",
                                },
                                "name": "set_device_info",
                            }
                        ],
                        "intermediate_responses": [],  # Any intermediate sub-agent responses.
                    },
                }
            ],
            "session_input": {  # Initial session input.
                "app_name": "home_automation_agent",
                "user_id": "test_user",
                "state": {},
            },
        }
    ],
}

TRACE_SET_DATA = [
    {
        "name": "execute_tool get_city_weather",
        "span_id": 4497348974122733469,
        "trace_id": 142655176138954930885272077198014871976,
        "start_time": 1758158957162250000,
        "end_time": 1758158957162426000,
        "attributes": {
            "gen_ai.tool.name": "get_city_weather",
            "gen_ai.tool.input": '{"name": "get_city_weather", "description": "Retrieves the weather information of a given city. the args must in English", "parameters": {"city": "Beijing"}}',
            "gen_ai.tool.output": '{"id": "call_w4bj25flpvs74zgyyiquqh5s", "name": "get_city_weather", "response": {"result": "Sunny, 25°C"}}',
        },
        "parent_span_id": 574819447039686650,
    },
    {
        "name": "call_llm",
        "span_id": 574819447039686650,
        "trace_id": 142655176138954930885272077198014871976,
        "start_time": 1758158945807630000,
        "end_time": 1758158957171304000,
        "attributes": {
            "gen_ai.app.name": "veadk_default_app",
            "gen_ai.user.id": "veadk_default_user",
            "gen_ai.prompt.0.role": "user",
            "gen_ai.prompt.0.content": "How is the weather like in BeiJing?",
        },
        "parent_span_id": 13789664766018020416,
    },
    {
        "name": "call_llm",
        "span_id": 9007934154052797946,
        "trace_id": 142655176138954930885272077198014871976,
        "start_time": 1758158957171713000,
        "end_time": 1758158964035230000,
        "attributes": {
            "gen_ai.app.name": "veadk_default_app",
            "gen_ai.user.id": "veadk_default_user",
            "gen_ai.prompt.0.content": "How is the weather like in BeiJing?",
            "gen_ai.completion.0.content": "The weather in Beijing is sunny with a temperature of 25°C.",
        },
        "parent_span_id": 13789664766018020416,
    },
    {
        "name": "agent_run [chat_robot]",
        "span_id": 13789664766018020416,
        "trace_id": 142655176138954930885272077198014871976,
        "start_time": 1758158945807350000,
        "end_time": 1758158964035291000,
        "attributes": {},
        "parent_span_id": 5589459087402275636,
    },
    {
        "name": "invocation",
        "span_id": 5589459087402275636,
        "trace_id": 142655176138954930885272077198014871976,
        "start_time": 1758158945807233000,
        "end_time": 1758158964035304000,
        "attributes": {},
        "parent_span_id": None,
    },
]


MULTI_TRACE_SET_DATA = [
    # Trace A (app_a / user_a). Spans are deliberately NOT ordered by
    # start_time: the second call_llm span comes first in the file to
    # exercise the start_time sorting fix (issue #1021).
    {
        "name": "call_llm",
        "span_id": 2001,
        "trace_id": 11111111111111111111111111111111,
        "start_time": 1758158957171713000,
        "end_time": 1758158964035230000,
        "attributes": {
            "gen_ai.app.name": "app_a",
            "gen_ai.user.id": "user_a",
            "gen_ai.prompt.0.content": "follow-up A",
            "gen_ai.completion.0.content": "response A",
        },
        "parent_span_id": 1000,
    },
    {
        "name": "execute_tool get_city_weather",
        "span_id": 2002,
        "trace_id": 11111111111111111111111111111111,
        "start_time": 1758158957162250000,
        "end_time": 1758158957162426000,
        "attributes": {
            "gen_ai.tool.name": "get_city_weather",
            "gen_ai.tool.input": '{"name": "get_city_weather", "parameters": {"city": "Beijing"}}',
            "gen_ai.tool.output": '{"id": "call_w4bj25flpvs74zgyyiquqh5s", "name": "get_city_weather", "response": {"result": "Sunny, 25°C"}}',
        },
        "parent_span_id": 1000,
    },
    {
        "name": "call_llm",
        "span_id": 1001,
        "trace_id": 11111111111111111111111111111111,
        "start_time": 1758158945807630000,
        "end_time": 1758158957171304000,
        "attributes": {
            "gen_ai.app.name": "app_a",
            "gen_ai.user.id": "user_a",
            "gen_ai.prompt.0.role": "user",
            "gen_ai.prompt.0.content": "hello A",
        },
        "parent_span_id": 1000,
    },
    {
        "name": "invocation",
        "span_id": 1000,
        "trace_id": 11111111111111111111111111111111,
        "start_time": 1758158945807233000,
        "end_time": 1758158964035304000,
        "attributes": {},
        "parent_span_id": None,
    },
    # Trace B (app_b / user_b): single call_llm span, no tool uses.
    {
        "name": "call_llm",
        "span_id": 3001,
        "trace_id": 22222222222222222222222222222222,
        "start_time": 1758159045807630000,
        "end_time": 1758159047171304000,
        "attributes": {
            "gen_ai.app.name": "app_b",
            "gen_ai.user.id": "user_b",
            "gen_ai.prompt.0.content": "hello B",
            "gen_ai.completion.0.content": "response B",
        },
        "parent_span_id": 3000,
    },
    {
        "name": "invocation",
        "span_id": 3000,
        "trace_id": 22222222222222222222222222222222,
        "start_time": 1758159045807233000,
        "end_time": 1758159047171304000,
        "attributes": {},
        "parent_span_id": None,
    },
]


def test_evaluator():
    base_evaluator = BaseEvaluator(agent=None, name="test_evaluator")

    # save data to file
    eval_set_file_path = "./eval_set_for_test_evaluator.json"
    with open(eval_set_file_path, "w") as f:
        json.dump(EVAL_SET_DATA, f)

    base_evaluator.build_eval_set(file_path=eval_set_file_path)

    assert len(base_evaluator.invocation_list) == 1
    assert len(base_evaluator.invocation_list[0].invocations) == 1
    assert (
        base_evaluator.invocation_list[0].invocations[0].invocation_id
        == "b7982664-0ab6-47cc-ab13-326656afdf75"
    )

    os.remove(eval_set_file_path)


def test_tracing_file_to_evalset():
    base_evaluator = BaseEvaluator(agent=None, name="test_evaluator")

    # save data to file
    tracing_file_path = "./tracing_for_test_evaluator.json"
    with open(tracing_file_path, "w") as f:
        json.dump(TRACE_SET_DATA, f)

    base_evaluator.build_eval_set(file_path=tracing_file_path)

    assert len(base_evaluator.invocation_list) == 1
    assert len(base_evaluator.invocation_list[0].invocations) == 1
    assert (
        base_evaluator.invocation_list[0].invocations[0].expected_output
        == "The weather in Beijing is sunny with a temperature of 25°C."
    )

    os.remove(tracing_file_path)


def test_tracing_file_multiple_traces_to_evalset():
    """Regression test for #1021: multi-trace files must not collapse into one
    eval case.

    Each trace_id must produce one isolated EvalCase, spans must be ordered by
    start_time within a trace, and conversation/tool uses/session metadata must
    never cross trace boundaries.
    """
    base_evaluator = BaseEvaluator(agent=None, name="test_evaluator")

    tracing_file_path = "./tracing_for_test_evaluator_multiple_traces.json"
    with open(tracing_file_path, "w") as f:
        json.dump(MULTI_TRACE_SET_DATA, f)

    base_evaluator.build_eval_set(file_path=tracing_file_path)

    # Two traces -> two isolated eval cases
    assert len(base_evaluator.invocation_list) == 2
    assert len(base_evaluator.agent_information_list) == 2

    # First case: trace A metadata and conversation, spans were out of order
    first_case = base_evaluator.invocation_list[0]
    assert base_evaluator.agent_information_list[0]["app_name"] == "app_a"
    assert base_evaluator.agent_information_list[0]["user_id"] == "user_a"
    assert len(first_case.invocations) == 1
    assert first_case.invocations[0].input == "hello A"
    assert first_case.invocations[0].expected_output == "response A"
    assert first_case.invocations[0].expected_tool == [
        {"name": "get_city_weather", "args": {"city": "Beijing"}}
    ]

    # Second case: trace B metadata and conversation
    second_case = base_evaluator.invocation_list[1]
    assert base_evaluator.agent_information_list[1]["app_name"] == "app_b"
    assert base_evaluator.agent_information_list[1]["user_id"] == "user_b"
    assert len(second_case.invocations) == 1
    assert second_case.invocations[0].input == "hello B"
    assert second_case.invocations[0].expected_output == "response B"
    assert second_case.invocations[0].expected_tool == []

    os.remove(tracing_file_path)
