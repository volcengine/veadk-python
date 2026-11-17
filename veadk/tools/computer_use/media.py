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

"""Adapt CUA tool-result images without changing provider model classes."""

from google.genai import types


def lift_screenshots(request):
    """Expose nested screenshot media to Ark without editing stored events."""
    expanded = []
    for content in request.contents:
        images, parts = [], []
        for part in content.parts or []:
            response = part.function_response
            if (
                response
                and response.name
                and response.name.startswith("cua_")
                and response.parts
            ):
                for media in response.parts:
                    blob = media.inline_data
                    if blob and blob.mime_type and blob.mime_type.startswith("image/"):
                        images.append(
                            types.Part.from_bytes(
                                data=blob.data, mime_type=blob.mime_type
                            )
                        )
                part = part.model_copy(
                    update={
                        "function_response": response.model_copy(update={"parts": None})
                    }
                )
            parts.append(part)
        expanded.append(content.model_copy(update={"parts": parts}))
        if images:
            expanded.append(types.Content(role="user", parts=images))
    request.contents = expanded
