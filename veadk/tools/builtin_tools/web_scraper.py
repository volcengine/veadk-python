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

from typing import Any

import requests

from veadk.config import getenv


def web_scraper(query: str) -> dict[str, Any]:
    """query a single keyword from some search engineer

    Args:
        query (str, optional): query keyword. Defaults to None.

    Returns:
        dict[str, Any]: search results
    """

    endpoint = getenv("TOOL_WEB_SCRAPER_ENDPOINT")
    token = getenv("TOOL_WEB_SCRAPER_API_KEY")

    try:
        url = f"https://{endpoint}/v1/queries"
        headers = {
            "Content-Type": "application/json",
            "X-VE-Source": "google_search",
            "X-VE-API-Key": token,
        }
        data = {
            "query": query,
            "source": "google_search",
            "parse": True,
            "limit": "10",
            "start_page": "1",
            "pages": "1",
            "context": [
                {"key": "nfpr", "value": True},
                {"key": "safe_search", "value": False},
                {"key": "filter", "value": 1},
            ],
        }
        response = requests.post(url, headers=headers, json=data, verify=False)

        response.raise_for_status()

        response_json = response.json() if response.content else None
        results_dict = (
            response_json.get("results")[0].get("content").get("results").get("organic")
        )

        results_str = ""
        for r in results_dict:
            dic = {
                "url": r.get("url"),
                "title": r.get("title"),
                "description": r.get("desc"),
            }
            results_str += str(dic)
        return results_str

    except requests.exceptions.RequestException as e:
        error_message = f"Error: {str(e)}, response: {response}"
        raise ValueError(error_message)
