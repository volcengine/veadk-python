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

import hashlib
import json
from typing import Any, Literal

import httpx
from volcengine.ApiInfo import ApiInfo
from volcengine.auth.SignerV4 import SignerV4
from volcengine.tls.const import (
    APPLICATION_JSON,
    CONTENT_MD5,
    CONTENT_TYPE,
    DATA,
    WEB_TRACKS,
)
from volcengine.tls.TLSService import TLSService

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

HEADER_API_VERSION = "x-tls-apiversion"
API_VERSION_V_0_3_0 = "0.3.0"

API_INFO = {
    "CreateProject": ApiInfo("POST", "/CreateProject", {}, {}, {}),
    "DescribeProjects": ApiInfo("GET", "/DescribeProjects", {}, {}, {}),
    "CreateTraceInstance": ApiInfo("POST", "/CreateTraceInstance", {}, {}, {}),
    "DescribeTraceInstances": ApiInfo("GET", "/DescribeTraceInstances", {}, {}, {}),
    "DescribeTraceInstance": ApiInfo("GET", "/DescribeTraceInstance", {}, {}, {}),
}


def __prepare_request(
    client: TLSService,
    api: str,
    params: dict | None = None,
    body: Any | None = None,
    request_headers: dict | None = None,
):
    if params is None:
        params = {}
    if body is None:
        body = {}

    request = client.prepare_request(API_INFO[api], params)

    if request_headers is None:
        request_headers = {CONTENT_TYPE: APPLICATION_JSON}
    request.headers.update(request_headers)

    if "json" in request.headers[CONTENT_TYPE] and api != WEB_TRACKS:
        request.body = json.dumps(body)
    else:
        request.body = body[DATA]

    if len(request.body) != 0:
        if isinstance(request.body, str):
            request.headers[CONTENT_MD5] = hashlib.md5(
                request.body.encode("utf-8")
            ).hexdigest()
        else:
            request.headers[CONTENT_MD5] = hashlib.md5(request.body).hexdigest()

    SignerV4.sign(request, client.service_info.credentials)

    return request


async def ve_tls_request(
    client: TLSService,
    api: str,
    params: dict | None = None,
    body: dict | None = None,
    request_headers: dict | None = None,
    method: Literal["POST", "GET", "PUT", "DELETE"] = "POST",
):
    """Customize a standard HTTP request to the Volcengine TLS API"""

    if request_headers is None:
        request_headers = {HEADER_API_VERSION: API_VERSION_V_0_3_0}
    elif HEADER_API_VERSION not in request_headers:
        request_headers[HEADER_API_VERSION] = API_VERSION_V_0_3_0
    if CONTENT_TYPE not in request_headers:
        request_headers[CONTENT_TYPE] = APPLICATION_JSON
    request = __prepare_request(client, api, params, body, request_headers)

    url = request.build()

    async with httpx.AsyncClient() as session:
        while True:
            try:
                response = await session.request(
                    method=method,
                    url=url,
                    headers=request.headers,
                    data=request.body,  # type: ignore
                    timeout=60,
                )
                return response.json()
            except Exception as e:
                logger.error(
                    f"Error occurred while making {method} request to {url}: {e}. Response: {response}"
                )
