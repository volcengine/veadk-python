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

import os

from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


# ARK ListApiKeys caps the page size at 10 server-side (a larger PageSize is
# ignored), so a specific key may sit on any page. We page through until we
# either match by name or exhaust the list.
_ARK_PROJECT_NAME = "default"
_ARK_PAGE_SIZE = 10


def get_ark_token(region: str = "cn-beijing", api_key_name: str | None = None) -> str:
    """Fetch a raw ARK API key.

    Args:
        region: VolcEngine region for signing (ARK keys are region-agnostic; this
            only affects the signed host, kept for BytePlus routing).
        api_key_name: When given, resolve the key whose ``Name`` matches exactly.
            Raises ``ValueError`` if no key with that name exists. When omitted,
            the first key in the account's list is used (legacy behavior).

    Returns:
        The raw API key string.
    """
    logger.info("Fetching ARK token...")

    access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY")
    session_token = ""

    if not (access_key and secret_key):
        # try to get from vefaas iam
        cred = get_credential_from_vefaas_iam()
        access_key = cred.access_key_id
        secret_key = cred.secret_access_key
        session_token = cred.session_token

    provider = os.getenv("CLOUD_PROVIDER")
    host = "open.volcengineapi.com"
    if provider and provider.lower() == "byteplus":
        region = "ap-southeast-1"
        host = "open.byteplusapi.com"

    def _list_api_keys(page_number: int) -> dict:
        # Pagination goes in the query string; putting PageNumber/PageSize in the
        # request body makes the ARK gateway 504.
        res = ve_request(
            request_body={
                "ProjectName": _ARK_PROJECT_NAME,
                "Filter": {"AllowAll": True},
            },
            header={"X-Security-Token": session_token},
            query={"PageNumber": str(page_number), "PageSize": str(_ARK_PAGE_SIZE)},
            action="ListApiKeys",
            ak=access_key,
            sk=secret_key,
            service="ark",
            version="2024-01-01",
            region=region,
            host=host,
        )
        try:
            return res["Result"]
        except KeyError:
            raise ValueError(f"Failed to get ARK api key list: {res}")

    if api_key_name:
        target_id = None
        page = 1
        scanned = 0
        total = 0
        while True:
            result = _list_api_keys(page)
            total = result.get("TotalCount", 0)
            items = result.get("Items", [])
            for item in items:
                if item.get("Name") == api_key_name:
                    target_id = item["Id"]
                    break
            scanned += len(items)
            # Stop as soon as we match, run out of items, or cover the whole list.
            if target_id is not None or not items or scanned >= total:
                break
            page += 1
        if target_id is None:
            raise ValueError(
                f"ARK API Key named '{api_key_name}' not found in project "
                f"'{_ARK_PROJECT_NAME}' (scanned {scanned} keys)."
            )
        logger.info(f"Using ARK API Key by name='{api_key_name}', id={target_id}.")
    else:
        items = _list_api_keys(1).get("Items", [])
        if not items:
            raise ValueError(f"No ARK API keys found in project '{_ARK_PROJECT_NAME}'.")
        target_id = items[0]["Id"]
        logger.warning("By default, VeADK fetches the first API Key in the list.")
        logger.info(
            f"Try to fetch ARK API Key with id={target_id}, name={items[0].get('Name')}"
        )

    # get raw api key
    res = ve_request(
        request_body={"Id": target_id},
        header={"X-Security-Token": session_token},
        action="GetRawApiKey",
        ak=access_key,
        sk=secret_key,
        service="ark",
        version="2024-01-01",
        region=region,
        host=host,
    )
    try:
        api_key = res["Result"]["ApiKey"]
        logger.info(f"Successfully fetched ARK API Key (starts with {api_key[:8]}).")
        return api_key
    except KeyError:
        raise ValueError(f"Failed to get ARK api key: {res}")
