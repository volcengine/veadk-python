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
            "session.id": "veadk_example_session",
            "user.id": "veadk_default_user",
            "gen_ai.system": "gcp.vertex.agent",
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "get_city_weather",
            "gen_ai.tool.description": "Retrieves the weather information of a given city. the args must in English",
            "gen_ai.tool.call.id": "call_6ow5622pvcouw3tpvr7rfqtl",
            "gcp.vertex.agent.tool_call_args": '{"city": "Xi\'an"}',
            "gcp.vertex.agent.event_id": "afdc4159-10f1-4f94-aa91-1003a9b6f1cc",
            "gcp.vertex.agent.tool_response": '{"result": "Cool, 18\u00b0C"}',
            "gcp.vertex.agent.llm_request": "{}",
            "gcp.vertex.agent.llm_response": "{}",
            "tool.name": "get_city_weather",
            "tool.description": "Retrieves the weather information of a given city. the args must in English",
            "tool.parameters": '{"city": "Xi\'an"}',
            "input.value": '{"city": "Xi\'an"}',
            "input.mime_type": "application/json",
            "output.value": '{"id":"call_6ow5622pvcouw3tpvr7rfqtl","name":"get_city_weather","response":{"result":"Cool, 18\u00b0C"}}',
            "output.mime_type": "application/json",
            "openinference.span.kind": "TOOL",
        },
        "parent_span_id": 7997784243558253239,
    },
    {
        "name": "call_llm",
        "span_id": 7997784243558253239,
        "trace_id": 115143748123782151752771111946932434777,
        "start_time": 1754884660688448000,
        "end_time": 1754884672227098000,
        "attributes": {
            "session.id": "veadk_example_session",
            "user.id": "veadk_default_user",
            "gen_ai.system": "gcp.vertex.agent",
            "gen_ai.request.model": "openai/doubao-seed-1.6-250615",
            "gcp.vertex.agent.invocation_id": "e-ea6bb35b-c3f0-4c5c-b127-c71c7d6d6441",
            "gcp.vertex.agent.session_id": "veadk_example_session",
            "gcp.vertex.agent.event_id": "9e94cb99-9f78-47db-a79c-f5422354953e",
            "gcp.vertex.agent.llm_request": '{"model": "openai/doubao-seed-1.6-250615", "config": {"system_instruction": "Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"", "tools": [{"function_declarations": [{"description": "Retrieves the weather information of a given city. the args must in English", "name": "get_city_weather", "parameters": {"properties": {"city": {"type": "STRING"}}, "required": ["city"], "type": "OBJECT"}}]}], "labels": {"adk_agent_name": "chat_robot"}}, "contents": [{"parts": [{"text": "How is the weather like in Xi\'an?"}], "role": "user"}]}',
            "gcp.vertex.agent.llm_response": '{"content":{"parts":[{"function_call":{"id":"call_6ow5622pvcouw3tpvr7rfqtl","args":{"city":"Xi\'an"},"name":"get_city_weather"}}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":496,"prompt_token_count":487,"total_token_count":983}}',
            "gen_ai.usage.input_tokens": 487,
            "gen_ai.usage.output_tokens": 983,
            "llm.provider": "google",
            "input.value": '{"model": "openai/doubao-seed-1.6-250615", "config": {"system_instruction": "Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"", "tools": [{"function_declarations": [{"description": "Retrieves the weather information of a given city. the args must in English", "name": "get_city_weather", "parameters": {"properties": {"city": {"type": "STRING"}}, "required": ["city"], "type": "OBJECT"}}]}], "labels": {"adk_agent_name": "chat_robot"}}, "contents": [{"parts": [{"text": "How is the weather like in Xi\'an?"}], "role": "user"}]}',
            "input.mime_type": "application/json",
            "llm.tools.0.tool.json_schema": '{"description":"Retrieves the weather information of a given city. the args must in English","name":"get_city_weather","parameters":{"properties":{"city":{"type":"STRING"}},"required":["city"],"type":"OBJECT"}}',
            "llm.model_name": "openai/doubao-seed-1.6-250615",
            "llm.invocation_parameters": '{"system_instruction":"Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"","tools":[{"function_declarations":[{"description":"Retrieves the weather information of a given city. the args must in English","name":"get_city_weather","parameters":{"properties":{"city":{"type":"STRING"}},"required":["city"],"type":"OBJECT"}}]}],"labels":{"adk_agent_name":"chat_robot"}}',
            "llm.input_messages.0.message.role": "system",
            "llm.input_messages.0.message.content": 'Talk with user friendly.\n\nYou are an agent. Your internal name is "chat_robot".\n\n The description about you is "A robot talk with user."',
            "llm.input_messages.1.message.role": "user",
            "llm.input_messages.1.message.contents.0.message_content.text": "How is the weather like in Xi'an?",
            "llm.input_messages.1.message.contents.0.message_content.type": "text",
            "output.value": '{"content":{"parts":[{"function_call":{"id":"call_6ow5622pvcouw3tpvr7rfqtl","args":{"city":"Xi\'an"},"name":"get_city_weather"}}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":496,"prompt_token_count":487,"total_token_count":983}}',
            "output.mime_type": "application/json",
            "llm.token_count.total": 983,
            "llm.token_count.prompt": 487,
            "llm.token_count.completion": 496,
            "llm.output_messages.0.message.role": "model",
            "llm.output_messages.0.message.tool_calls.0.tool_call.id": "call_6ow5622pvcouw3tpvr7rfqtl",
            "llm.output_messages.0.message.tool_calls.0.tool_call.function.name": "get_city_weather",
            "llm.output_messages.0.message.tool_calls.0.tool_call.function.arguments": '{"city": "Xi\'an"}',
            "gen_ai.prompt.0.role": "user",
            "gen_ai.prompt.0.content": '[{"text": "How is the weather like in Xi\'an?"}]',
            "gen_ai.completion.0.role": "model",
            "gen_ai.completion.0.content": '[{"function_call": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "args": {"city": "Xi\'an"}, "name": "get_city_weather"}}]',
            "gen_ai.usage.prompt_tokens": 487,
            "gen_ai.usage.completion_tokens": 496,
            "gen_ai.usage.total_tokens": 983,
            "gen_ai.usage.cache_read_input_tokens": 0,
            "gen_ai.usage.cache_create_input_tokens": 0,
            "openinference.span.kind": "LLM",
        },
        "parent_span_id": 14844888006539887900,
    },
    {
        "name": "call_llm",
        "span_id": 7789424022423491416,
        "trace_id": 115143748123782151752771111946932434777,
        "start_time": 1754884672227703000,
        "end_time": 1754884676664423000,
        "attributes": {
            "session.id": "veadk_example_session",
            "user.id": "veadk_default_user",
            "gen_ai.system": "gcp.vertex.agent",
            "gen_ai.request.model": "openai/doubao-seed-1.6-250615",
            "gcp.vertex.agent.invocation_id": "e-ea6bb35b-c3f0-4c5c-b127-c71c7d6d6441",
            "gcp.vertex.agent.session_id": "veadk_example_session",
            "gcp.vertex.agent.event_id": "c0929124-9be0-4f75-a6ba-f7a531c9ccb6",
            "gcp.vertex.agent.llm_request": '{"model": "openai/doubao-seed-1.6-250615", "config": {"system_instruction": "Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"", "tools": [{"function_declarations": [{"description": "Retrieves the weather information of a given city. the args must in English", "name": "get_city_weather", "parameters": {"properties": {"city": {"type": "STRING"}}, "required": ["city"], "type": "OBJECT"}}]}], "labels": {"adk_agent_name": "chat_robot"}}, "contents": [{"parts": [{"text": "How is the weather like in Xi\'an?"}], "role": "user"}, {"parts": [{"function_call": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "args": {"city": "Xi\'an"}, "name": "get_city_weather"}}], "role": "model"}, {"parts": [{"function_response": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "name": "get_city_weather", "response": {"result": "Cool, 18\u00b0C"}}}], "role": "user"}]}',
            "gcp.vertex.agent.llm_response": '{"content":{"parts":[{"text":"The weather in Xi\'an is cool, with a temperature of 18\u00b0C."}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":132,"prompt_token_count":547,"total_token_count":679}}',
            "gen_ai.usage.input_tokens": 547,
            "gen_ai.usage.output_tokens": 679,
            "llm.provider": "google",
            "input.value": '{"model": "openai/doubao-seed-1.6-250615", "config": {"system_instruction": "Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"", "tools": [{"function_declarations": [{"description": "Retrieves the weather information of a given city. the args must in English", "name": "get_city_weather", "parameters": {"properties": {"city": {"type": "STRING"}}, "required": ["city"], "type": "OBJECT"}}]}], "labels": {"adk_agent_name": "chat_robot"}}, "contents": [{"parts": [{"text": "How is the weather like in Xi\'an?"}], "role": "user"}, {"parts": [{"function_call": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "args": {"city": "Xi\'an"}, "name": "get_city_weather"}}], "role": "model"}, {"parts": [{"function_response": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "name": "get_city_weather", "response": {"result": "Cool, 18\u00b0C"}}}], "role": "user"}]}',
            "input.mime_type": "application/json",
            "llm.tools.0.tool.json_schema": '{"description":"Retrieves the weather information of a given city. the args must in English","name":"get_city_weather","parameters":{"properties":{"city":{"type":"STRING"}},"required":["city"],"type":"OBJECT"}}',
            "llm.model_name": "openai/doubao-seed-1.6-250615",
            "llm.invocation_parameters": '{"system_instruction":"Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"","tools":[{"function_declarations":[{"description":"Retrieves the weather information of a given city. the args must in English","name":"get_city_weather","parameters":{"properties":{"city":{"type":"STRING"}},"required":["city"],"type":"OBJECT"}}]}],"labels":{"adk_agent_name":"chat_robot"}}',
            "llm.input_messages.0.message.role": "system",
            "llm.input_messages.0.message.content": 'Talk with user friendly.\n\nYou are an agent. Your internal name is "chat_robot".\n\n The description about you is "A robot talk with user."',
            "llm.input_messages.1.message.role": "user",
            "llm.input_messages.1.message.contents.0.message_content.text": "How is the weather like in Xi'an?",
            "llm.input_messages.1.message.contents.0.message_content.type": "text",
            "llm.input_messages.2.message.role": "model",
            "llm.input_messages.2.message.tool_calls.0.tool_call.id": "call_6ow5622pvcouw3tpvr7rfqtl",
            "llm.input_messages.2.message.tool_calls.0.tool_call.function.name": "get_city_weather",
            "llm.input_messages.2.message.tool_calls.0.tool_call.function.arguments": '{"city": "Xi\'an"}',
            "llm.input_messages.3.message.role": "tool",
            "llm.input_messages.3.message.name": "get_city_weather",
            "llm.input_messages.3.message.content": '{"result": "Cool, 18\u00b0C"}',
            "output.value": '{"content":{"parts":[{"text":"The weather in Xi\'an is cool, with a temperature of 18\u00b0C."}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":132,"prompt_token_count":547,"total_token_count":679}}',
            "output.mime_type": "application/json",
            "llm.token_count.total": 679,
            "llm.token_count.prompt": 547,
            "llm.token_count.completion": 132,
            "llm.output_messages.0.message.role": "model",
            "llm.output_messages.0.message.contents.0.message_content.text": "The weather in Xi'an is cool, with a temperature of 18\u00b0C.",
            "llm.output_messages.0.message.contents.0.message_content.type": "text",
            "gen_ai.prompt.0.role": "user",
            "gen_ai.prompt.0.content": '[{"text": "How is the weather like in Xi\'an?"}]',
            "gen_ai.completion.0.role": "model",
            "gen_ai.completion.0.content": '[{"text": "The weather in Xi\'an is cool, with a temperature of 18\\u00b0C."}]',
            "gen_ai.usage.prompt_tokens": 547,
            "gen_ai.usage.completion_tokens": 132,
            "gen_ai.usage.total_tokens": 679,
            "gen_ai.usage.cache_read_input_tokens": 0,
            "gen_ai.usage.cache_create_input_tokens": 0,
            "openinference.span.kind": "LLM",
        },
        "parent_span_id": 14844888006539887900,
    },
    {
        "name": "agent_run [chat_robot]",
        "span_id": 14844888006539887900,
        "trace_id": 115143748123782151752771111946932434777,
        "start_time": 1754884660688136000,
        "end_time": 1754884676664691000,
        "attributes": {
            "session.id": "veadk_example_session",
            "user.id": "veadk_default_user",
            "gen_ai.system": "veadk",
            "gen_ai.request.model": "openai/doubao-seed-1.6-250615",
            "gen_ai.response.model": "openai/doubao-seed-1.6-250615",
            "gen_ai.request.type": "completion",
            "output.value": '{"content":{"parts":[{"text":"The weather in Xi\'an is cool, with a temperature of 18\u00b0C."}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":132,"prompt_token_count":547,"total_token_count":679},"invocation_id":"e-ea6bb35b-c3f0-4c5c-b127-c71c7d6d6441","author":"chat_robot","actions":{"state_delta":{},"artifact_delta":{},"requested_auth_configs":{}},"id":"c0929124-9be0-4f75-a6ba-f7a531c9ccb6","timestamp":1754884672.227546}',
            "output.mime_type": "application/json",
            "openinference.span.kind": "AGENT",
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
            "input.mime_type": "application/json",
            "user.id": "veadk_default_user",
            "session.id": "veadk_example_session",
            "output.value": '{"content":{"parts":[{"text":"The weather in Xi\'an is cool, with a temperature of 18\u00b0C."}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":132,"prompt_token_count":547,"total_token_count":679},"invocation_id":"e-ea6bb35b-c3f0-4c5c-b127-c71c7d6d6441","author":"chat_robot","actions":{"state_delta":{},"artifact_delta":{},"requested_auth_configs":{}},"id":"c0929124-9be0-4f75-a6ba-f7a531c9ccb6","timestamp":1754884672.227546}',
            "output.mime_type": "application/json",
            "openinference.span.kind": "CHAIN",
        },
        "parent_span_id": None,
    },
    {
        "name": "execute_tool get_city_weather",
        "span_id": 10315930087681041331,
        "trace_id": 225149951093293230286974602372571218832,
        "start_time": 1754884684740875000,
        "end_time": 1754884684741386000,
        "attributes": {
            "session.id": "veadk_example_session",
            "user.id": "veadk_default_user",
            "gen_ai.system": "gcp.vertex.agent",
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "get_city_weather",
            "gen_ai.tool.description": "Retrieves the weather information of a given city. the args must in English",
            "gen_ai.tool.call.id": "call_4x60qqjspcwxfu3jtsw1m3sh",
            "gcp.vertex.agent.tool_call_args": '{"city": "Beijing"}',
            "gcp.vertex.agent.event_id": "e4e1b9cb-c147-4fb7-8cf6-dfecc0e0b9a0",
            "gcp.vertex.agent.tool_response": '{"result": "Sunny, 25\u00b0C"}',
            "gcp.vertex.agent.llm_request": "{}",
            "gcp.vertex.agent.llm_response": "{}",
            "tool.name": "get_city_weather",
            "tool.description": "Retrieves the weather information of a given city. the args must in English",
            "tool.parameters": '{"city": "Beijing"}',
            "input.value": '{"city": "Beijing"}',
            "input.mime_type": "application/json",
            "output.value": '{"id":"call_4x60qqjspcwxfu3jtsw1m3sh","name":"get_city_weather","response":{"result":"Sunny, 25\u00b0C"}}',
            "output.mime_type": "application/json",
            "openinference.span.kind": "TOOL",
        },
        "parent_span_id": 5741673860775380214,
    },
    {
        "name": "call_llm",
        "span_id": 5741673860775380214,
        "trace_id": 225149951093293230286974602372571218832,
        "start_time": 1754884677052310000,
        "end_time": 1754884684741523000,
        "attributes": {
            "session.id": "veadk_example_session",
            "user.id": "veadk_default_user",
            "gen_ai.system": "gcp.vertex.agent",
            "gen_ai.request.model": "openai/doubao-seed-1.6-250615",
            "gcp.vertex.agent.invocation_id": "e-b4defdb1-d023-47fa-9962-acd1e95ba1e1",
            "gcp.vertex.agent.session_id": "veadk_example_session",
            "gcp.vertex.agent.event_id": "262f18e2-3756-4633-95ee-5e76fe07b754",
            "gcp.vertex.agent.llm_request": '{"model": "openai/doubao-seed-1.6-250615", "config": {"system_instruction": "Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"", "tools": [{"function_declarations": [{"description": "Retrieves the weather information of a given city. the args must in English", "name": "get_city_weather", "parameters": {"properties": {"city": {"type": "STRING"}}, "required": ["city"], "type": "OBJECT"}}]}], "labels": {"adk_agent_name": "chat_robot"}}, "contents": [{"parts": [{"text": "How is the weather like in Xi\'an?"}], "role": "user"}, {"parts": [{"function_call": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "args": {"city": "Xi\'an"}, "name": "get_city_weather"}}], "role": "model"}, {"parts": [{"function_response": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "name": "get_city_weather", "response": {"result": "Cool, 18\u00b0C"}}}], "role": "user"}, {"parts": [{"text": "The weather in Xi\'an is cool, with a temperature of 18\u00b0C."}], "role": "model"}, {"parts": [{"text": "How is the weather like in BeiJing?"}], "role": "user"}]}',
            "gcp.vertex.agent.llm_response": '{"content":{"parts":[{"function_call":{"id":"call_4x60qqjspcwxfu3jtsw1m3sh","args":{"city":"Beijing"},"name":"get_city_weather"}}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":316,"prompt_token_count":584,"total_token_count":900}}',
            "gen_ai.usage.input_tokens": 584,
            "gen_ai.usage.output_tokens": 900,
            "llm.provider": "google",
            "input.value": '{"model": "openai/doubao-seed-1.6-250615", "config": {"system_instruction": "Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"", "tools": [{"function_declarations": [{"description": "Retrieves the weather information of a given city. the args must in English", "name": "get_city_weather", "parameters": {"properties": {"city": {"type": "STRING"}}, "required": ["city"], "type": "OBJECT"}}]}], "labels": {"adk_agent_name": "chat_robot"}}, "contents": [{"parts": [{"text": "How is the weather like in Xi\'an?"}], "role": "user"}, {"parts": [{"function_call": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "args": {"city": "Xi\'an"}, "name": "get_city_weather"}}], "role": "model"}, {"parts": [{"function_response": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "name": "get_city_weather", "response": {"result": "Cool, 18\u00b0C"}}}], "role": "user"}, {"parts": [{"text": "The weather in Xi\'an is cool, with a temperature of 18\u00b0C."}], "role": "model"}, {"parts": [{"text": "How is the weather like in BeiJing?"}], "role": "user"}]}',
            "input.mime_type": "application/json",
            "llm.tools.0.tool.json_schema": '{"description":"Retrieves the weather information of a given city. the args must in English","name":"get_city_weather","parameters":{"properties":{"city":{"type":"STRING"}},"required":["city"],"type":"OBJECT"}}',
            "llm.model_name": "openai/doubao-seed-1.6-250615",
            "llm.invocation_parameters": '{"system_instruction":"Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"","tools":[{"function_declarations":[{"description":"Retrieves the weather information of a given city. the args must in English","name":"get_city_weather","parameters":{"properties":{"city":{"type":"STRING"}},"required":["city"],"type":"OBJECT"}}]}],"labels":{"adk_agent_name":"chat_robot"}}',
            "llm.input_messages.0.message.role": "system",
            "llm.input_messages.0.message.content": 'Talk with user friendly.\n\nYou are an agent. Your internal name is "chat_robot".\n\n The description about you is "A robot talk with user."',
            "llm.input_messages.1.message.role": "user",
            "llm.input_messages.1.message.contents.0.message_content.text": "How is the weather like in Xi'an?",
            "llm.input_messages.1.message.contents.0.message_content.type": "text",
            "llm.input_messages.2.message.role": "model",
            "llm.input_messages.2.message.tool_calls.0.tool_call.id": "call_6ow5622pvcouw3tpvr7rfqtl",
            "llm.input_messages.2.message.tool_calls.0.tool_call.function.name": "get_city_weather",
            "llm.input_messages.2.message.tool_calls.0.tool_call.function.arguments": '{"city": "Xi\'an"}',
            "llm.input_messages.3.message.role": "tool",
            "llm.input_messages.3.message.name": "get_city_weather",
            "llm.input_messages.3.message.content": '{"result": "Cool, 18\u00b0C"}',
            "llm.input_messages.4.message.role": "model",
            "llm.input_messages.4.message.contents.0.message_content.text": "The weather in Xi'an is cool, with a temperature of 18\u00b0C.",
            "llm.input_messages.4.message.contents.0.message_content.type": "text",
            "llm.input_messages.5.message.role": "user",
            "llm.input_messages.5.message.contents.0.message_content.text": "How is the weather like in BeiJing?",
            "llm.input_messages.5.message.contents.0.message_content.type": "text",
            "output.value": '{"content":{"parts":[{"function_call":{"id":"call_4x60qqjspcwxfu3jtsw1m3sh","args":{"city":"Beijing"},"name":"get_city_weather"}}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":316,"prompt_token_count":584,"total_token_count":900}}',
            "output.mime_type": "application/json",
            "llm.token_count.total": 900,
            "llm.token_count.prompt": 584,
            "llm.token_count.completion": 316,
            "llm.output_messages.0.message.role": "model",
            "llm.output_messages.0.message.tool_calls.0.tool_call.id": "call_4x60qqjspcwxfu3jtsw1m3sh",
            "llm.output_messages.0.message.tool_calls.0.tool_call.function.name": "get_city_weather",
            "llm.output_messages.0.message.tool_calls.0.tool_call.function.arguments": '{"city": "Beijing"}',
            "gen_ai.prompt.0.role": "user",
            "gen_ai.prompt.0.content": '[{"text": "How is the weather like in BeiJing?"}]',
            "gen_ai.completion.0.role": "model",
            "gen_ai.completion.0.content": '[{"function_call": {"id": "call_4x60qqjspcwxfu3jtsw1m3sh", "args": {"city": "Beijing"}, "name": "get_city_weather"}}]',
            "gen_ai.usage.prompt_tokens": 584,
            "gen_ai.usage.completion_tokens": 316,
            "gen_ai.usage.total_tokens": 900,
            "gen_ai.usage.cache_read_input_tokens": 0,
            "gen_ai.usage.cache_create_input_tokens": 0,
            "openinference.span.kind": "LLM",
        },
        "parent_span_id": 8830792093920828159,
    },
    {
        "name": "call_llm",
        "span_id": 1294773233164416528,
        "trace_id": 225149951093293230286974602372571218832,
        "start_time": 1754884684742479000,
        "end_time": 1754884692281442000,
        "attributes": {
            "session.id": "veadk_example_session",
            "user.id": "veadk_default_user",
            "gen_ai.system": "gcp.vertex.agent",
            "gen_ai.request.model": "openai/doubao-seed-1.6-250615",
            "gcp.vertex.agent.invocation_id": "e-b4defdb1-d023-47fa-9962-acd1e95ba1e1",
            "gcp.vertex.agent.session_id": "veadk_example_session",
            "gcp.vertex.agent.event_id": "2aad3f22-94da-4e55-9976-56b2256b61fc",
            "gcp.vertex.agent.llm_request": '{"model": "openai/doubao-seed-1.6-250615", "config": {"system_instruction": "Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"", "tools": [{"function_declarations": [{"description": "Retrieves the weather information of a given city. the args must in English", "name": "get_city_weather", "parameters": {"properties": {"city": {"type": "STRING"}}, "required": ["city"], "type": "OBJECT"}}]}], "labels": {"adk_agent_name": "chat_robot"}}, "contents": [{"parts": [{"text": "How is the weather like in Xi\'an?"}], "role": "user"}, {"parts": [{"function_call": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "args": {"city": "Xi\'an"}, "name": "get_city_weather"}}], "role": "model"}, {"parts": [{"function_response": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "name": "get_city_weather", "response": {"result": "Cool, 18\u00b0C"}}}], "role": "user"}, {"parts": [{"text": "The weather in Xi\'an is cool, with a temperature of 18\u00b0C."}], "role": "model"}, {"parts": [{"text": "How is the weather like in BeiJing?"}], "role": "user"}, {"parts": [{"function_call": {"id": "call_4x60qqjspcwxfu3jtsw1m3sh", "args": {"city": "Beijing"}, "name": "get_city_weather"}}], "role": "model"}, {"parts": [{"function_response": {"id": "call_4x60qqjspcwxfu3jtsw1m3sh", "name": "get_city_weather", "response": {"result": "Sunny, 25\u00b0C"}}}], "role": "user"}]}',
            "gcp.vertex.agent.llm_response": '{"content":{"parts":[{"text":"The weather in Beijing is sunny, with a temperature of 25\u00b0C."}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":256,"prompt_token_count":644,"total_token_count":900}}',
            "gen_ai.usage.input_tokens": 644,
            "gen_ai.usage.output_tokens": 900,
            "llm.provider": "google",
            "input.value": '{"model": "openai/doubao-seed-1.6-250615", "config": {"system_instruction": "Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"", "tools": [{"function_declarations": [{"description": "Retrieves the weather information of a given city. the args must in English", "name": "get_city_weather", "parameters": {"properties": {"city": {"type": "STRING"}}, "required": ["city"], "type": "OBJECT"}}]}], "labels": {"adk_agent_name": "chat_robot"}}, "contents": [{"parts": [{"text": "How is the weather like in Xi\'an?"}], "role": "user"}, {"parts": [{"function_call": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "args": {"city": "Xi\'an"}, "name": "get_city_weather"}}], "role": "model"}, {"parts": [{"function_response": {"id": "call_6ow5622pvcouw3tpvr7rfqtl", "name": "get_city_weather", "response": {"result": "Cool, 18\u00b0C"}}}], "role": "user"}, {"parts": [{"text": "The weather in Xi\'an is cool, with a temperature of 18\u00b0C."}], "role": "model"}, {"parts": [{"text": "How is the weather like in BeiJing?"}], "role": "user"}, {"parts": [{"function_call": {"id": "call_4x60qqjspcwxfu3jtsw1m3sh", "args": {"city": "Beijing"}, "name": "get_city_weather"}}], "role": "model"}, {"parts": [{"function_response": {"id": "call_4x60qqjspcwxfu3jtsw1m3sh", "name": "get_city_weather", "response": {"result": "Sunny, 25\u00b0C"}}}], "role": "user"}]}',
            "input.mime_type": "application/json",
            "llm.tools.0.tool.json_schema": '{"description":"Retrieves the weather information of a given city. the args must in English","name":"get_city_weather","parameters":{"properties":{"city":{"type":"STRING"}},"required":["city"],"type":"OBJECT"}}',
            "llm.model_name": "openai/doubao-seed-1.6-250615",
            "llm.invocation_parameters": '{"system_instruction":"Talk with user friendly.\\n\\nYou are an agent. Your internal name is \\"chat_robot\\".\\n\\n The description about you is \\"A robot talk with user.\\"","tools":[{"function_declarations":[{"description":"Retrieves the weather information of a given city. the args must in English","name":"get_city_weather","parameters":{"properties":{"city":{"type":"STRING"}},"required":["city"],"type":"OBJECT"}}]}],"labels":{"adk_agent_name":"chat_robot"}}',
            "llm.input_messages.0.message.role": "system",
            "llm.input_messages.0.message.content": 'Talk with user friendly.\n\nYou are an agent. Your internal name is "chat_robot".\n\n The description about you is "A robot talk with user."',
            "llm.input_messages.1.message.role": "user",
            "llm.input_messages.1.message.contents.0.message_content.text": "How is the weather like in Xi'an?",
            "llm.input_messages.1.message.contents.0.message_content.type": "text",
            "llm.input_messages.2.message.role": "model",
            "llm.input_messages.2.message.tool_calls.0.tool_call.id": "call_6ow5622pvcouw3tpvr7rfqtl",
            "llm.input_messages.2.message.tool_calls.0.tool_call.function.name": "get_city_weather",
            "llm.input_messages.2.message.tool_calls.0.tool_call.function.arguments": '{"city": "Xi\'an"}',
            "llm.input_messages.3.message.role": "tool",
            "llm.input_messages.3.message.name": "get_city_weather",
            "llm.input_messages.3.message.content": '{"result": "Cool, 18\u00b0C"}',
            "llm.input_messages.4.message.role": "model",
            "llm.input_messages.4.message.contents.0.message_content.text": "The weather in Xi'an is cool, with a temperature of 18\u00b0C.",
            "llm.input_messages.4.message.contents.0.message_content.type": "text",
            "llm.input_messages.5.message.role": "user",
            "llm.input_messages.5.message.contents.0.message_content.text": "How is the weather like in BeiJing?",
            "llm.input_messages.5.message.contents.0.message_content.type": "text",
            "llm.input_messages.6.message.role": "model",
            "llm.input_messages.6.message.tool_calls.0.tool_call.id": "call_4x60qqjspcwxfu3jtsw1m3sh",
            "llm.input_messages.6.message.tool_calls.0.tool_call.function.name": "get_city_weather",
            "llm.input_messages.6.message.tool_calls.0.tool_call.function.arguments": '{"city": "Beijing"}',
            "llm.input_messages.7.message.role": "tool",
            "llm.input_messages.7.message.name": "get_city_weather",
            "llm.input_messages.7.message.content": '{"result": "Sunny, 25\u00b0C"}',
            "output.value": '{"content":{"parts":[{"text":"The weather in Beijing is sunny, with a temperature of 25\u00b0C."}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":256,"prompt_token_count":644,"total_token_count":900}}',
            "output.mime_type": "application/json",
            "llm.token_count.total": 900,
            "llm.token_count.prompt": 644,
            "llm.token_count.completion": 256,
            "llm.output_messages.0.message.role": "model",
            "llm.output_messages.0.message.contents.0.message_content.text": "The weather in Beijing is sunny, with a temperature of 25\u00b0C.",
            "llm.output_messages.0.message.contents.0.message_content.type": "text",
            "gen_ai.prompt.0.role": "user",
            "gen_ai.prompt.0.content": '[{"text": "How is the weather like in BeiJing?"}]',
            "gen_ai.completion.0.role": "model",
            "gen_ai.completion.0.content": '[{"text": "The weather in Beijing is sunny, with a temperature of 25\\u00b0C."}]',
            "gen_ai.usage.prompt_tokens": 644,
            "gen_ai.usage.completion_tokens": 256,
            "gen_ai.usage.total_tokens": 900,
            "gen_ai.usage.cache_read_input_tokens": 0,
            "gen_ai.usage.cache_create_input_tokens": 0,
            "openinference.span.kind": "LLM",
        },
        "parent_span_id": 8830792093920828159,
    },
    {
        "name": "agent_run [chat_robot]",
        "span_id": 8830792093920828159,
        "trace_id": 225149951093293230286974602372571218832,
        "start_time": 1754884677050889000,
        "end_time": 1754884692281791000,
        "attributes": {
            "session.id": "veadk_example_session",
            "user.id": "veadk_default_user",
            "gen_ai.system": "veadk",
            "gen_ai.request.model": "openai/doubao-seed-1.6-250615",
            "gen_ai.response.model": "openai/doubao-seed-1.6-250615",
            "gen_ai.request.type": "completion",
            "output.value": '{"content":{"parts":[{"text":"The weather in Beijing is sunny, with a temperature of 25\u00b0C."}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":256,"prompt_token_count":644,"total_token_count":900},"invocation_id":"e-b4defdb1-d023-47fa-9962-acd1e95ba1e1","author":"chat_robot","actions":{"state_delta":{},"artifact_delta":{},"requested_auth_configs":{}},"id":"2aad3f22-94da-4e55-9976-56b2256b61fc","timestamp":1754884684.74225}',
            "output.mime_type": "application/json",
            "openinference.span.kind": "AGENT",
        },
        "parent_span_id": 6624741805060007734,
    },
    {
        "name": "invocation [veadk_default_app]",
        "span_id": 6624741805060007734,
        "trace_id": 225149951093293230286974602372571218832,
        "start_time": 1754884677050051000,
        "end_time": 1754884692281935000,
        "attributes": {
            "input.value": '{"user_id": "veadk_default_user", "session_id": "veadk_example_session", "new_message": "{\\"parts\\": [{\\"video_metadata\\": null, \\"thought\\": null, \\"inline_data\\": null, \\"file_data\\": null, \\"thought_signature\\": null, \\"code_execution_result\\": null, \\"executable_code\\": null, \\"function_call\\": null, \\"function_response\\": null, \\"text\\": \\"How is the weather like in BeiJing?\\"}], \\"role\\": \\"user\\"}", "run_config": "{\\"speech_config\\": null, \\"response_modalities\\": null, \\"save_input_blobs_as_artifacts\\": false, \\"support_cfc\\": false, \\"streaming_mode\\": \\"StreamingMode.NONE\\", \\"output_audio_transcription\\": null, \\"input_audio_transcription\\": null, \\"realtime_input_config\\": null, \\"enable_affective_dialog\\": null, \\"proactivity\\": null, \\"max_llm_calls\\": 500}"}',
            "input.mime_type": "application/json",
            "user.id": "veadk_default_user",
            "session.id": "veadk_example_session",
            "output.value": '{"content":{"parts":[{"text":"The weather in Beijing is sunny, with a temperature of 25\u00b0C."}],"role":"model"},"partial":false,"usage_metadata":{"candidates_token_count":256,"prompt_token_count":644,"total_token_count":900},"invocation_id":"e-b4defdb1-d023-47fa-9962-acd1e95ba1e1","author":"chat_robot","actions":{"state_delta":{},"artifact_delta":{},"requested_auth_configs":{}},"id":"2aad3f22-94da-4e55-9976-56b2256b61fc","timestamp":1754884684.74225}',
            "output.mime_type": "application/json",
            "openinference.span.kind": "CHAIN",
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

    base_evaluator.generate_eval_data(eval_set_file_path=eval_set_file_path)

    assert len(base_evaluator.invocation_list) == 1
    assert len(base_evaluator.invocation_list[0].invocations) == 1
    assert (
        base_evaluator.invocation_list[0].invocations[0].invocation_id
        == "b7982664-0ab6-47cc-ab13-326656afdf75"
    )

    os.remove(eval_set_file_path)


def test_evaluator_using_tracing():
    base_evaluator = BaseEvaluator(agent=None, name="test_evaluator")

    # save data to file
    tracing_set_file_path = "./tracing_set_for_test_evaluator.json"
    with open(tracing_set_file_path, "w") as f:
        json.dump(TRACE_SET_DATA, f)

    base_evaluator.generate_eval_data_from_tracing(
        tracing_set_file_path=tracing_set_file_path
    )

    assert len(base_evaluator.invocation_list) == 1
    assert len(base_evaluator.invocation_list[0].invocations) == 2
    assert (
        base_evaluator.invocation_list[0].invocations[0].invocation_id
        == "e-ea6bb35b-c3f0-4c5c-b127-c71c7d6d6441"
    )

    os.remove(tracing_set_file_path)
