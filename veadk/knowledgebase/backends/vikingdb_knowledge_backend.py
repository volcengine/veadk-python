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

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Literal

import requests
from pydantic import Field
from typing_extensions import override

import veadk.config  # noqa E401
from veadk.config import getenv
from veadk.configs.database_configs import NormalTOSConfig, TOSConfig
from veadk.knowledgebase.backends.base_backend import BaseKnowledgebaseBackend
from veadk.knowledgebase.backends.utils import build_vikingdb_knowledgebase_request
from veadk.knowledgebase.entry import KnowledgebaseEntry
from veadk.utils.logger import get_logger
from veadk.utils.misc import formatted_timestamp

try:
    from veadk.integrations.ve_tos.ve_tos import VeTOS
except ImportError:
    raise ImportError(
        "Please install VeADK extensions\npip install veadk-python[extensions]"
    )

logger = get_logger(__name__)


def _read_file_to_bytes(file_path: str) -> tuple[bytes, str]:
    """Read file content to bytes, and file name"""
    with open(file_path, "rb") as f:
        file_content = f.read()
    file_name = file_path.split("/")[-1]
    return file_content, file_name


def get_files_in_directory(directory: str):
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise ValueError(f"The directory does not exist: {directory}")
    file_paths = [str(file) for file in dir_path.iterdir() if file.is_file()]
    return file_paths


