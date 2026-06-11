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

"""Unit tests for ``veadk.models.ark_embedding``.

Credential resolution, client construction, and the (a)sync embedding calls
are covered with the Ark SDK (`Ark`/`AsyncArk`) fully mocked. The
``create_embedding_model`` factory's routing is verified for both branches.
No network or live Ark access is required.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from veadk.consts import (
    DEFAULT_MODEL_EMBEDDING_API_BASE,
    DEFAULT_MODEL_EMBEDDING_NAME,
)
from veadk.models import ark_embedding
from veadk.models.ark_embedding import (
    ArkEmbedding,
    ArkEmbeddingModel,
    create_embedding_model,
)


def _embedding_response(vector):
    """Mimic ``client.multimodal_embeddings.create(...)`` -> ``.data.embedding``."""
    resp = MagicMock()
    resp.data.embedding = vector
    return resp


# --------------------------------------------------------------------------
# enum / class_name
# --------------------------------------------------------------------------
def test_ark_embedding_model_enum_values():
    assert (
        ArkEmbeddingModel.DOUBAO_EMBEDDING_VISION_251215
        == "doubao-embedding-vision-251215"
    )
    assert (
        ArkEmbeddingModel.DOUBAO_EMBEDDING_VISION_250615
        == "doubao-embedding-vision-250615"
    )


def test_class_name():
    assert ArkEmbedding.class_name() == "ArkEmbedding"


# --------------------------------------------------------------------------
# credential resolution
# --------------------------------------------------------------------------
def test_explicit_api_key_takes_precedence():
    emb = ArkEmbedding(api_key="explicit-key")
    assert emb.api_key == "explicit-key"
    # default model + default base applied
    assert emb.model_name == DEFAULT_MODEL_EMBEDDING_NAME
    assert emb.api_base == DEFAULT_MODEL_EMBEDDING_API_BASE


def test_api_key_resolved_from_env(monkeypatch):
    monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "env-key")
    emb = ArkEmbedding()
    assert emb.api_key == "env-key"


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    with pytest.raises(ValueError, match="MODEL_EMBEDDING_API_KEY"):
        ArkEmbedding()


def test_custom_api_base_preserved():
    emb = ArkEmbedding(api_key="k", api_base="https://custom.example/")
    assert emb.api_base == "https://custom.example/"


def test_dimensions_propagates_to_additional_kwargs():
    emb = ArkEmbedding(api_key="k", dimensions=256)
    assert emb.dimensions == 256
    assert emb.additional_kwargs["dimensions"] == 256


# --------------------------------------------------------------------------
# client construction / reuse
# --------------------------------------------------------------------------
def test_get_credential_kwargs_shape():
    emb = ArkEmbedding(api_key="k", api_base="https://b/", timeout=12.0, max_retries=3)
    kwargs = emb._get_credential_kwargs()
    assert kwargs["api_key"] == "k"
    assert kwargs["base_url"] == "https://b/"
    assert kwargs["timeout"] == 12.0
    assert kwargs["max_retries"] == 3
    assert kwargs["http_client"] is None


def test_get_credential_kwargs_async_uses_async_http_client():
    emb = ArkEmbedding(api_key="k")
    sync_kwargs = emb._get_credential_kwargs(is_async=False)
    async_kwargs = emb._get_credential_kwargs(is_async=True)
    assert sync_kwargs["http_client"] is emb._http_client
    assert async_kwargs["http_client"] is emb._async_http_client


def test_get_client_reuses_when_reuse_client_true():
    emb = ArkEmbedding(api_key="k", reuse_client=True)
    with patch.object(ark_embedding, "Ark", return_value=MagicMock()) as ctor:
        c1 = emb._get_client()
        c2 = emb._get_client()
    assert c1 is c2
    ctor.assert_called_once()


def test_get_client_fresh_when_reuse_client_false():
    emb = ArkEmbedding(api_key="k", reuse_client=False)
    with patch.object(
        ark_embedding, "Ark", side_effect=lambda **_: MagicMock()
    ) as ctor:
        c1 = emb._get_client()
        c2 = emb._get_client()
    assert c1 is not c2
    assert ctor.call_count == 2


def test_get_aclient_reuses_when_reuse_client_true():
    emb = ArkEmbedding(api_key="k", reuse_client=True)
    with patch.object(ark_embedding, "AsyncArk", return_value=MagicMock()) as ctor:
        a1 = emb._get_aclient()
        a2 = emb._get_aclient()
    assert a1 is a2
    ctor.assert_called_once()


# --------------------------------------------------------------------------
# sync embedding calls
# --------------------------------------------------------------------------
def test_get_text_embedding_builds_request_and_parses_response():
    emb = ArkEmbedding(api_key="k", model_name="doubao-embedding-vision-250615")
    fake_client = MagicMock()
    fake_client.multimodal_embeddings.create.return_value = _embedding_response(
        [0.1, 0.2]
    )

    with patch.object(emb, "_get_client", return_value=fake_client):
        result = emb.get_text_embedding("hello")

    assert result == [0.1, 0.2]
    _, kwargs = fake_client.multimodal_embeddings.create.call_args
    assert kwargs["model"] == "doubao-embedding-vision-250615"
    assert kwargs["input"] == [{"type": "text", "text": "hello"}]


def test_get_query_embedding_builds_request():
    emb = ArkEmbedding(api_key="k")
    fake_client = MagicMock()
    fake_client.multimodal_embeddings.create.return_value = _embedding_response([1.0])

    with patch.object(emb, "_get_client", return_value=fake_client):
        result = emb.get_query_embedding("q")

    assert result == [1.0]
    _, kwargs = fake_client.multimodal_embeddings.create.call_args
    assert kwargs["input"] == [{"type": "text", "text": "q"}]


def test_get_text_embeddings_loops_per_text():
    emb = ArkEmbedding(api_key="k")
    fake_client = MagicMock()
    fake_client.multimodal_embeddings.create.side_effect = [
        _embedding_response([1.0]),
        _embedding_response([2.0]),
    ]

    with patch.object(emb, "_get_client", return_value=fake_client):
        result = emb.get_text_embeddings(["a", "b"])

    assert result == [[1.0], [2.0]]
    assert fake_client.multimodal_embeddings.create.call_count == 2


def test_get_text_embeddings_empty_returns_empty_without_client_call():
    emb = ArkEmbedding(api_key="k")
    with patch.object(emb, "_get_client") as get_client:
        assert emb.get_text_embeddings([]) == []
    get_client.assert_not_called()


def test_additional_kwargs_forwarded_to_create():
    emb = ArkEmbedding(api_key="k", dimensions=64)
    fake_client = MagicMock()
    fake_client.multimodal_embeddings.create.return_value = _embedding_response([0.0])

    with patch.object(emb, "_get_client", return_value=fake_client):
        emb.get_text_embedding("x")

    _, kwargs = fake_client.multimodal_embeddings.create.call_args
    assert kwargs["dimensions"] == 64


# --------------------------------------------------------------------------
# async embedding calls
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_aget_text_embedding():
    emb = ArkEmbedding(api_key="k")
    fake_aclient = MagicMock()
    fake_aclient.multimodal_embeddings.create = AsyncMock(
        return_value=_embedding_response([0.5, 0.6])
    )

    with patch.object(emb, "_get_aclient", return_value=fake_aclient):
        result = await emb.aget_text_embedding("hi")

    assert result == [0.5, 0.6]
    _, kwargs = fake_aclient.multimodal_embeddings.create.call_args
    assert kwargs["input"] == [{"type": "text", "text": "hi"}]


@pytest.mark.asyncio
async def test_aget_query_embedding():
    emb = ArkEmbedding(api_key="k")
    fake_aclient = MagicMock()
    fake_aclient.multimodal_embeddings.create = AsyncMock(
        return_value=_embedding_response([9.0])
    )

    with patch.object(emb, "_get_aclient", return_value=fake_aclient):
        result = await emb.aget_query_embedding("q")

    assert result == [9.0]


@pytest.mark.asyncio
async def test_aget_text_embeddings_loops():
    emb = ArkEmbedding(api_key="k")
    fake_aclient = MagicMock()
    fake_aclient.multimodal_embeddings.create = AsyncMock(
        side_effect=[_embedding_response([1.0]), _embedding_response([2.0])]
    )

    with patch.object(emb, "_get_aclient", return_value=fake_aclient):
        result = await emb.aget_text_embeddings(["a", "b"])

    assert result == [[1.0], [2.0]]
    assert fake_aclient.multimodal_embeddings.create.call_count == 2


@pytest.mark.asyncio
async def test_aget_text_embeddings_empty_returns_empty():
    emb = ArkEmbedding(api_key="k")
    with patch.object(emb, "_get_aclient") as get_aclient:
        assert await emb.aget_text_embeddings([]) == []
    get_aclient.assert_not_called()


# --------------------------------------------------------------------------
# factory
# --------------------------------------------------------------------------
def test_create_embedding_model_routes_to_ark_for_doubao():
    model = create_embedding_model(
        model_name="doubao-embedding-vision-250615", api_key="k"
    )
    assert isinstance(model, ArkEmbedding)
    assert model.model_name == "doubao-embedding-vision-250615"


def test_create_embedding_model_routes_to_openai_like_for_other():
    fake_instance = object()
    with patch(
        "llama_index.embeddings.openai_like.OpenAILikeEmbedding",
        return_value=fake_instance,
    ) as ctor:
        model = create_embedding_model(
            model_name="text-embedding-3-small",
            api_key="k",
            api_base="https://api.openai.com/v1",
        )
    assert model is fake_instance
    ctor.assert_called_once()
    _, kwargs = ctor.call_args
    assert kwargs["model_name"] == "text-embedding-3-small"


def test_environ_default_does_not_leak(monkeypatch):
    # Constructing with an explicit key must not depend on the env var.
    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    emb = ArkEmbedding(api_key="explicit")
    assert emb.api_key == "explicit"
    assert os.getenv("MODEL_EMBEDDING_API_KEY") is None
