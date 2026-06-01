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

"""VeADK documentation assistant — the "Ask AI" agent for the docs site.

A VeADK `Agent` with one tool, `search_docs`, that does keyword search over the
prebuilt docs index (`docs_index.json`). The model retrieves relevant pages,
then answers grounded in them and cites the page URLs.

Run locally:   python serve.py
Deploy:        veadk deploy --vefaas-app-name veadk-docs-assistant ...
"""

import os

from veadk import Agent

from docs_search import search

# Model name (Volcengine Ark). Overridable via MODEL_AGENT_NAME.
MODEL_NAME = os.getenv("MODEL_AGENT_NAME") or "deepseek-v4-flash-260425"

INSTRUCTION = """\
You are the documentation assistant for VeADK (Volcengine Agent Development Kit).

Your job is to answer questions about VeADK using ONLY the official documentation.

Workflow for every question:
1. Call the `search_docs` tool with a focused query (you may call it several times
   with different queries to gather enough context).
2. Answer strictly based on the returned excerpts. Do not invent APIs, flags, or
   behavior that the docs do not mention.
3. If the docs do not contain the answer, say so plainly and suggest the closest
   relevant page.

Style:
- Reply in the SAME language as the user's question (Chinese or English).
- Be concise and concrete; prefer short code snippets when the docs show them.
- Always cite the pages you used as a short "Sources" list of their `url`s.
"""


def search_docs(query: str, language: str = "") -> dict:
    """Search the VeADK documentation and return the most relevant pages.

    Args:
        query: A focused search query, in the user's language. Keep it to the key
            terms (e.g. "deploy to VeFaaS", "短期记忆 MySQL").
        language: Optional language filter: "cn" for Chinese pages, "en" for
            English, or "" to search both.

    Returns:
        A dict with a "results" list; each result has `title`, `url`, `lang`, and
        an `excerpt` of the page content to ground your answer.
    """
    lang = language.strip().lower() or None
    if lang not in (None, "cn", "en"):
        lang = None
    return {"results": search(query, top_k=5, lang=lang)}


agent = Agent(
    name="veadk_docs_assistant",
    description="Answers questions about VeADK using the official documentation.",
    instruction=INSTRUCTION,
    model_name=MODEL_NAME,
    tools=[search_docs],
)

# Required by the Google ADK / VeADK agent loader and `veadk deploy`.
root_agent = agent
