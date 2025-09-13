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

from abc import ABC, abstractmethod

from pydantic import BaseModel


class BaseKnowledgebaseBackend(ABC, BaseModel):
    index: str
    """Index or collection name of the vector storage."""

    @abstractmethod
    def add_from_directory(self, directory: str, **kwargs) -> bool:
        """Add knowledge from file path to knowledgebase"""
        ...

    @abstractmethod
    def add_from_files(self, files: list[str], **kwargs) -> bool:
        """Add knowledge (e.g, documents, strings, ...) to knowledgebase"""
        ...

    @abstractmethod
    def add_from_text(self, text: str | list[str], **kwargs) -> bool:
        """Add knowledge from text to knowledgebase"""
        ...

    @abstractmethod
    def search(self, **kwargs) -> list:
        """Search knowledge from knowledgebase"""
        ...

    def delete(self, **kwargs) -> bool:
        """Delete knowledge from knowledgebase"""
        ...

    def list_docs(self, **kwargs) -> None:
        """List original documents in knowledgebase"""
        pass

    def list_chunks(self, **kwargs) -> None:
        """List embeded document chunks in knowledgebase"""
        pass
