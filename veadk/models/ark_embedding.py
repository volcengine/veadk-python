import os
from typing import Any, Dict, Optional, List, Union, Tuple
from enum import Enum

import httpx
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.callbacks.base import CallbackManager
from pydantic import PrivateAttr, Field
from volcenginesdkarkruntime import Ark, AsyncArk

from veadk.consts import DEFAULT_MODEL_EMBEDDING_NAME, DEFAULT_MODEL_EMBEDDING_API_BASE
from llama_index.embeddings.openai_like import OpenAILikeEmbedding


class ArkEmbeddingModel(str, Enum):
    DOUBAO_EMBEDDING_VISION_251215 = "doubao-embedding-vision-251215"
    DOUBAO_EMBEDDING_VISION_250615 = "doubao-embedding-vision-250615"


class ArkEmbedding(BaseEmbedding):
    additional_kwargs: Dict[str, Any] = Field(
        default_factory=dict, description="Additional kwargs for the Ark API."
    )

    api_key: str = Field(description="The Ark API key.")
    api_base: Optional[str] = Field(
        default=None, description="The base URL for Ark API."
    )
    max_retries: int = Field(default=10, description="Maximum number of retries.", ge=0)
    timeout: float = Field(default=60.0, description="Timeout for each request.", ge=0)
    default_headers: Optional[Dict[str, str]] = Field(
        default=None, description="The default headers for API requests."
    )
    reuse_client: bool = Field(
        default=True,
        description=(
            "Reuse the Ark client between requests. When doing anything with large "
            "volumes of async API calls, setting this to false can improve stability."
        ),
    )
    dimensions: Optional[int] = Field(
        default=None,
        description=(
            "The number of dimensions on the output embedding vectors. "
            "Works only with v3 embedding models."
        ),
    )

    _client: Optional[Ark] = PrivateAttr()
    _aclient: Optional[AsyncArk] = PrivateAttr()
    _http_client: Optional[httpx.Client] = PrivateAttr()
    _async_http_client: Optional[httpx.AsyncClient] = PrivateAttr()

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_EMBEDDING_NAME,
        embed_batch_size: int = 100,
        dimensions: Optional[int] = None,
        additional_kwargs: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        max_retries: int = 10,
        timeout: float = 60.0,
        reuse_client: bool = True,
        callback_manager: Optional[CallbackManager] = None,
        default_headers: Optional[Dict[str, str]] = None,
        http_client: Optional[httpx.Client] = None,
        async_http_client: Optional[httpx.AsyncClient] = None,
        num_workers: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        additional_kwargs = additional_kwargs or {}
        if dimensions is not None:
            additional_kwargs["dimensions"] = dimensions

        api_key, api_base = self._resolve_credentials(
            api_key=api_key,
            api_base=api_base,
        )

        super().__init__(
            embed_batch_size=embed_batch_size,
            dimensions=dimensions,
            callback_manager=callback_manager,
            model_name=model_name,
            additional_kwargs=additional_kwargs,
            api_key=api_key,
            api_base=api_base,
            max_retries=max_retries,
            reuse_client=reuse_client,
            timeout=timeout,
            default_headers=default_headers,
            num_workers=num_workers,
            **kwargs,
        )

        # 设置默认值
        if self.api_base is None:
            self.api_base = DEFAULT_MODEL_EMBEDDING_API_BASE

        self._client = None
        self._aclient = None
        self._http_client = http_client
        self._async_http_client = async_http_client

    def _resolve_credentials(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        if api_key is None:
            api_key = os.getenv("MODEL_EMBEDDING_API_KEY")
        if api_key is None:
            raise ValueError(
                "API key must be provided or set as MODEL_EMBEDDING_API_KEY environment variable"
            )

        return api_key, api_base

    def _get_credential_kwargs(self, is_async: bool = False) -> Dict[str, Any]:
        return {
            "api_key": self.api_key,
            "base_url": self.api_base,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "http_client": self._async_http_client if is_async else self._http_client,
        }

    def _get_client(self) -> Ark:
        if not self.reuse_client:
            return Ark(**self._get_credential_kwargs())
        if self._client is None:
            self._client = Ark(**self._get_credential_kwargs())
        return self._client

    def _get_aclient(self) -> AsyncArk:
        if not self.reuse_client:
            return AsyncArk(**self._get_credential_kwargs(is_async=True))
        if self._aclient is None:
            self._aclient = AsyncArk(**self._get_credential_kwargs(is_async=True))
        return self._aclient

    def _get_query_embedding(self, query: str) -> List[float]:
        """Get query embedding."""
        client = self._get_client()

        input_data = [{"type": "text", "text": query}]

        response = client.multimodal_embeddings.create(
            model=self.model_name, input=input_data, **self.additional_kwargs
        )

        return response.data.embedding

    async def _aget_query_embedding(self, query: str) -> List[float]:
        """The asynchronous version of _get_query_embedding."""
        aclient = self._get_aclient()

        input_data = [{"type": "text", "text": query}]

        response = await aclient.multimodal_embeddings.create(
            model=self.model_name, input=input_data, **self.additional_kwargs
        )

        return response.data.embedding

    def _get_text_embedding(self, text: str) -> List[float]:
        """Get text embedding."""
        client = self._get_client()

        input_data = [{"type": "text", "text": text}]

        response = client.multimodal_embeddings.create(
            model=self.model_name, input=input_data, **self.additional_kwargs
        )

        return response.data.embedding

    async def _aget_text_embedding(self, text: str) -> List[float]:
        """Asynchronously get text embedding."""
        aclient = self._get_aclient()

        input_data = [{"type": "text", "text": text}]

        response = await aclient.multimodal_embeddings.create(
            model=self.model_name, input=input_data, **self.additional_kwargs
        )

        return response.data.embedding

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get text embeddings for multiple texts.

        Simple loop implementation - Ark API requires one request per text.
        """
        if not texts:
            return []

        client = self._get_client()
        results = []

        for text in texts:
            single_input = [{"type": "text", "text": text}]
            response = client.multimodal_embeddings.create(
                model=self.model_name, input=single_input, **self.additional_kwargs
            )
            results.append(response.data.embedding)

        return results

    async def _aget_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Asynchronously get text embeddings for multiple texts.

        Simple async loop implementation - Ark API requires one request per text.
        """
        if not texts:
            return []

        aclient = self._get_aclient()
        results = []

        for text in texts:
            single_input = [{"type": "text", "text": text}]
            response = await aclient.multimodal_embeddings.create(
                model=self.model_name, input=single_input, **self.additional_kwargs
            )
            results.append(response.data.embedding)

        return results

    def get_text_embedding(self, text: str) -> List[float]:
        """公共接口：获取文本嵌入"""
        return self._get_text_embedding(text)

    async def aget_text_embedding(self, text: str) -> List[float]:
        """公共接口：异步获取文本嵌入"""
        return await self._aget_text_embedding(text)

    def get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Public interface: batch text embedding"""
        return self._get_text_embeddings(texts)

    async def aget_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Public interface: async batch text embedding"""
        return await self._aget_text_embeddings(texts)

    def get_query_embedding(self, query: str) -> List[float]:
        """Public interface: get query embedding"""
        return self._get_query_embedding(query)

    async def aget_query_embedding(self, query: str) -> List[float]:
        """Public interface: async get query embedding"""
        return await self._aget_query_embedding(query)


# Independent factory function
def create_embedding_model(
    model_name: str,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs: Any,
) -> Union["ArkEmbedding", "OpenAILikeEmbedding"]:
    """
    Factory function: smart embedding model creation by model name

    Args:
        model_name: Model name
        api_key: API key
        api_base: API base URL
        **kwargs: Other parameters

    Returns:
        Suitable embedding model instance (ArkEmbedding or OpenAILikeEmbedding)
    """
    # Ark supported model list
    ark_models = {"doubao-embedding-vision-250615", "doubao-embedding-vision-251215"}

    # Check if it's Ark supported model
    if model_name in ark_models:
        return ArkEmbedding(
            model_name=model_name, api_key=api_key, api_base=api_base, **kwargs
        )
    else:
        # Use OpenAILikeEmbedding
        from llama_index.embeddings.openai_like import OpenAILikeEmbedding

        return OpenAILikeEmbedding(
            model_name=model_name, api_key=api_key, api_base=api_base, **kwargs
        )

    @classmethod
    def class_name(cls) -> str:
        return "ArkEmbedding"
