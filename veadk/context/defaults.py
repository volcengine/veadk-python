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

"""Invocation-owned retrieval for ordinary SDK and Studio Agents.

Open the disposable index only under context pressure. Explicitly bound rankers
remain caller-owned. Session records, not the index, authorize every lookup.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import os
from contextlib import asynccontextmanager
from pathlib import Path

from veadk.utils.logger import get_logger

from .adaptive_retriever import AdaptiveContextRetriever
from .runtime import context_retriever

logger = get_logger(__name__)


class ArkContextEmbedding:
    """Small text-only adapter with a per-invocation request/concurrency budget.

    Uses the SDK's existing Ark embedding model configuration. No embedding
    weights, traces, source bodies or credentials are downloaded or logged.
    """

    def __init__(self, *, model, dimension, api_key, api_base, max_calls):
        # Identical model labels on different configured services cannot reuse
        # one another's vectors. Only a digest of the endpoint enters the index.
        endpoint = hashlib.sha256(api_base.rstrip("/").encode()).hexdigest()[:16]
        self.model = f"ark:{endpoint}:{model}"
        self._request_model = model
        self.dimension = dimension
        self._api_key = api_key
        self._api_base = api_base
        self._remaining = max_calls
        self._semaphore = asyncio.Semaphore(4)
        self._client = None

    async def embed(self, texts):
        if len(texts) > self._remaining:
            raise ValueError("embedding_call_budget_exhausted")
        self._remaining -= len(texts)
        if self._client is None:
            from volcenginesdkarkruntime import AsyncArk

            self._client = AsyncArk(
                api_key=self._api_key,
                base_url=self._api_base,
                timeout=4.0,
                max_retries=0,
            )

        client = self._client

        async def one(text):
            async with self._semaphore:
                result = await client.multimodal_embeddings.create(
                    model=self._request_model,
                    input=[{"type": "text", "text": text}],
                    dimensions=self.dimension,
                )
                return result.data.embedding

        tasks = [asyncio.create_task(one(text)) for text in texts]
        try:
            return await asyncio.gather(*tasks)
        finally:
            # gather alone leaves sibling requests running after an exception.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self):
        try:
            if self._client is not None:
                await self._client.close()
        finally:
            self._api_key = ""


def create_embedder(agent, config):
    """Online embedding requires explicit configuration; no model is bundled."""
    from veadk.consts import (
        DEFAULT_MODEL_EMBEDDING_API_BASE,
        DEFAULT_MODEL_EMBEDDING_DIM,
        DEFAULT_MODEL_EMBEDDING_NAME,
    )

    if config.retrieval == "lexical":
        return None
    base = os.getenv("MODEL_EMBEDDING_API_BASE") or DEFAULT_MODEL_EMBEDDING_API_BASE
    key = os.getenv("MODEL_EMBEDDING_API_KEY")
    if not key:
        return None
    model = os.getenv("MODEL_EMBEDDING_NAME") or DEFAULT_MODEL_EMBEDDING_NAME
    dimension = int(os.getenv("MODEL_EMBEDDING_DIM") or DEFAULT_MODEL_EMBEDDING_DIM)
    return ArkContextEmbedding(
        model=model,
        dimension=dimension,
        api_key=key,
        api_base=base,
        max_calls=config.embedding_max_calls,
    )


class DefaultContextRetriever:
    """Lazy owner; the evaluated ranker handles full-source indexing and fallback."""

    def __init__(self, agent, config):
        self._agent = agent
        self._config = config
        self._ranker = None
        self._embedder = None
        self._initialized = False
        self._preparation_owner = None
        self.last_status = "not_requested"

    def _initialize(self):
        if self._initialized:
            return
        self._initialized = True
        self._embedder = create_embedder(self._agent, self._config)
        if self._embedder is None:
            self.last_status = "lexical"
            return
        path = Path(self._config.index_path)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # The derived index also contains source text. Preserve private file
        # permissions even when the project's .adk directory already exists.
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        self._ranker = AdaptiveContextRetriever(path, self._embedder)

    async def rank_with_deadline(self, *args, deadline):
        self._initialize()
        if self._ranker is None:
            from .lexical_retriever import rank_lexical

            self.last_status = "bm25"
            return await rank_lexical(*args, deadline=deadline)
        try:
            return await self._ranker.rank_with_deadline(*args, deadline=deadline)
        finally:
            self.last_status = self._ranker.last_status

    async def rank_search_with_deadline(self, *args, deadline):
        # Explicit source lookup retains lexical hit/miss semantics. Nearest
        # neighbours are useful for previews, but cannot prove a search hit.
        return []

    async def prepare_source(self, *args, deadline):
        """Use a separate invocation pool; preparation cannot spend query calls."""
        if not self._config.prepare_index:
            return {"complete": False, "reason": "disabled"}
        self._initialize()
        if self._ranker is None:
            return {"complete": False, "reason": "no_embedding"}
        if self._preparation_owner is None:
            self._preparation_owner = DefaultContextRetriever(
                self._agent,
                self._config.model_copy(
                    update={
                        "prepare_index": False,
                        "embedding_max_calls": self._config.index_preparation_max_calls,
                    }
                ),
            )
            self._preparation_owner._initialize()
        owner = self._preparation_owner
        if owner._ranker is None or (
            owner._embedder.model,
            owner._embedder.dimension,
        ) != (self._embedder.model, self._embedder.dimension):
            raise ValueError("embedding_version_changed")
        return await owner._ranker.prepare_source(*args, deadline=deadline)

    async def close(self):
        try:
            try:
                if self._preparation_owner is not None:
                    await self._preparation_owner.close()
            finally:
                if self._ranker is not None:
                    await self._ranker.close()
        finally:
            try:
                close = getattr(self._embedder, "close", None)
                if callable(close):
                    result = close()
                    if inspect.isawaitable(result):
                        await result
            finally:
                self._agent = None


@asynccontextmanager
async def invocation_retriever(agent, config):
    """No resources for short/off requests, no sharing across event loops."""
    if config.mode == "off":
        yield None
        return
    supplied = context_retriever.get()
    if supplied is not None:
        yield supplied
        return
    owner = DefaultContextRetriever(agent, config)
    try:
        yield owner
    finally:
        try:
            await owner.close()
        except Exception:
            # Optional index/client cleanup must not replace a business result
            # or its original exception. Do not log provider exception bodies.
            logger.warning("context_retrieval_cleanup_failed")
