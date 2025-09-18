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
