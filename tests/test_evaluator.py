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
        "span_id": 5421848634094108689,
        "trace_id": 115143748123782151752771111946932434777,
        "start_time": 1754884672226444000,
        "end_time": 1754884672226993000,
        "attributes": {
            "gen_ai.tool.name": "get_city_weather",
            "gen_ai.tool.description": "Retrieves the weather information of a given city. the args must in English",
            "gen_ai.tool.call.id": "call_6ow5622pvcouw3tpvr7rfqtl",
            "gcp.vertex.agent.tool_call_args": '{"city": "Xi\'an"}',
        },
        "parent_span_id": 7997784243558253239,
    },
    {
        "name": "call_llm",
        "span_id": 7997784243558253239,
        "trace_id": 115143748123782151752771111946932434777,
        "attributes": {
            "session.id": "veadk_example_session",
            "user.id": "veadk_default_user",
        },
        "parent_span_id": 14844888006539887900,
    },
    {
        "name": "call_llm",
        "span_id": 7789424022423491416,
        "trace_id": 115143748123782151752771111946932434777,
        "attributes": {
            "session.id": "veadk_example_session",
            "user.id": "veadk_default_user",
        },
        "parent_span_id": 14844888006539887900,
    },
    {
        "name": "agent_run [chat_robot]",
        "span_id": 14844888006539887900,
        "trace_id": 115143748123782151752771111946932434777,
        "attributes": {
            "session.id": "veadk_example_session",
            "user.id": "veadk_default_user",
        },
        "parent_span_id": 2943363177785645047,
    },
    {
        "name": "invocation [veadk_default_app]",
        "span_id": 2943363177785645047,
        "trace_id": 115143748123782151752771111946932434777,
        "start_time": 1754884660687962000,
        "end_time": 1754884676664833000,
        "attributes": {
            "input.value": '{"user_id": "veadk_default_user", "session_id": "veadk_example_session", "new_message": "{\\"parts\\": [{\\"video_metadata\\": null, \\"thought\\": null, \\"inline_data\\": null, \\"file_data\\": null, \\"thought_signature\\": null, \\"code_execution_result\\": null, \\"executable_code\\": null, \\"function_call\\": null, \\"function_response\\": null, \\"text\\": \\"How is the weather like in Xi\'an?\\"}], \\"role\\": \\"user\\"}", "run_config": "{\\"speech_config\\": null, \\"response_modalities\\": null, \\"save_input_blobs_as_artifacts\\": false, \\"support_cfc\\": false, \\"streaming_mode\\": \\"StreamingMode.NONE\\", \\"output_audio_transcription\\": null, \\"input_audio_transcription\\": null, \\"realtime_input_config\\": null, \\"enable_affective_dialog\\": null, \\"proactivity\\": null, \\"max_llm_calls\\": 500}"}',
            "user.id": "veadk_default_user",
            "session.id": "veadk_example_session",
            "output.value": '{"content":{"parts":[{"text":"The weather in Xi\'an is cool, with a temperature of 18\u00b0C."}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":132,"prompt_token_count":547,"total_token_count":679},"invocation_id":"e-ea6bb35b-c3f0-4c5c-b127-c71c7d6d6441","author":"chat_robot","actions":{"state_delta":{},"artifact_delta":{},"requested_auth_configs":{}},"id":"c0929124-9be0-4f75-a6ba-f7a531c9ccb6","timestamp":1754884672.227546}',
        },
        "parent_span_id": None,
    },
]


def test_evaluator():
    base_evaluator = BaseEvaluator(agent=None, name="test_evaluator")

    # save data to file
    eval_set_file_path = "./eval_set_for_test_evaluator.json"
    with open(eval_set_file_path, "w") as f:
        json.dump(EVAL_SET_DATA, f)

    base_evaluator.generate_eval_data(file_path=eval_set_file_path)

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

    base_evaluator.generate_eval_data(file_path=tracing_file_path)

    assert len(base_evaluator.invocation_list) == 1
    assert len(base_evaluator.invocation_list[0].invocations) == 1
    assert (
        base_evaluator.invocation_list[0].invocations[0].invocation_id
        == "e-ea6bb35b-c3f0-4c5c-b127-c71c7d6d6441"
    )

    os.remove(tracing_file_path)
