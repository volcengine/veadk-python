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

import asyncio
import os

from google.adk.tools import ToolContext

from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


def do_search(query: str, ak: str, sk: str, session_token: str) -> list[str]:
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


async def parallel_web_search(
    queries: list[str], tool_context: ToolContext | None = None
) -> dict[str, list[str]]:
    """Search queries from websites in parallel.

    Args:
        queries: The queries to search. Each query will be searched in parallel.

    Returns:
        A dict of query to result documents.
    """
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

    results = {}

    logger.info(f"Start to search {queries} in parallel.")
    results_list = await asyncio.gather(
        *(
            asyncio.to_thread(do_search, query, ak, sk, session_token)
            for query in queries
        )
    )
    logger.info(f"Finish to search {queries} in parallel.")

    results = dict(zip(queries, results_list))
    logger.debug(f"Search results: {results}")
    return results
