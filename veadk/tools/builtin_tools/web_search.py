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

"""
The document of this tool see: https://www.volcengine.com/docs/85508/1650263
"""

import os
import requests

from google.adk.tools import ToolContext

from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)
_BYTEPLUS_WEB_SEARCH_URL = "https://torchlight.byteintlapi.com/search_api/web_search"


def _extract_web_results(response: object) -> list[dict]:
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    if not isinstance(response, dict):
        return []
    candidates: list[object] = [
        ((response.get("Result") or {}).get("WebResults")),
        ((response.get("Result") or {}).get("Results")),
        ((response.get("Result") or {}).get("SearchResults")),
        ((response.get("Data") or {}).get("WebResults")),
        ((response.get("Data") or {}).get("Results")),
        ((response.get("data") or {}).get("web_results")),
        ((response.get("data") or {}).get("results")),
        response.get("WebResults"),
        response.get("results"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def _result_summary(item: dict) -> str:
    for key in ("Summary", "summary", "Snippet", "snippet", "Content", "content"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _byteplus_web_search(query: str, count: int = 5) -> dict:
    api_key = os.getenv("BYTEPLUS_WEB_SEARCH_API_KEY")
    if not api_key:
        raise ValueError("BYTEPLUS_WEB_SEARCH_API_KEY is not set.")
    response = requests.post(
        url=os.getenv("BYTEPLUS_WEB_SEARCH_URL", _BYTEPLUS_WEB_SEARCH_URL),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"Query": query, "Count": count},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {"results": data}


def web_search(query: str, tool_context: ToolContext | None = None) -> list[str]:
    """Search a query in websites.

    Args:
        query: The query to search.

    Returns:
        A list of result documents.
    """
    provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
    logger.info(f"Cloud provider: {provider}")
    if provider == "byteplus":
        try:
            response = _byteplus_web_search(query, count=5)
            return [
                summary
                for summary in (
                    _result_summary(item) for item in _extract_web_results(response)
                )
                if summary
            ]
        except Exception as e:
            logger.error(f"BytePlus web search failed {e}")
            return [f"Web search failed: {e}"]

    ak = None
    sk = None
    # First try to get tool-specific AK/SK
    ak = os.getenv("TOOL_WEB_SEARCH_ACCESS_KEY")
    sk = os.getenv("TOOL_WEB_SEARCH_SECRET_KEY")
    if ak and sk:
        logger.debug("Successfully get tool-specific AK/SK.")
    elif tool_context:
        ak = tool_context.state.get("VOLCENGINE_ACCESS_KEY")
        sk = tool_context.state.get("VOLCENGINE_SECRET_KEY")
    session_token = ""

    if not (ak and sk):
        logger.debug("Get AK/SK from tool context failed.")
        ak = os.getenv("VOLCENGINE_ACCESS_KEY")
        sk = os.getenv("VOLCENGINE_SECRET_KEY")
        if not (ak and sk):
            logger.debug("Get AK/SK from environment variables failed.")
            credential = get_credential_from_vefaas_iam()
            ak = credential.access_key_id
            sk = credential.secret_access_key
            session_token = credential.session_token
        else:
            logger.debug("Successfully get AK/SK from environment variables.")
    else:
        logger.debug("Successfully get AK/SK from tool context.")

    response = ve_request(
        request_body={
            "Query": query,
            "SearchType": "web",
            "Count": 5,
            "NeedSummary": True,
        },
        action="WebSearch",
        ak=ak,
        sk=sk,
        service="volc_torchlight_api",
        version="2025-01-01",
        region="cn-beijing",
        host="mercury.volcengineapi.com",
        header={"X-Security-Token": session_token},
    )

    try:
        results: list = response["Result"]["WebResults"]
        final_results = []
        for result in results:
            final_results.append(result["Summary"].strip())
        return final_results
    except Exception as e:
        logger.error(f"Web search failed {e}, response body: {response}")
        return [response]
