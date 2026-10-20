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

from google.genai import types

from veadk.models.ark_llm import _content_to_input_item


def test_model_thought_and_final_text_are_aggregated_once():
    content = types.Content(
        role="model",
        parts=[
            types.Part(text="thinking", thought=True),
            types.Part(text="final answer"),
        ],
    )

    assert _content_to_input_item(content) == [
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "input_text", "text": "thinking"},
                {"type": "input_text", "text": "final answer"},
            ],
        }
    ]


def test_model_function_call_precedes_single_aggregated_text_message():
    content = types.Content(
        role="model",
        parts=[
            types.Part(text="first"),
            types.Part(
                function_call=types.FunctionCall(
                    id="call-1",
                    name="lookup",
                    args={"query": "veadk"},
                )
            ),
            types.Part(text="second"),
        ],
    )

    assert _content_to_input_item(content) == [
        {
            "arguments": '{"query": "veadk"}',
            "call_id": "call-1",
            "name": "lookup",
            "type": "function_call",
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "input_text", "text": "first"},
                {"type": "input_text", "text": "second"},
            ],
        },
    ]


def test_model_file_data_is_preserved_in_single_message():
    content = types.Content(
        role="model",
        parts=[
            types.Part(
                file_data=types.FileData(
                    file_uri="file_id://file-1",
                    mime_type="application/pdf",
                )
            )
        ],
    )

    assert _content_to_input_item(content) == [
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "input_file",
                    "file_id": "file-1",
                }
            ],
        }
    ]


def test_model_inline_data_is_preserved_in_single_message():
    content = types.Content(
        role="model",
        parts=[
            types.Part(
                inline_data=types.Blob(
                    data=b"image-bytes",
                    mime_type="image/png",
                )
            )
        ],
    )

    assert _content_to_input_item(content) == [
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,aW1hZ2UtYnl0ZXM=",
                    "detail": "auto",
                }
            ],
        }
    ]
