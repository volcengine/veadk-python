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

"""Preserve generation diagnostics while removing credential values."""

import json
import os
import re
import traceback


def generation_diagnostics(error: BaseException, *secrets: str) -> str:
    sections: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        sections.append(f"{type(current).__name__}: {current}")
        response = getattr(current, "response", None)
        status = getattr(current, "status_code", None) or getattr(
            response, "status_code", None
        )
        if status is not None:
            sections.append(f"HTTP status: {status}")
        request_id = getattr(current, "request_id", None)
        if request_id:
            sections.append(f"Request ID: {request_id}")
        headers = getattr(response, "headers", {})
        for name in ("x-request-id", "x-tt-logid", "x-trace-id", "x-amzn-requestid"):
            if headers.get(name):
                sections.append(f"{name}: {headers[name]}")
        body = getattr(current, "body", None)
        if body is not None:
            sections.append(
                "Provider error body:\n"
                + json.dumps(body, ensure_ascii=False, default=str)
            )
        if response is not None:
            try:
                response_text = response.text
            except (AttributeError, RuntimeError, UnicodeError):
                response_text = ""
            if response_text:
                sections.append("Provider response:\n" + str(response_text))
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    sections.append(
        "Exception trace:\n"
        + "".join(traceback.format_exception(type(error), error, error.__traceback__))
    )
    text = "\n\n".join(sections)
    environment_secrets = [
        value
        for key, value in os.environ.items()
        if len(value) >= 8
        and any(
            marker in key.upper()
            for marker in ("KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")
        )
    ]
    for secret in sorted(set([*secrets, *environment_secrets]), key=len, reverse=True):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)(\bbearer\s+)[^\s,;\"']+", r"\1[REDACTED]", text)
    text = re.sub(
        r"(?i)((?:[\"']?)(?:api[_-]?key|access[_-]?key(?:[_-]?id)?|secret[_-]?(?:access[_-]?)?key|client[_-]?secret|authorization|password|session[_-]?token|security[_-]?token|token|secret|credential|ak|sk|cookie|set-cookie)(?:[\"']?)\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
        r"\1[REDACTED]",
        text,
    )
    return text


class QualityGenerationError(Exception):
    def __init__(self, diagnostics: str, *, timeout: bool = False) -> None:
        super().__init__(
            "quality_generation_timeout" if timeout else "quality_generation_failed"
        )
        self.diagnostics = diagnostics
        self.timeout = timeout
