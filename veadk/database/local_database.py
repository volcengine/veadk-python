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

from .base_database import BaseDatabase


class LocalDataBase(BaseDatabase):
    """This database is only for basic demonstration.
    It does not support the vector search function, and the `search` function will return all data.
    """

    def __init__(self, **kwargs):
        super().__init__()
        self.data = {}
        self._type = "local"
        self._next_id = 0  # Used to generate unique IDs

    def add_texts(self, texts: list[str], **kwargs):
        for text in texts:
            self.data[str(self._next_id)] = text
            self._next_id += 1

    def is_empty(self):
        return len(self.data) == 0

    def query(self, query: str, **kwargs: Any) -> list[str]:
        return list(self.data.values())

    def delete(self, **kwargs: Any):
        self.data = {}

    def add(self, texts: list[str], **kwargs: Any):
        return self.add_texts(texts)

    def list_docs(self, **kwargs: Any) -> list[dict]:
        return [{"id": id, "content": content} for id, content in self.data.items()]

    def delete_doc(self, id: str, **kwargs: Any):
        if id not in self.data:
            raise ValueError(f"id {id} not found")
        try:
            del self.data[id]
            return True
        except Exception:
            return False
