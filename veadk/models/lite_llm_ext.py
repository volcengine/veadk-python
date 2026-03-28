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


def patch_litellm_get_content():
    import base64
    from typing import Union, Iterable

    import litellm
    from litellm import OpenAIMessageContent
    from google.adk.models import lite_llm
    from google.genai import types

    async def _patch_get_content(
        parts: Iterable[types.Part],
        *,
        provider: str = "",
    ) -> Union[OpenAIMessageContent, str]:
        from google.adk.models.lite_llm import (
            _decode_inline_text_data,
            _SUPPORTED_FILE_CONTENT_MIME_TYPES,
            _FILE_ID_REQUIRED_PROVIDERS,
            ChatCompletionFileUrlObject,
        )

        content_objects = []
        for part in parts:
            if part.text:
                if len(parts) == 1:
                    return part.text
                content_objects.append(
                    {
                        "type": "text",
                        "text": part.text,
                    }
                )
            elif (
                part.inline_data
                and part.inline_data.data
                and part.inline_data.mime_type
            ):
                if part.inline_data.mime_type.startswith("text/"):
                    decoded_text = _decode_inline_text_data(part.inline_data.data)
                    if len(parts) == 1:
                        return decoded_text
                    content_objects.append(
                        {
                            "type": "text",
                            "text": decoded_text,
                        }
                    )
                    continue
                base64_string = base64.b64encode(part.inline_data.data).decode("utf-8")
                data_uri = f"data:{part.inline_data.mime_type};base64,{base64_string}"
                # LiteLLM providers extract the MIME type from the data URI; avoid
                # passing a separate `format` field that some backends reject.

                if part.inline_data.mime_type.startswith("image"):
                    content_objects.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": data_uri},
                        }
                    )
                elif part.inline_data.mime_type.startswith("video"):
                    content_objects.append(
                        {
                            "type": "video_url",
                            "video_url": {"url": data_uri},
                        }
                    )
                elif part.inline_data.mime_type.startswith("audio"):
                    content_objects.append(
                        {
                            "type": "audio_url",
                            "audio_url": {"url": data_uri},
                        }
                    )
                elif part.inline_data.mime_type in _SUPPORTED_FILE_CONTENT_MIME_TYPES:
                    # OpenAI/Azure require file_id from uploaded file, not inline data
                    if provider in _FILE_ID_REQUIRED_PROVIDERS:
                        file_response = await litellm.acreate_file(
                            file=part.inline_data.data,
                            purpose="assistants",
                            custom_llm_provider=provider,
                        )
                        content_objects.append(
                            {
                                "type": "file",
                                "file": {"file_id": file_response.id},
                            }
                        )
                    else:
                        content_objects.append(
                            {
                                "type": "file",
                                "file": {"file_data": data_uri},
                            }
                        )
                else:
                    raise ValueError(
                        "LiteLlm(BaseLlm) does not support content part with MIME type "
                        f"{part.inline_data.mime_type}."
                    )
            elif part.file_data and part.file_data.file_uri:
                # Modify to enable file_data to support image, video URLs
                if part.file_data.mime_type.startswith("image"):
                    content_objects.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": part.file_data.file_uri},
                        }
                    )
                elif part.file_data.mime_type.startswith("video"):
                    content_objects.append(
                        {
                            "type": "video_url",
                            "video_url": {"url": part.file_data.file_uri},
                        }
                    )
                else:
                    # The original part of lite_llm `_get_content`
                    file_object: ChatCompletionFileUrlObject = {
                        "file_id": part.file_data.file_uri,
                    }
                    content_objects.append(
                        {
                            "type": "file",
                            "file": file_object,
                        }
                    )

        return content_objects

    # Apply the patch
    lite_llm._get_content = _patch_get_content
