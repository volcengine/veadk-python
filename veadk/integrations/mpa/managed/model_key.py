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

"""Read an existing Ark model key using account-verified deployment credentials."""

from __future__ import annotations

import asyncio
import math
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Protocol

from veadk.utils.volcengine_sign import volcengine_signed_request

from .config import Profile
from .database import DeploymentError
from .diagnostics import CODE_CATEGORIES, classify_error, report


class ModelKeyError(DeploymentError):
    """A safe discovery failure with no provider text or credential values."""


class CredentialSource(Protocol):
    def _credentials(self) -> Any: ...


def _creation_time(item: dict) -> datetime:
    """Normalize creation metadata without assuming provider list ordering."""
    value = next(
        (
            item[name]
            for name in ("CreateTime", "CreatedAt", "CreationTime")
            if name in item
        ),
        None,
    )
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError()
        if isinstance(value, str) and not value.replace(".", "", 1).isdigit():
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if instant.tzinfo is None:
                raise ValueError()
            return instant.astimezone(timezone.utc)
        seconds = float(value)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError()
        if seconds >= 100_000_000_000:
            seconds /= 1000
        return datetime.fromtimestamp(seconds, timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        report("list_model_keys", "protocol_error")
        raise ModelKeyError(
            "Cannot determine the newest Ark key from creation time; "
            "set VEADK_MPA_ARK_API_KEY_ID or VEADK_MPA_ARK_API_KEY_NAME"
        ) from None


async def _read(
    cloud: CredentialSource, profile: Profile, action: str, body: dict
) -> dict:
    operation = "list_model_keys" if action == "ListApiKeys" else "get_model_key"
    for attempt in range(1, 4):

        def request():
            from .provider import managed_host

            # Refresh and verify the deployment account for every signed call.
            credential = cloud._credentials()
            return volcengine_signed_request(
                request_body=body,
                ak=credential.access_key_id,
                sk=credential.secret_access_key,
                header={"X-Security-Token": credential.session_token or ""},
                service="ark",
                region=profile.region,
                host=managed_host("ark", profile.region, profile.provider),
                path="/",
                query={"Action": action, "Version": "2024-01-01"},
                timeout=(10, 30),
            )

        category = ""
        try:
            response = await asyncio.to_thread(request)
        except Exception as error:
            category = classify_error(error)
            response = {}
        if not category:
            if not isinstance(response, dict):
                category = "protocol_error"
            else:
                metadata = response.get("ResponseMetadata") or {}
                failure = metadata.get("Error") if isinstance(metadata, dict) else None
                if not isinstance(metadata, dict):
                    category = "protocol_error"
                elif failure:
                    category = CODE_CATEGORIES.get(
                        str(failure.get("Code", ""))
                        if isinstance(failure, dict)
                        else "",
                        "provider_error",
                    )
                elif isinstance(response.get("Result"), dict):
                    return response["Result"]
                else:
                    category = "protocol_error"
        retry = attempt < 3 and category in {
            "connection",
            "timeout",
            "throttled",
            "unavailable",
        }
        report(
            operation,
            category,
            attempt=attempt,
            outcome="retrying" if retry else "failed",
        )
        if not retry:
            raise ModelKeyError(
                "Ark model key lookup failed; check deployment Ark read permissions and connectivity"
            ) from None
        await asyncio.sleep((0.2, 0.5)[attempt - 1])
    raise AssertionError("Ark read retry loop exhausted")


async def resolve_model_key(profile: Profile, cloud: CredentialSource) -> Profile:
    """Resolve only opted-in profiles; leave explicit CLI model auth unchanged."""
    options = profile.managed.model_key
    if options.mode != "ark":
        return profile
    candidates: dict[str, dict] = {}
    previous_total = None
    for page in range(1, 101):
        result = await _read(
            cloud,
            profile,
            "ListApiKeys",
            {
                "ProjectName": options.project_name,
                "Filter": {"AllowAll": True},
                "PageNumber": page,
                "PageSize": 100,
            },
        )
        items = result.get("Items")
        total = result.get("TotalCount", result.get("Total"))
        if (
            not isinstance(items, list)
            or len(items) > 100
            or total is not None
            and (type(total) is not int or total < 0)
            or previous_total is not None
            and total != previous_total
        ):
            raise ModelKeyError(
                "Invalid Ark key list; retry after checking Ark configuration"
            )
        for item in items:
            if not isinstance(item, dict) or type(item.get("Id")) not in (str, int):
                raise ModelKeyError("Invalid Ark key list")
            identifier = str(item["Id"])
            if (
                not identifier
                or identifier in candidates
                and candidates[identifier] != item
            ):
                raise ModelKeyError("Conflicting Ark key list; retry discovery")
            candidates[identifier] = item
        if total is not None:
            if len(candidates) > total or not items and len(candidates) < total:
                raise ModelKeyError("Incomplete Ark key list; retry discovery")
            if len(candidates) == total:
                break
        elif len(items) < 100:
            break
        previous_total = total
    else:
        raise ModelKeyError("Ark key list exceeded the discovery limit")
    matches = [
        item
        for identifier, item in candidates.items()
        if (not options.api_key_id or identifier == options.api_key_id)
        and (not options.api_key_name or item.get("Name") == options.api_key_name)
        and ("Status" not in item or item["Status"] == "Active")
    ]
    if not matches:
        report("list_model_keys", "not_found")
        raise ModelKeyError(
            "No matching Ark API key; create or enable a key in the selected project"
        )
    selected = matches[0]
    if len(matches) > 1 and not (options.api_key_id or options.api_key_name):
        selected = max(
            matches, key=lambda item: (_creation_time(item), str(item["Id"]))
        )
    elif len(matches) > 1:
        report("list_model_keys", "invalid_request")
        raise ModelKeyError(
            "Found multiple Ark API keys; set VEADK_MPA_ARK_API_KEY_ID or VEADK_MPA_ARK_API_KEY_NAME"
        )
    identifier = selected["Id"]
    result = await _read(
        cloud,
        profile,
        "GetRawApiKey",
        {
            "Id": int(identifier) if str(identifier).isdigit() else identifier,
            "ProjectName": options.project_name,
        },
    )
    value = result.get("ApiKey")
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or "*" in value
        or any(c.isspace() for c in value)
    ):
        report("get_model_key", "protocol_error")
        raise ModelKeyError("Ark did not return a usable raw API key")
    return replace(profile, values={**profile.values, "model_api_key": value})
