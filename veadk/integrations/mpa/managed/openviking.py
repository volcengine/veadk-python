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
import re
import time

from .database import DeploymentError, agent_suffix
from .diagnostics import CODE_CATEGORIES, classify_error, report

ERROR_KEYS = frozenset(
    {
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


class OpenVikingCloud:
    def __init__(self, source):
        if source.provider != "volcengine" or source.region != "cn-beijing":
            raise OpenVikingError("openvikingConfigurationConflict")
        self.source = source

    async def _call(self, action: str, body: dict, operation: str, *, create=False):
        for attempt in range(1, 2 if create else 4):
            rejected = False

            def request():
                from veadk.utils.volcengine_sign import volcengine_signed_request

                credential = self.source._credentials()
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
            else:
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
            report(
                operation,
                category,
                attempt=attempt,
                outcome="retrying" if retry else "failed",
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
            raise OpenVikingError(key, category=category, rejected=rejected) from None
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
            result.get("Success") is not True
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
            {"ResourceID": ident, "UserID": "default"},
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
    for field in ("VLM", "Embedding"):
        actual = row.get(field)
        expected = request[field]
        if (
            not isinstance(actual, dict)
            or actual.get("ModelVersion") != expected["ModelVersion"]
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
    model_api_key,
    project="default",
    timeout=600,
    progress=lambda stage: None,
):
    """Caller holds the deployment lock; uncertain creates never repeat."""
    if region != "cn-beijing":
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
            openviking_id=ident, openviking_managed=True, openviking_url=DATA_URL
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
        "OPENVIKING_URL": DATA_URL,
        "OPENVIKING_RESOURCE_ID": ident,
        "OPENVIKING_API_KEY": key,
        "OPENVIKING_USER": "default",
    }
