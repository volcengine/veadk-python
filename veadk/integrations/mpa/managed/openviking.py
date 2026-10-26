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

"""Prepare an owned OpenViking library without persisting data-plane secrets."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import time

from .database import DeploymentError, agent_suffix
from .diagnostics import (
    CODE_CATEGORIES,
    classify_error,
    report,
    safe_error_code,
    safe_request_id,
    with_diagnostic,
)

ERROR_KEYS = frozenset(
    {
        "openvikingModelEndpointsInvalid",
        "openvikingPermissionDenied",
        "openvikingConfigurationConflict",
        "openvikingCreateUnknown",
        "openvikingNotReady",
        "openvikingResourceFailed",
        "openvikingResourceMissing",
        "openvikingModelConfigurationRejected",
        "openvikingUnavailable",
        "openvikingInvalidResponse",
        "openvikingQuotaExceeded",
    }
)
DATA_URL = "https://api.vikingdb.cn-beijing.volces.com/openviking"

BYTEPLUS_DATA_URL = "https://api.vikingdb.ap-southeast-1.bytepluses.com/openviking"


def supports_auto_openviking(provider, region):
    return (provider, region) in {
        ("volcengine", "cn-beijing"),
        ("byteplus", "ap-southeast-1"),
    }


def byteplus_model_endpoints() -> tuple[str, str]:
    """Resolve nonsecret inference endpoints; defaults are operator-requested trials."""
    vlm = os.getenv("OV_VLM_ENDPOINT_ID", "seed-2-0-lite-260428")
    embedding = os.getenv("OV_EMBEDDING_ENDPOINT_ID", "skylark-embedding-vision-251215")
    validate_model_endpoints(vlm, embedding)
    return vlm, embedding


def validate_model_endpoints(vlm, embedding):
    for value in (vlm, embedding):
        if not isinstance(value, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value
        ):
            raise OpenVikingError("openvikingModelEndpointsInvalid")


def validate_model_key(value):
    """Reject unusable model credentials without including them in errors."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or value.startswith("<")
        or "*" in value
        or any(character.isspace() for character in value)
    ):
        raise OpenVikingError("openvikingConfigurationConflict")


class OpenVikingError(DeploymentError):
    """Allowlisted error; never carry provider response text or credentials."""

    def __init__(
        self, key: str, *, category: str = "deployment_error", rejected: bool = False
    ):
        self.key = key if key in ERROR_KEYS else "openvikingUnavailable"
        self.category = category
        self.rejected = rejected
        super().__init__(self.key)


def response_metadata(response: object) -> tuple[str, str]:
    """Extract identifiers only; provider messages and payloads never escape."""
    if not isinstance(response, dict):
        return "", ""
    metadata = response.get("ResponseMetadata")
    if not isinstance(metadata, dict):
        return "", ""
    error = metadata.get("Error")
    return (
        safe_error_code(error.get("Code")) if isinstance(error, dict) else "",
        safe_request_id(metadata.get("RequestId")),
    )


def exception_metadata(error: Exception) -> tuple[str, str]:
    """Inspect structured HTTP/SDK bodies without using exception text."""
    response = getattr(error, "response", None)
    if response is not None:
        try:
            code, request_id = response_metadata(response.json())
            if code or request_id:
                return code, request_id
        except (ValueError, TypeError, AttributeError):
            pass
    body = getattr(error, "body", None)
    if isinstance(body, (str, bytes)) and len(body) <= 65536:
        try:
            return response_metadata(json.loads(body))
        except (ValueError, TypeError):
            pass
    return "", ""


