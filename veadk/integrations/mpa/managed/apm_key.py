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

"""Fetch a BytePlus APM AppKey for the managed Studio Runtime environment."""

from __future__ import annotations

import asyncio

from veadk.utils.volcengine_sign import volcengine_signed_request

from .config import Profile
from .database import DeploymentError
from .diagnostics import CODE_CATEGORIES, classify_error, report
from .model_key import CredentialSource
from .openviking import exception_metadata, response_metadata

RUNTIME_APM_KEY = "OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY"


class ApmKeyError(DeploymentError):
    """A safe lookup error without provider text or credentials."""


def _usable_key(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 4096
        and "*" not in value
        and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
    )


async def get_runtime_apm_key(profile: Profile, cloud: CredentialSource) -> str:
    """Use deployment credentials; the caller holds the result only in memory."""
    if profile.provider != "byteplus":
        return ""
    explicit = profile.managed.runtime.env.get(RUNTIME_APM_KEY, "")
    if explicit:
        if not _usable_key(explicit):
            report("get_apm_key", "protocol_error")
            raise ApmKeyError("Configured APM AppKey is invalid")
        return explicit
    if profile.region != "ap-southeast-1":
        raise ApmKeyError("APM AppKey lookup is unsupported in this BytePlus region")
    for attempt in range(1, 4):

        def request():
            credential = cloud._credentials()
            return volcengine_signed_request(
                request_body={},
                ak=credential.access_key_id,
                sk=credential.secret_access_key,
                header={
                    "X-Security-Token": credential.session_token or "",
                    "X-Apmplus-Region": profile.region.replace("-", "_"),
                },
                service="apmplus_server",
                region=profile.region,
                host="apmplus-server.ap-southeast-1.byteplusapi.com",
                path="/",
                query={"Action": "GetAppKey", "Version": "2024-07-30"},
                timeout=(10, 30),
            )

        error_code, request_id = "", ""
        try:
            response = await asyncio.wait_for(asyncio.to_thread(request), timeout=45)
        except Exception as error:
            category = classify_error(error)
            error_code, request_id = exception_metadata(error)
        else:
            category = "protocol_error"
            if isinstance(response, dict):
                error_code, request_id = response_metadata(response)
                metadata = response.get("ResponseMetadata") or {}
                data = response.get("data")
                if isinstance(metadata, dict) and metadata.get("Error"):
                    category = "provider_error"
                elif isinstance(metadata, dict) and isinstance(data, dict):
                    value = data.get("app_key")
                    if _usable_key(value):
                        return str(value)
        if error_code:
            category = (
                "timeout"
                if error_code == "InternalServiceTimeout"
                else CODE_CATEGORIES.get(error_code, category)
            )
        retrying = attempt < 3 and category in {
            "connection",
            "timeout",
            "throttled",
            "unavailable",
        }
        report(
            "get_apm_key",
            category,
            attempt=attempt,
            outcome="retrying" if retrying else "failed",
            error_code=error_code,
            request_id=request_id,
        )
        if not retrying:
            raise ApmKeyError(
                "APM AppKey lookup failed; check deployment APM read permissions and connectivity"
            ) from None
        await asyncio.sleep((0.2, 0.5)[attempt - 1])
    raise AssertionError("APM read retry loop exhausted")
