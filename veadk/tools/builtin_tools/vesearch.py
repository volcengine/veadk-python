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

import requests

from veadk.config import getenv, settings


def vesearch(query: str) -> str:
    """Search information from Internet, social media, news sites, etc.

    Args:
        query: The query string to search.

    Returns:
        Summarized search results.
    """
    api_key = settings.tool.vesearch.api_key
    bot_id = str(getenv("TOOL_VESEARCH_ENDPOINT"))

    if api_key == "":
        return "Invoke `vesearch` failed. Please set TOOL_VESEARCH_API_KEY as your environment variable."
    if bot_id == "":
        return "Invoke `vesearch` failed. Please set VESEARCH_BOT_ID as your environment variable."

    URL = "https://open.feedcoopapi.com/agent_api/agent/chat/completion"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {
        "bot_id": bot_id,
        "messages": [{"role": "user", "content": query}],
    }

    response = requests.post(URL, json=data, headers=headers)
    if response.status_code == 200:
        result = response.json()
        return result["choices"][0]["message"]["content"]
    else:
        return response.text
