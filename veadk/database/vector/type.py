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

from veadk.config import getenv


class Embeddings:
    def __init__(
        self,
        model: str = getenv("MODEL_EMBEDDING_NAME"),
        api_base: str = getenv("MODEL_EMBEDDING_API_BASE"),
        api_key: str = getenv("MODEL_EMBEDDING_API_KEY"),
        dim: int = int(getenv("MODEL_EMBEDDING_DIM")),
    ):
        self.model = model
        self.url = api_base
        self.api_key = api_key
        self.dim = dim

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        MAX_CHARS = 4000
        data = {"model": self.model, "input": [text[:MAX_CHARS] for text in texts]}
        response = requests.post(self.url, headers=self.headers, json=data)
        response.raise_for_status()
        result = response.json()
        return [item["embedding"] for item in result["data"]]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def get_embedding_dim(self) -> int:
        return self.dim
