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

import io
from typing import cast

import pypdfium2 as pdfium
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from veadk.utils.pdf_to_images import make_pdf_to_images_callback

# The callback ignores its context; a placeholder keeps the type checker happy.
_NO_CTX = cast(CallbackContext, None)


def _parts(request: LlmRequest) -> list[types.Part]:
    assert request.contents and request.contents[0].parts is not None
    return request.contents[0].parts


def _make_pdf(num_pages: int) -> bytes:
    """Build an in-memory PDF with the requested number of blank pages."""
    doc = pdfium.PdfDocument.new()
    for _ in range(num_pages):
        doc.new_page(200, 200)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _request_with_pdf(pdf_bytes: bytes) -> LlmRequest:
    return LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(text="What is in this document?"),
                    types.Part(
                        inline_data=types.Blob(
                            mime_type="application/pdf", data=pdf_bytes
                        )
                    ),
                ],
            )
        ]
    )


def test_pdf_part_replaced_with_page_images():
    request = _request_with_pdf(_make_pdf(3))
    callback = make_pdf_to_images_callback()

    result = callback(callback_context=_NO_CTX, llm_request=request)

    assert result is None  # proceed to the model
    parts = _parts(request)
    # The original text part is preserved.
    assert parts[0].text == "What is in this document?"
    # No PDF part remains.
    assert all(
        not (p.inline_data and p.inline_data.mime_type == "application/pdf")
        for p in parts
    )
    # One image/png part per page.
    image_parts = [
        p for p in parts if p.inline_data and p.inline_data.mime_type == "image/png"
    ]
    assert len(image_parts) == 3
    assert all(p.inline_data and p.inline_data.data for p in image_parts)


def test_max_pages_is_respected():
    request = _request_with_pdf(_make_pdf(5))
    callback = make_pdf_to_images_callback(max_pages=2)

    callback(callback_context=_NO_CTX, llm_request=request)

    image_parts = [
        p
        for p in _parts(request)
        if p.inline_data and p.inline_data.mime_type == "image/png"
    ]
    assert len(image_parts) == 2


def test_non_pdf_request_is_untouched():
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])]
    )
    callback = make_pdf_to_images_callback()

    callback(callback_context=_NO_CTX, llm_request=request)

    parts = _parts(request)
    assert len(parts) == 1
    assert parts[0].text == "hello"