class OpenVikingCloud:
    def __init__(self, source):
        if not supports_auto_openviking(source.provider, source.region):
            raise OpenVikingError("openvikingConfigurationConflict")
        self.source = source

    async def _call(self, action: str, body: dict, operation: str, *, create=False):
        for attempt in range(1, 2 if create else 4):
            rejected = False
            error_code, request_id = "", ""

            def request():
                credential = self.source._credentials()
                if self.source.provider == "byteplus":
                    from .openviking_byteplus import signed_request

                    return signed_request(
                        action=action, body=body, credential=credential
                    )
                from veadk.utils.volcengine_sign import volcengine_signed_request

                return volcengine_signed_request(
                    request_body=body,
                    ak=credential.access_key_id,
                    sk=credential.secret_access_key,
                    header={"X-Security-Token": credential.session_token or ""},
                    service="vikingdb",
                    region="cn-beijing",
                    host="vikingdb.cn-beijing.volcengineapi.com",
                    path="/",
                    query={"Action": action, "Version": "2025-06-09"},
                    timeout=(10, 30),
                )

            try:
                response = await asyncio.to_thread(request)
            except Exception as exc:
                category = classify_error(exc)
                error_code, request_id = exception_metadata(exc)
            else:
                error_code, request_id = response_metadata(response)
                if self.source.provider == "byteplus" and isinstance(response, dict):
                    response = dict(response)
                    if "Result" not in response and isinstance(
                        response.get("result"), dict
                    ):
                        response["Result"] = response["result"]
                metadata = (
                    response.get("ResponseMetadata", {})
                    if isinstance(response, dict)
                    else None
                )
                error = metadata.get("Error") if isinstance(metadata, dict) else None
                if isinstance(error, dict):
                    category = CODE_CATEGORIES.get(
                        str(error.get("Code", "")), "provider_error"
                    )
                    if error.get("Code") == "ResourceNotExist":
                        category = "not_found"
                    elif error.get("Code") == "QuotaExceeded":
                        category = "throttled"
                    rejected = category in {
                        "permission",
                        "invalid_request",
                        "throttled",
                    }
                elif (
                    isinstance(response, dict)
                    and isinstance(metadata, dict)
                    and not error
                    and isinstance(response.get("Result"), dict)
                ):
                    return response["Result"]
                else:
                    category = "protocol_error"
            retry = (
                not create
                and attempt < 3
                and category in {"connection", "timeout", "throttled", "unavailable"}
            )
            diagnostic = report(
                operation,
                category,
                attempt=attempt,
                outcome="retrying" if retry else "failed",
                error_code=error_code,
                request_id=request_id,
            )
            if retry:
                await asyncio.sleep((0.2, 0.5)[attempt - 1])
                continue
            key = {
                "permission": "openvikingPermissionDenied",
                "not_found": "openvikingResourceMissing",
                "invalid_request": "openvikingModelConfigurationRejected"
                if create
                else "openvikingConfigurationConflict",
                "protocol_error": "openvikingInvalidResponse",
                "throttled": "openvikingQuotaExceeded",
            }.get(category, "openvikingUnavailable")
            raise with_diagnostic(
                OpenVikingError(key, category=category, rejected=rejected), diagnostic
            ) from None
        raise AssertionError("OpenViking read retry exhausted")

    async def create(self, request, *, model_api_key):
        validate_model_key(model_api_key)
        wire = copy.deepcopy(request)
        for field in ("VLM", "Embedding"):
            for credential in wire[field]["Credentials"]:
                credential["ApiKey"] = model_api_key
        result = await self._call(
            "CreateOpenVikingCollection", wire, "create_openviking", create=True
        )
        ident = result.get("ResourceID")
        if (
            (
                result.get("Success") is not True
                if self.source.provider == "volcengine"
                else result.get("Success", True) is not True
            )
            or not isinstance(ident, str)
            or not re.fullmatch(r"ov-[A-Za-z0-9_-]{1,125}", ident)
        ):
            raise OpenVikingError("openvikingCreateUnknown", category="protocol_error")
        return ident

    async def get(self, ident):
        return await self._call(
            "GetOpenVikingCollection", {"ResourceID": ident}, "get_openviking"
        )

    async def api_key(self, ident):
        result = await self._call(
            "AccessOpenVikingApiKey",
            {
                "ResourceID": ident,
                **(
                    {"UserID": "default"}
                    if self.source.provider == "volcengine"
                    else {}
                ),
            },
            "get_openviking_key",
        )
        key = result.get("ApiKey")
        if result.get("UserID", "default") != "default":
            raise OpenVikingError(
                "openvikingInvalidResponse", category="protocol_error"
            )
        if not isinstance(key, str) or not key.strip() or len(key) > 4096 or "*" in key:
            raise OpenVikingError(
                "openvikingInvalidResponse", category="protocol_error"
            )
        return key


def validate_library(row, ident, request):
    if not isinstance(row, dict) or row.get("ResourceID") != ident:
        raise OpenVikingError("openvikingResourceMissing")
    if any(
        row.get(key) != request[key]
        for key in ("Name", "Description", "Project", "Version")
    ):
        raise OpenVikingError("openvikingConfigurationConflict")
    if "Source" in request and row.get("Source") != request["Source"]:
        raise OpenVikingError("openvikingConfigurationConflict")
    for field in ("VLM", "Embedding"):
        actual = row.get(field)
        expected = request[field]
        if (
            not isinstance(actual, dict)
            or (
                "ModelVersion" in expected
                and actual.get("ModelVersion") != expected["ModelVersion"]
            )
            or str(actual.get("ModelName", "")).replace(".", "-")
            != expected["ModelName"].replace(".", "-")
        ):
            raise OpenVikingError("openvikingConfigurationConflict")
        credentials = actual.get("Credentials")
        if (
            not isinstance(credentials, list)
            or len(credentials) != len(expected["Credentials"])
            or any(
                not isinstance(credential, dict)
                or any(
                    credential.get(key) != desired[key]
                    for key in ("Source", "EndpointID")
                    if key in desired
                )
                for credential, desired in zip(credentials, expected["Credentials"])
            )
        ):
            raise OpenVikingError("openvikingConfigurationConflict")


