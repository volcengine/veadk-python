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
import io
import os.path
from typing import Any, BinaryIO, Literal, TextIO

from pydantic import BaseModel

from veadk.database.database_adapter import get_knowledgebase_database_adapter
from veadk.database.database_factory import DatabaseFactory
from veadk.utils.misc import formatted_timestamp
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def build_knowledgebase_index(app_name: str):
    return f"veadk_kb_{app_name}"


class KnowledgeBase(BaseModel):
    backend: Literal["local", "opensearch", "viking", "redis", "mysql"] = "local"
    top_k: int = 10
    db_config: Any | None = None

    def model_post_init(self, __context: Any) -> None:
        logger.info(
            f"Initializing knowledgebase: backend={self.backend} top_k={self.top_k}"
        )

        self._db_client = DatabaseFactory.create(
            backend=self.backend, config=self.db_config
        )
        self._adapter = get_knowledgebase_database_adapter(self._db_client)

        logger.info(
            f"Initialized knowledgebase: db_client={self._db_client.__class__.__name__} adapter={self._adapter}"
        )

    def add(
        self,
        data: str | list[str] | TextIO | BinaryIO | bytes,
        app_name: str,
        **kwargs,
    ):
        """
        Add documents to the vector database.
        Args:
            data (str | list[str] | TextIO | BinaryIO | bytes): The data to be added.
                - str: A single file path. (viking only)
                - list[str]: A list of file paths.
                - TextIO: A file object (TextIO). (viking only) file descriptor
                - BinaryIO: A file object (BinaryIO). (viking only) file descriptor
                - bytes: Binary data. (viking only) binary data (f.read())
            app_name: index name
            **kwargs: Additional keyword arguments.
                - file_name (str | list[str]): The file name or a list of file names (including suffix). (viking only)
        """
        if self.backend != "viking" and not (
            isinstance(data, str) or isinstance(data, list)
        ):
            raise ValueError(
                "Only vikingdb supports uploading files or file characters."
            )

        index = build_knowledgebase_index(app_name)
        logger.info(f"Adding documents to knowledgebase: index={index}")

        if self.backend == "viking":
            # Case 1: Handling file paths or lists of file paths (str)
            if isinstance(data, str) and os.path.isfile(data):
                # Get the file name (including the suffix)
                if "file_name" not in kwargs or not kwargs["file_name"]:
                    kwargs["file_name"] = os.path.basename(data)
                return self._adapter.add(data=data, index=index, **kwargs)
            # Case 2: Handling when list[str] is a full path  (list[str])
            if isinstance(data, list):
                if all(isinstance(item, str) for item in data):
                    all_paths = all(os.path.isfile(item) for item in data)
                    all_not_paths = all(not os.path.isfile(item) for item in data)
                    if all_paths:
                        if "file_name" not in kwargs or not kwargs["file_name"]:
                            kwargs["file_name"] = [
                                os.path.basename(item) for item in data
                            ]
                        return self._adapter.add(data=data, index=index, **kwargs)
                    elif (
                        not all_not_paths
                    ):  # Prevent the occurrence of non-existent paths
                        # There is a mixture of paths and non-paths
                        raise ValueError(
                            "Mixed file paths and content strings in list are not allowed"
                        )
            # Case 3: Handling strings or string arrays (content)  (str or list[str])
            if isinstance(data, str) or (
                isinstance(data, list) and all(isinstance(item, str) for item in data)
            ):
                if "file_name" not in kwargs or not kwargs["file_name"]:
                    if isinstance(data, str):
                        kwargs["file_name"] = f"{formatted_timestamp()}.txt"
                    else:  # list[str] without file_names
                        prefix_file_name = formatted_timestamp()
                        kwargs["file_name"] = [
                            f"{prefix_file_name}_{i}.txt" for i in range(len(data))
                        ]
                return self._adapter.add(data=data, index=index, **kwargs)

            # Case 4: Handling binary data (bytes)
            if isinstance(data, bytes):
                # user must give file_name
                if "file_name" not in kwargs:
                    raise ValueError("file_name must be provided for binary data")
                return self._adapter.add(data=data, index=index, **kwargs)

            # Case 5: Handling file objects TextIO or BinaryIO
            if isinstance(data, (io.TextIOWrapper, io.BufferedReader)):
                if not kwargs.get("file_name") and hasattr(data, "name"):
                    kwargs["file_name"] = os.path.basename(data.name)
                return self._adapter.add(data=data, index=index, **kwargs)
            # Case6: Unsupported data type
            raise TypeError(f"Unsupported data type: {type(data)}")

        if isinstance(data, list):
            raise TypeError(
                f"Unsupported data type: {type(data)}, Only viking support file_path and file bytes"
            )
        # not viking
        return self._adapter.add(data=data, index=index, **kwargs)

    def search(self, query: str, app_name: str, top_k: int | None = None) -> list[str]:
        top_k = self.top_k if top_k is None else top_k

        logger.info(
            f"Searching knowledgebase: app_name={app_name} query={query} top_k={top_k}"
        )
        index = build_knowledgebase_index(app_name)
        result = self._adapter.query(query=query, index=index, top_k=top_k)
        if len(result) == 0:
            logger.warning(f"No documents found in knowledgebase. Query: {query}")
        return result

    def delete(self, app_name: str) -> bool:
        index = build_knowledgebase_index(app_name)
        return self.adapter.delete(index=index)

    def delete_doc(self, app_name: str, id: str) -> bool:
        index = build_knowledgebase_index(app_name)
        return self._adapter.delete_doc(index=index, id=id)

    def list_docs(self, app_name: str, offset: int = 0, limit: int = 100) -> list[dict]:
        index = build_knowledgebase_index(app_name)
        return self._adapter.list_chunks(index=index, offset=offset, limit=limit)
