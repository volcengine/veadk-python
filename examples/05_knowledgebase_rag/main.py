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

"""Retrieval-Augmented Generation (RAG) with a KnowledgeBase.

A `KnowledgeBase` embeds your documents and stores them in a vector backend.
When you attach it to an `Agent`, VeADK automatically gives the agent a
retrieval tool, so it can look up relevant passages before answering — grounding
its responses in *your* content instead of the model's general knowledge.

This uses the `local` (in-memory) backend, which requires the embedding model
config and the optional `extensions` dependency:

    pip install "veadk-python[extensions]"
"""

import asyncio
from pathlib import Path

from veadk import Agent, Runner
from veadk.knowledgebase import KnowledgeBase

DOCS_DIR = Path(__file__).parent / "docs"


async def main() -> None:
    # 1. Build a knowledge base and ingest the local docs (embedded on add).
    knowledgebase = KnowledgeBase(backend="local", index="company_faq")
    knowledgebase.add_from_directory(str(DOCS_DIR))

    # 2. Attach it to the agent. VeADK adds a retrieval tool automatically.
    agent = Agent(
        name="rag_agent",
        description="Answers questions using the company knowledge base.",
        instruction=(
            "Answer questions about the company. Always consult the knowledge "
            "base first and base your answer on what you retrieve. If the answer "
            "is not in the knowledge base, say so."
        ),
        knowledgebase=knowledgebase,
    )

    runner = Runner(agent=agent, app_name="rag_demo")

    answer = await runner.run(
        messages="公司的年假政策是怎样的？远程办公可以吗？",
        session_id="demo-session",
    )
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
