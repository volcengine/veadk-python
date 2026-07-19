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

"""Render PDF attachments to page images before the model sees them.

Most chat models (e.g. doubao-seed) accept images but not raw PDF bytes. This
``before_model_callback`` rewrites every ``application/pdf`` inline-data part in
the request into one ``image/png`` part per page, so a vision-capable model can
read the document (including scanned PDFs — the model effectively OCRs them).

Usage::

    from veadk import Agent
    from veadk.utils.pdf_to_images import pdf_to_images_before_model_callback

    agent = Agent(
        ...,
        before_model_callback=pdf_to_images_before_model_callback,
    )

PDF rendering dependencies are included in the default VeADK installation.
"""

import io
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_PDF_MIME = "application/pdf"


def render_pdf_to_png_parts(
    pdf_bytes: bytes, max_pages: int, scale: float
) -> list[types.Part]:
    """Render up to ``max_pages`` pages of a PDF into ``image/png`` parts."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    page_count = len(pdf)
    rendered = min(page_count, max_pages)
    if page_count > max_pages:
        logger.warning(
            f"PDF has {page_count} pages; rendering only the first {max_pages}."
        )

    parts: list[types.Part] = []
    for i in range(rendered):
        # pypdfium2 leaves `scale` untyped (default 1), so it is inferred as
        # int; floats are valid at runtime (e.g. 1.5x). Cast away the warning.
        image = pdf[i].render(scale=scale).to_pil()  # type: ignore[arg-type]
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        parts.append(
            types.Part(
                inline_data=types.Blob(mime_type="image/png", data=buffer.getvalue())
            )
        )
    return parts


def make_pdf_to_images_callback(max_pages: int = 10, scale: float = 2.0):
    """Build a ``before_model_callback`` that turns PDF parts into page images.

    Args:
        max_pages: Maximum pages rendered per PDF (caps token cost).
        scale: pypdfium2 render scale; higher is sharper but larger.
    """

    def callback(
        callback_context: CallbackContext, llm_request: LlmRequest
    ) -> Optional[LlmResponse]:
        for content in llm_request.contents or []:
            parts = content.parts or []
            if not any(
                p.inline_data and p.inline_data.mime_type == _PDF_MIME for p in parts
            ):
                continue

            new_parts: list[types.Part] = []
            for part in parts:
                if (
                    part.inline_data
                    and part.inline_data.mime_type == _PDF_MIME
                    and part.inline_data.data
                ):
                    new_parts.extend(
                        render_pdf_to_png_parts(part.inline_data.data, max_pages, scale)
                    )
                else:
                    new_parts.append(part)
            content.parts = new_parts

        return None

    return callback


# Default callback: 10 pages, 2x scale.
pdf_to_images_before_model_callback = make_pdf_to_images_callback()
