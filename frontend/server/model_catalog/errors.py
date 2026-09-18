# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Preserve cloud error responses without forwarding request credentials."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from fastapi.responses import JSONResponse, Response

from .protocol import ModelCatalogError

if TYPE_CHECKING:
    import httpx
    import requests


def _redact_credentials(text: str, secrets: Sequence[str | None]) -> str:
    for value in sorted({value for value in secrets if value}, key=len, reverse=True):
        text = text.replace(value, "[redacted]")
    return text


def cloud_response_error(
    response: requests.Response | httpx.Response,
    *,
    action: str,
    secrets: Sequence[str | None] = (),
) -> ModelCatalogError:
    return ModelCatalogError(
        f"{action} 请求失败（云服务 HTTP {response.status_code}）",
        status_code=response.status_code if response.status_code >= 400 else 502,
        upstream_body=_redact_credentials(response.text, secrets),
        upstream_status=response.status_code,
        upstream_request_id=response.headers.get("X-Request-Id", ""),
        action=action,
        source="upstream",
    )


def cloud_request_error(
    error: Exception,
    *,
    action: str,
    secrets: Sequence[str | None] = (),
) -> ModelCatalogError:
    import httpx
    import requests

    response = getattr(error, "response", None)
    # requests.Response is false for HTTP errors, so do not test its truthiness.
    if isinstance(response, (requests.Response, httpx.Response)):
        return cloud_response_error(response, action=action, secrets=secrets)
    cause = error.__cause__
    if isinstance(cause, Exception):
        return cloud_request_error(cause, action=action, secrets=secrets)
    detail = _redact_credentials(str(error), secrets)
    timeout = isinstance(
        error, (requests.Timeout, httpx.TimeoutException, TimeoutError)
    )
    return ModelCatalogError(
        f"{action} 请求未完成，未收到云服务响应，请稍后重试（{type(error).__name__}: {detail}）",
        status_code=504 if timeout else 502,
        action=action,
        source="transport",
    )


def cloud_payload(
    result: Any,
    *,
    action: str,
    secrets: Sequence[str | None] = (),
) -> Any:
    import httpx
    import requests

    response = (
        result if isinstance(result, (requests.Response, httpx.Response)) else None
    )
    if response is not None:
        if response.status_code >= 400:
            raise cloud_response_error(response, action=action, secrets=secrets)
        try:
            result = response.json()
        except ValueError as error:
            if action == "GetRawApiKey":
                raise ModelCatalogError("API Key 服务返回了无法解析的结果") from error
            raise cloud_response_error(
                response, action=action, secrets=secrets
            ) from error
    metadata = result.get("ResponseMetadata") if isinstance(result, dict) else None
    error = metadata.get("Error") if isinstance(metadata, dict) else None
    if error or (isinstance(result, dict) and result.get("error")):
        if response is None:
            # Injectable clients may already have decoded the JSON response.
            response = httpx.Response(200, text=json.dumps(result, ensure_ascii=False))
        raise cloud_response_error(response, action=action, secrets=secrets)
    return result


def model_catalog_error_response(error: ModelCatalogError) -> Response:
    headers = {"Cache-Control": "no-store", "X-Studio-Error-Source": error.source}
    if error.action:
        headers["X-Studio-Upstream-Action"] = error.action
    if error.upstream_status is not None:
        headers["X-Studio-Upstream-Status"] = str(error.upstream_status)
    if error.upstream_request_id:
        headers["X-Request-Id"] = error.upstream_request_id
    if error.upstream_body is not None:
        try:
            json.loads(error.upstream_body)
            media_type = "application/json"
        except ValueError:
            media_type = "text/plain"
        return Response(
            content=error.upstream_body,
            status_code=error.status_code,
            media_type=media_type,
            headers=headers,
        )
    return JSONResponse(
        {"detail": str(error)}, status_code=error.status_code, headers=headers
    )