async def ensure_openviking(
    entry,
    cloud,
    *,
    account,
    region,
    agent_id,
    provider="volcengine",
    model_api_key,
    model_endpoints: tuple[str, str] | None = None,
    project="default",
    timeout=600,
    progress=lambda stage: None,
):
    """Caller holds the deployment lock; uncertain creates never repeat."""
    if not supports_auto_openviking(provider, region):
        raise OpenVikingError("openvikingConfigurationConflict")
    validate_model_key(model_api_key)
    progress("openviking")
    suffix = agent_suffix(account, region, agent_id)
    request = {
        "Name": "mpa_ov_" + suffix,
        "Description": "mpa-openviking:v1:" + suffix,
        "Project": project,
        "Version": "enterprise",
        "VLM": {
            "ModelName": "doubao-seed-2.0-lite",
            "ModelVersion": "260428",
            "Credentials": [
                {"Source": "volcengine", "EndpointID": "doubao-seed-2-0-lite-260428"}
            ],
        },
        "Embedding": {
            "ModelName": "doubao-embedding-vision",
            "ModelVersion": "251215",
            "Credentials": [
                {"Source": "volcengine", "EndpointID": "doubao-embedding-vision-251215"}
            ],
        },
    }
    data_url = DATA_URL
    if provider == "byteplus":
        data_url = BYTEPLUS_DATA_URL
        vlm, embedding = (
            byteplus_model_endpoints() if model_endpoints is None else model_endpoints
        )
        validate_model_endpoints(vlm, embedding)
        request.update(Version="developer", Source="volcengine")
        request["VLM"] = {
            "ModelName": "seed-2-0-lite",
            "Credentials": [{"Source": "volcengine", "EndpointID": vlm}],
        }
        request["Embedding"] = {
            "ModelName": "skylark-embedding-vision",
            "Credentials": [{"Source": "volcengine", "EndpointID": embedding}],
        }
    record = await entry.read()
    if record.get("state") in {"deleting", "deleted"}:
        raise OpenVikingError("openvikingConfigurationConflict")
    ident = record.get("openviking_id", "")
    if record.get("openviking_request") and record["openviking_request"] != request:
        legacy_request = copy.deepcopy(request)
        for field in ("VLM", "Embedding"):
            legacy_request[field].pop("Credentials")
        if not (
            not ident
            and not record.get("pending")
            and record.get("openviking_create_requested") is False
            and record["openviking_request"] == legacy_request
        ):
            raise OpenVikingError("openvikingConfigurationConflict")
    if ident:
        if (
            record.get("openviking_managed") is not True
            or record.get("openviking_request") != request
        ):
            raise OpenVikingError("openvikingConfigurationConflict")
    else:
        if record.get("pending"):
            raise OpenVikingError("openvikingConfigurationConflict")
        if record.get("openviking_create_requested"):
            raise OpenVikingError("openvikingCreateUnknown")
        record.update(openviking_request=request, openviking_create_requested=True)
        await entry.save(record)
        try:
            ident = await cloud.create(request, model_api_key=model_api_key)
        except Exception as exc:
            if isinstance(exc, OpenVikingError) and (
                exc.rejected
                or exc.category
                in {
                    "permission",
                    "invalid_request",
                }
            ):
                record["openviking_create_requested"] = False
                await entry.save(record)
                raise
            raise OpenVikingError("openvikingCreateUnknown") from None
        if not isinstance(ident, str) or not re.fullmatch(
            r"ov-[A-Za-z0-9_-]{1,125}", ident
        ):
            raise OpenVikingError("openvikingCreateUnknown")
        record.update(
            openviking_id=ident, openviking_managed=True, openviking_url=data_url
        )
        await entry.save(record)
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OpenVikingError("openvikingNotReady", category="timeout")
        try:
            row = await asyncio.wait_for(cloud.get(ident), remaining)
        except asyncio.TimeoutError:
            raise OpenVikingError("openvikingNotReady", category="timeout") from None
        validate_library(row, ident, request)
        status = row.get("Status")
        if status == "READY":
            break
        if status == "FAILED":
            raise OpenVikingError(
                "openvikingResourceFailed", category="resource_failed"
            )
        if status != "INIT":
            raise OpenVikingError(
                "openvikingInvalidResponse", category="protocol_error"
            )
        if time.monotonic() >= deadline:
            raise OpenVikingError("openvikingNotReady", category="timeout")
        await asyncio.sleep(2)
    record["openviking_state"] = "READY"
    await entry.save(record)
    progress("openviking_key")
    key = await cloud.api_key(ident)
    return {
        "OPENVIKING_URL": data_url,
        "OPENVIKING_RESOURCE_ID": ident,
        "OPENVIKING_API_KEY": key,
        "OPENVIKING_USER": "default",
    }