class VikingDBKnowledgeBackend(BaseKnowledgebaseBackend):
    volcengine_access_key: str = Field(
        default_factory=lambda: getenv("VOLCENGINE_ACCESS_KEY")
    )

    volcengine_secret_key: str = Field(
        default_factory=lambda: getenv("VOLCENGINE_SECRET_KEY")
    )

    volcengine_project: str = "default"
    """VikingDB knowledgebase project in Volcengine console platform. Default by `default`"""

    region: str = "cn-beijing"
    """VikingDB knowledgebase region"""

    tos_config: TOSConfig | NormalTOSConfig = Field(default_factory=TOSConfig)
    """TOS config, used to upload files to TOS"""

    def precheck_index_naming(self):
        if not (
            isinstance(self.index, str)
            and 0 < len(self.index) <= 128
            and re.fullmatch(r"^[a-zA-Z][a-zA-Z0-9_]*$", self.index)
        ):
            raise ValueError(
                "The index name does not conform to the rules: "
                "it must start with an English letter, contain only letters, numbers, and underscores, and have a length of 1-128."
            )

    def model_post_init(self, __context: Any) -> None:
        self.precheck_index_naming()

        # check whether collection exist, if not, create it
        if not self.collection_status()["existed"]:
            logger.warning(
                f"VikingDB knowledgebase collection {self.index} does not exist, please create it first..."
            )

        self._tos_client = VeTOS(
            ak=self.volcengine_access_key,
            sk=self.volcengine_secret_key,
            region=self.tos_config.region,
            bucket_name=self.tos_config.bucket,
        )

    @override
    def add_from_directory(
        self,
        directory: str,
        tos_bucket_name: str | None = None,
        tos_bucket_path: str = "knowledgebase",
        metadata: dict | None = None,
        **kwargs,
    ) -> bool:
        """Add knowledge from a directory to the knowledgebase.

        Args:
            directory (str): The directory to add to knowledgebase.
            tos_bucket_name (str | None, optional): The bucket name of TOS. Defaults to None.
            tos_bucket_path (str, optional): The path of TOS bucket. Defaults to "knowledgebase".
            metadata (dict | None, optional): The metadata of the files. Defaults to None.
            **kwargs: Additional keyword arguments.

        Returns:
            bool: True if successful, False otherwise.
        """
        tos_bucket_name = tos_bucket_name or self.tos_config.bucket
        files = get_files_in_directory(directory=directory)
        for _file in files:
            content, file_name = _read_file_to_bytes(_file)
            tos_url = self._upload_bytes_to_tos(
                content,
                tos_bucket_name=tos_bucket_name,
                object_key=f"{tos_bucket_path}/{file_name}",
                metadata=metadata,
            )
            self._add_doc(tos_url=tos_url)
        return True

    @override
    def add_from_files(
        self,
        files: list[str],
        tos_bucket_name: str | None = None,
        tos_bucket_path: str = "knowledgebase",
        metadata: dict | None = None,
        **kwargs,
    ) -> bool:
        """Add knowledge from a directory to the knowledgebase.

        Args:
            files (list[str]): The files to add to knowledgebase.
            tos_bucket_name (str | None, optional): The bucket name of TOS. Defaults to None.
            tos_bucket_path (str, optional): The path of TOS bucket. Defaults to "knowledgebase".
            metadata (dict | None, optional): The metadata of the files. Defaults to None.
            **kwargs: Additional keyword arguments.

        Returns:
            bool: True if successful, False otherwise.
        """
        tos_bucket_name = tos_bucket_name or self.tos_config.bucket
        for _file in files:
            content, file_name = _read_file_to_bytes(_file)
            tos_url = self._upload_bytes_to_tos(
                content,
                tos_bucket_name=tos_bucket_name,
                object_key=f"{tos_bucket_path}/{file_name}",
                metadata=metadata,
            )
            self._add_doc(tos_url=tos_url)
        return True

    @override
    def add_from_text(
        self,
        text: str | list[str],
        tos_bucket_name: str | None = None,
        tos_bucket_path: str = "knowledgebase",
        metadata: dict | None = None,
        **kwargs,
    ) -> bool:
        """Add knowledge from text to the knowledgebase.

        Args:
            text (str | list[str]): The text to add to knowledgebase.
            tos_bucket_name (str | None, optional): The bucket name of TOS. Defaults to None.
            tos_bucket_path (str, optional): The path of TOS bucket. Defaults to "knowledgebase".

        Returns:
            bool: True if successful, False otherwise.
        """
        tos_bucket_name = tos_bucket_name or self.tos_config.bucket
        if isinstance(text, list):
            object_keys = kwargs.get(
                "tos_object_keys",
                [
                    f"{tos_bucket_path}/{formatted_timestamp()}-{i}.txt"
                    for i, _ in enumerate(text)
                ],
            )
            for _text, _object_key in zip(text, object_keys):
                _content = _text.encode("utf-8")
                tos_url = self._upload_bytes_to_tos(
                    _content, tos_bucket_name, _object_key, metadata=metadata
                )
                self._add_doc(tos_url=tos_url)
            return True
        elif isinstance(text, str):
            content = text.encode("utf-8")
            object_key = kwargs.get(
                "object_key", f"veadk/knowledgebase/{formatted_timestamp()}.txt"
            )
            tos_url = self._upload_bytes_to_tos(
                content, tos_bucket_name, object_key, metadata=metadata
            )
            self._add_doc(tos_url=tos_url)
        else:
            raise ValueError("text must be str or list[str]")
        return True

    def add_from_bytes(
        self,
        content: bytes,
        file_name: str,
        tos_bucket_name: str | None = None,
        tos_bucket_path: str = "knowledgebase",
        metadata: dict | None = None,
        **kwargs,
    ) -> bool:
        """Add knowledge from bytes to the knowledgebase.

        Args:
            content (bytes): The content to add to knowledgebase.
            file_name (str): The file name of the content.
            tos_bucket_name (str | None, optional): The bucket name of TOS. Defaults to None.
            tos_bucket_path (str, optional): The path of TOS bucket. Defaults to "knowledgebase".
            metadata (dict | None, optional): The metadata of the files. Defaults to None.
            **kwargs: Additional keyword arguments.

        Returns:
            bool: True if successful, False otherwise.
        """
        tos_bucket_name = tos_bucket_name or self.tos_config.bucket
        tos_url = self._upload_bytes_to_tos(
            content,
            tos_bucket_name=tos_bucket_name,
            object_key=f"{tos_bucket_path}/{file_name}",
            metadata=metadata,
        )
        response = self._add_doc(tos_url=tos_url)
        if response["code"] == 0:
            return True
        return False

    @override
    def search(
        self,
        query: str,
        top_k: int = 5,
        metadata: dict | None = None,
        rerank: bool = True,
    ) -> list:
        return self._search_knowledge(
            query=query, top_k=top_k, metadata=metadata, rerank=rerank
        )

    def delete_collection(self) -> bool:
        DELETE_COLLECTION_PATH = "/api/knowledge/collection/delete"

        response = self._do_request(
            body={
                "name": self.index,
                "project": self.volcengine_project,
            },
            path=DELETE_COLLECTION_PATH,
            method="POST",
        )

        if response.get("code") != 0:
            logger.error(f"Error during collection deletion: {response}")
            return False
        return True

    def delete_doc_by_id(self, id: str) -> bool:
        DELETE_DOC_PATH = "/api/knowledge/doc/delete"
        response = self._do_request(
            body={
                "collection_name": self.index,
                "project": self.volcengine_project,
                "doc_id": id,
            },
            path=DELETE_DOC_PATH,
            method="POST",
        )

        if response.get("code") != 0:
            return False
        return True

    def list_docs(self, offset: int = 0, limit: int = -1):
        """List documents in collection.

        Args:
            offset (int): The offset of the first document to return.
            limit (int): The maximum number of documents to return. -1 means return all documents but max is 100.
        """
        LIST_DOCS_PATH = "/api/knowledge/doc/list"
        response = self._do_request(
            body={
                "collection_name": self.index,
                "project": self.volcengine_project,
                "offset": offset,
                "limit": limit,
            },
            path=LIST_DOCS_PATH,
            method="POST",
        )
        if response.get("code") != 0:
            raise ValueError(f"Error during list documents: {response.get('code')}")
        if not response["data"].get("doc_list", []):
            return []
        return response["data"]["doc_list"]

    def list_chunks(self, offset: int = 0, limit: int = -1):
        """List chunks in collection.

        Args:
            offset (int): The offset of the first chunk to return.
            limit (int): The maximum number of chunks to return. -1 means return all chunks but max is 100.
        """
        LIST_CHUNKS_PATH = "/api/knowledge/point/list"
        response = self._do_request(
            body={
                "collection_name": self.index,
                "project": self.volcengine_project,
                "offset": offset,
                "limit": limit,
            },
            path=LIST_CHUNKS_PATH,
            method="POST",
        )

        if response.get("code") != 0:
            raise ValueError(f"Error during list chunks: {response}")

        if not response["data"].get("point_list", []):
            return []
        data = [
            {
                "id": res["point_id"],
                "content": res["content"],
                "metadata": res["doc_info"],
            }
            for res in response["data"]["point_list"]
        ]
        return data

    def collection_status(self):
        COLLECTION_INFO_PATH = "/api/knowledge/collection/info"
        response = self._do_request(
            body={
                "name": self.index,
                "project": self.volcengine_project,
            },
            path=COLLECTION_INFO_PATH,
            method="POST",
        )
        if response["code"] == 0:
            status = response["data"]["pipeline_list"][0]["index_list"][0]["status"]
            return {
                "existed": True,
                "status": status,
            }
        elif response["code"] == 1000005:
            return {
                "existed": False,
                "status": None,
            }
        else:
            raise ValueError(f"Error during collection status: {response}")

    def create_collection(self) -> None:
        CREATE_COLLECTION_PATH = "/api/knowledge/collection/create"

        response = self._do_request(
            body={
                "name": self.index,
                "project": self.volcengine_project,
                "description": "Created by Volcengine Agent Development Kit (VeADK).",
            },
            path=CREATE_COLLECTION_PATH,
            method="POST",
        )

        if response.get("code") != 0:
            raise ValueError(
                f"Error during collection creation: {response.get('code')}"
            )

    def _upload_bytes_to_tos(
        self,
        content: bytes,
        tos_bucket_name: str,
        object_key: str,
        metadata: dict | None = None,
    ) -> str:
        # Here, we set the metadata via the TOS object, ref: https://www.volcengine.com/docs/84313/1254624
        self._tos_client.bucket_name = tos_bucket_name
        coro = self._tos_client.upload(
            object_key=object_key,
            bucket_name=tos_bucket_name,
            data=content,
            metadata=metadata,
        )
        try:
            loop = asyncio.get_running_loop()
            loop.run_until_complete(
                coro
            ) if not loop.is_running() else asyncio.ensure_future(coro)
        except RuntimeError:
            asyncio.run(coro)
        return f"{self._tos_client.bucket_name}/{object_key}"

    def _add_doc(self, tos_url: str) -> Any:
        ADD_DOC_PATH = "/api/knowledge/doc/add"

        response = self._do_request(
            body={
                "collection_name": self.index,
                "project": self.volcengine_project,
                "add_type": "tos",
                "tos_path": tos_url,
            },
            path=ADD_DOC_PATH,
            method="POST",
        )
        return response

    def _search_knowledge(
        self,
        query: str,
        top_k: int = 5,
        metadata: dict | None = None,
        rerank: bool = True,
        chunk_diffusion_count: int | None = 3,
    ) -> list[KnowledgebaseEntry]:
        SEARCH_KNOWLEDGE_PATH = "/api/knowledge/collection/search_knowledge"

        query_param = (
            {
                "doc_filter": {
                    "op": "and",
                    "conds": [
                        {"op": "must", "field": str(k), "conds": [str(v)]}
                        for k, v in metadata.items()
                    ],
                }
            }
            if metadata
            else None
        )

        post_precessing = {
            "rerank_swich": rerank,
            "chunk_diffusion_count": chunk_diffusion_count,
        }

        response = self._do_request(
            body={
                "name": self.index,
                "project": self.volcengine_project,
                "query": query,
                "limit": top_k,
                "query_param": query_param,
                "post_processing": post_precessing,
            },
            path=SEARCH_KNOWLEDGE_PATH,
            method="POST",
        )

        if response.get("code") != 0:
            raise ValueError(
                f"Error during knowledge search: {response.get('code')}, message: {response.get('message')}"
            )

        entries = []
        for result in response.get("data", {}).get("result_list", []):
            doc_meta_raw_str = result.get("doc_info", {}).get("doc_meta")
            doc_meta_list = json.loads(doc_meta_raw_str) if doc_meta_raw_str else []
            metadata = {}
            for meta in doc_meta_list:
                metadata[meta["field_name"]] = meta["field_value"]

            entries.append(
                KnowledgebaseEntry(content=result.get("content", ""), metadata=metadata)
            )

        return entries

    def _do_request(
        self,
        body: dict,
        path: str,
        method: Literal["GET", "POST", "PUT", "DELETE"] = "POST",
    ) -> dict:
        VIKINGDB_KNOWLEDGEBASE_BASE_URL = "api-knowledgebase.mlp.cn-beijing.volces.com"

        request = build_vikingdb_knowledgebase_request(
            path=path,
            volcengine_access_key=self.volcengine_access_key,
            volcengine_secret_key=self.volcengine_secret_key,
            method=method,
            data=body,
        )
        response = requests.request(
            method=method,
            url=f"https://{VIKINGDB_KNOWLEDGEBASE_BASE_URL}{path}",
            headers=request.headers,
            data=request.body,
        )
        if not response.ok:
            logger.error(
                f"VikingDBKnowledgeBackend error during request: {response.json()}"
            )
        return response.json()
