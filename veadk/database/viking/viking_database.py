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
import json
import os
import uuid
from typing import Any, BinaryIO, Literal, TextIO

import requests
import tos
from pydantic import BaseModel, Field
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request
from volcengine.Credentials import Credentials

from veadk.config import getenv
from veadk.database.base_database import BaseDatabase
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# knowledge base domain
g_knowledge_base_domain = "api-knowledgebase.mlp.cn-beijing.volces.com"
# paths
create_collection_path = "/api/knowledge/collection/create"
search_knowledge_path = "/api/knowledge/collection/search_knowledge"
list_collections_path = "/api/knowledge/collection/list"
get_collections_path = "/api/knowledge/collection/info"
doc_del_path = "/api/knowledge/collection/delete"
doc_add_path = "/api/knowledge/doc/add"
doc_info_path = "/api/knowledge/doc/info"
list_point_path = "/api/knowledge/point/list"
list_docs_path = "/api/knowledge/doc/list"
delete_docs_path = "/api/knowledge/point/delete"


class VolcengineTOSConfig(BaseModel):
    endpoint: str = Field(
        default_factory=lambda: getenv(
            "DATABASE_TOS_ENDPOINT", "tos-cn-beijing.volces.com"
        ),
        description="VikingDB TOS endpoint",
    )
    region: str = Field(
        default_factory=lambda: getenv("DATABASE_TOS_REGION", "cn-beijing"),
        description="VikingDB TOS region",
    )
    bucket: str = Field(
        default_factory=lambda: getenv("DATABASE_TOS_BUCKET"),
        description="VikingDB TOS bucket",
    )
    base_key: str = Field(
        default="veadk",
        description="VikingDB TOS base key",
    )


class VikingDatabaseConfig(BaseModel):
    volcengine_ak: str = Field(
        default_factory=lambda: getenv("VOLCENGINE_ACCESS_KEY"),
        description="VikingDB access key",
    )
    volcengine_sk: str = Field(
        default_factory=lambda: getenv("VOLCENGINE_SECRET_KEY"),
        description="VikingDB secret key",
    )
    project: str = Field(
        default_factory=lambda: getenv("DATABASE_VIKING_PROJECT"),
        description="VikingDB project name",
    )
    region: str = Field(
        default_factory=lambda: getenv("DATABASE_VIKING_REGION"),
        description="VikingDB region",
    )
    tos: VolcengineTOSConfig = Field(
        default_factory=VolcengineTOSConfig,
        description="VikingDB TOS configuration",
    )


def prepare_request(
    method, path, config: VikingDatabaseConfig, params=None, data=None, doseq=0
):
    ak = config.volcengine_ak
    sk = config.volcengine_sk

    if params:
        for key in params:
            if (
                type(params[key]) is int
                or type(params[key]) is float
                or type(params[key]) is bool
            ):
                params[key] = str(params[key])
            elif type(params[key]) is list:
                if not doseq:
                    params[key] = ",".join(params[key])
    r = Request()
    r.set_shema("https")
    r.set_method(method)
    r.set_connection_timeout(10)
    r.set_socket_timeout(10)
    mheaders = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    r.set_headers(mheaders)
    if params:
        r.set_query(params)
    r.set_path(path)
    if data is not None:
        r.set_body(json.dumps(data))
    credentials = Credentials(ak, sk, "air", config.region)
    SignerV4.sign(r, credentials)
    return r


class VikingDatabase(BaseModel, BaseDatabase):
    config: VikingDatabaseConfig = Field(
        default_factory=VikingDatabaseConfig,
        description="VikingDB configuration",
    )

    def _upload_to_tos(
        self,
        data: str | list[str] | TextIO | BinaryIO | bytes,
        **kwargs: Any,
    ) -> tuple[int, str]:
        """
        Upload data to TOS (Tinder Object Storage).

        Args:
            data: The data to be uploaded. Can be one of the following types:
                - str: File path or string data
                - list[str]: List of strings
                - TextIO: File object (text)
                - BinaryIO: File object (binary)
                - bytes: Binary data
            **kwargs: Additional keyword arguments.
                - file_name (str): The file name (including suffix).

        Returns:
            tuple: A tuple containing the status code and TOS URL.
                - status_code (int): HTTP status code
                - tos_url (str): The URL of the uploaded file in TOS
        """
        ak = self.config.volcengine_ak
        sk = self.config.volcengine_sk

        tos_bucket = self.config.tos.bucket
        tos_endpoint = self.config.tos.endpoint
        tos_region = self.config.tos.region
        tos_key = self.config.tos.base_key

        client = tos.TosClientV2(ak, sk, tos_endpoint, tos_region, max_connections=1024)

        # Extract file_name from kwargs - this is now required and includes the extension
        file_names = kwargs.get("file_name")

        if isinstance(data, str) and os.path.isfile(data):  # Process file path
            # Use provided file_name which includes the extension
            new_key = f"{tos_key}/{file_names}"
            with open(data, "rb") as f:
                upload_data = f.read()

        elif (
            isinstance(data, list)
            and all(isinstance(item, str) for item in data)
            and all(os.path.isfile(item) for item in data)
        ):
            # Process list of file paths - this should be handled at a higher level
            raise ValueError(
                "Uploading multiple files through a list of file paths is not supported in _upload_to_tos directly. Please call this function for each file individually."
            )

        elif isinstance(
            data,
            (io.TextIOWrapper, io.BufferedReader),  # file type: TextIO | BinaryIO
        ):  # Process file stream
            # Use provided file_name which includes the extension
            new_key = f"{tos_key}/{file_names}"
            if isinstance(data, TextIO):
                # Encode the text stream content into bytes
                upload_data = data.read().encode("utf-8")
            else:
                # Read the content of the binary stream
                upload_data = data.read()

        elif isinstance(data, str):  # Process ordinary strings
            # Use provided file_name which includes the extension
            new_key = f"{tos_key}/{file_names}"
            upload_data = data.encode("utf-8")  # Encode as byte type

        elif isinstance(data, list):  # Process list of strings
            # Use provided file_name which includes the extension
            new_key = f"{tos_key}/{file_names}"
            # Join the strings in the list with newlines and encode as byte type
            upload_data = "\n".join(data).encode("utf-8")

        elif isinstance(data, bytes):  # Process bytes data
            # Use provided file_name which includes the extension
            new_key = f"{tos_key}/{file_names}"
            upload_data = data

        else:
            raise ValueError(f"Unsupported data type: {type(data)}")

        resp = client.put_object(tos_bucket, new_key, content=upload_data)
        tos_url = f"{tos_bucket}/{new_key}"

        return resp.resp.status, tos_url

    def _add_doc(self, collection_name: str, tos_url: str, doc_id: str, **kwargs: Any):
        request_params = {
            "collection_name": collection_name,
            "project": self.config.project,
            "add_type": "tos",
            "doc_id": doc_id,
            "tos_path": tos_url,
        }

        doc_add_req = prepare_request(
            method="POST", path=doc_add_path, config=self.config, data=request_params
        )
        rsp = requests.request(
            method=doc_add_req.method,
            url="https://{}{}".format(g_knowledge_base_domain, doc_add_req.path),
            headers=doc_add_req.headers,
            data=doc_add_req.body,
        )

        result = rsp.json()
        if result["code"] != 0:
            logger.error(f"Error in add_doc: {result['message']}")
            return {"error": result["message"]}

        doc_add_data = result["data"]
        if not doc_add_data:
            raise ValueError(f"doc {doc_id} has no data.")

        return doc_id

    def add(
        self,
        data: str | list[str] | TextIO | BinaryIO | bytes,
        collection_name: str,
        **kwargs,
    ):
        """
        Add documents to the Viking database.
        Args:
            data: The data to be added. Can be one of the following types:
                - str: File path or string data
                - list[str]: List of file paths or list of strings
                - TextIO: File object (text)
                - BinaryIO: File object (binary)
                - bytes: Binary data
            collection_name: The name of the collection to add documents to.
            **kwargs: Additional keyword arguments.
                - file_name (str | list[str]): The file name or a list of file names (including suffix).
                - doc_id (str): The document ID. If not provided, a UUID will be generated.
        Returns:
            dict or list: A dictionary containing the TOS URL and document ID, or a list of such dictionaries for multiple file uploads.
            Format: {
                "tos_url": "tos://<bucket>/<key>",
                "doc_id": "<doc_id>",
            }
        """
        # Handle list of file paths (multiple file upload)
        if (
            isinstance(data, list)
            and all(isinstance(item, str) for item in data)
            and all(os.path.isfile(item) for item in data)
        ):
            # Handle multiple file upload
            file_names = kwargs.get("file_name")
            if (
                not file_names
                or not isinstance(file_names, list)
                or len(file_names) != len(data)
            ):
                raise ValueError(
                    "For multiple file upload, file_name must be provided as a list with the same length as data"
                )

            results = []
            for i, file_path in enumerate(data):
                # Create kwargs for this specific file
                single_kwargs = kwargs.copy()
                single_kwargs["file_name"] = file_names[i]

                # Generate or use provided doc_id for this file
                doc_id = single_kwargs.get("doc_id")
                if not doc_id:
                    doc_id = str(uuid.uuid4())
                    single_kwargs["doc_id"] = doc_id

                status, tos_url = self._upload_to_tos(data=file_path, **single_kwargs)
                if status != 200:
                    raise ValueError(
                        f"Error in upload_to_tos for file {file_path}: {status}"
                    )

                doc_id = self._add_doc(
                    collection_name=collection_name,
                    tos_url=tos_url,
                    doc_id=doc_id,
                )

                results.append(
                    {
                        "tos_url": f"tos://{tos_url}",
                        "doc_id": doc_id,
                    }
                )

            return results

        # Handle list of strings (multiple string upload)
        elif isinstance(data, list) and all(isinstance(item, str) for item in data):
            # Handle multiple string upload
            file_names = kwargs.get("file_name")
            if (
                not file_names
                or not isinstance(file_names, list)
                or len(file_names) != len(data)
            ):
                raise ValueError(
                    "For multiple string upload, file_name must be provided as a list with the same length as data"
                )

            results = []
            for i, content in enumerate(data):
                # Create kwargs for this specific string
                single_kwargs = kwargs.copy()
                single_kwargs["file_name"] = file_names[i]

                # Generate or use provided doc_id for this string
                doc_id = single_kwargs.get("doc_id")
                if not doc_id:
                    doc_id = str(uuid.uuid4())
                    single_kwargs["doc_id"] = doc_id

                status, tos_url = self._upload_to_tos(data=content, **single_kwargs)
                if status != 200:
                    raise ValueError(f"Error in upload_to_tos for string {i}: {status}")

                doc_id = self._add_doc(
                    collection_name=collection_name,
                    tos_url=tos_url,
                    doc_id=doc_id,
                )

                results.append(
                    {
                        "tos_url": f"tos://{tos_url}",
                        "doc_id": doc_id,
                    }
                )

            return results

        # Handle single file upload or other data types
        else:
            # Handle doc_id from kwargs or generate a new one
            doc_id = kwargs.get("doc_id", str(uuid.uuid4()))

            status, tos_url = self._upload_to_tos(data=data, **kwargs)
            if status != 200:
                raise ValueError(f"Error in upload_to_tos: {status}")
            doc_id = self._add_doc(
                collection_name=collection_name,
                tos_url=tos_url,
                doc_id=doc_id,
            )
            return {
                "tos_url": f"tos://{tos_url}",
                "doc_id": doc_id,
            }

    def delete(self, **kwargs: Any):
        name = kwargs.get("name")
        project = kwargs.get("project", self.config.project)
        request_param = {"name": name, "project": project}
        doc_del_req = prepare_request(
            method="POST", path=doc_del_path, config=self.config, data=request_param
        )
        rsp = requests.request(
            method=doc_del_req.method,
            url="http://{}{}".format(g_knowledge_base_domain, doc_del_req.path),
            headers=doc_del_req.headers,
            data=doc_del_req.body,
        )
        result = rsp.json()
        if result["code"] != 0:
            logger.error(f"Error in add_doc: {result['message']}")
            return False
        return True

    def query(self, query: str, **kwargs: Any) -> list[str]:
        """
        Args:
            query:  query text
            **kwargs: collection_name(required), top_k(optional, default 5)

        Returns: list of str, the search result
        """
        collection_name = kwargs.get("collection_name")
        assert collection_name is not None, "collection_name is required"
        request_params = {
            "query": query,
            "limit": int(kwargs.get("top_k", 5)),
            "name": collection_name,
            "project": self.config.project,
        }
        search_req = prepare_request(
            method="POST",
            path=search_knowledge_path,
            config=self.config,
            data=request_params,
        )
        resp = requests.request(
            method=search_req.method,
            url="https://{}{}".format(g_knowledge_base_domain, search_req.path),
            headers=search_req.headers,
            data=search_req.body,
        )

        result = resp.json()
        if result["code"] != 0:
            logger.error(f"Error in search_knowledge: {result['message']}")
            raise ValueError(f"Error in search_knowledge: {result['message']}")

        if not result["data"]["result_list"]:
            raise ValueError(f"No results found for collection {collection_name}")

        chunks = result["data"]["result_list"]

        search_result = []

        for chunk in chunks:
            search_result.append(chunk["content"])

        return search_result

    def create_collection(
        self,
        collection_name: str,
        description: str = "",
        version: Literal[2, 4] = 4,
        data_type: Literal[
            "unstructured_data", "structured_data"
        ] = "unstructured_data",
        chunking_strategy: Literal["custom_balance", "custom"] = "custom_balance",
        chunk_length: int = 500,
        merge_small_chunks: bool = True,
    ):
        request_params = {
            "name": collection_name,
            "project": self.config.project,
            "description": description,
            "version": version,
            "data_type": data_type,
            "preprocessing": {
                "chunking_strategy": chunking_strategy,
                "chunk_length": chunk_length,
                "merge_small_chunks": merge_small_chunks,
            },
        }

        create_collection_req = prepare_request(
            method="POST",
            path=create_collection_path,
            config=self.config,
            data=request_params,
        )
        resp = requests.request(
            method=create_collection_req.method,
            url="https://{}{}".format(
                g_knowledge_base_domain, create_collection_req.path
            ),
            headers=create_collection_req.headers,
            data=create_collection_req.body,
        )

        result = resp.json()
        if result["code"] != 0:
            logger.error(f"Error in create_collection: {result['message']}")
            raise ValueError(f"Error in create_collection: {result['message']}")
        return result

    def collection_exists(self, collection_name: str) -> bool:
        request_params = {
            "project": self.config.project,
        }
        list_collections_req = prepare_request(
            method="POST",
            path=list_collections_path,
            config=self.config,
            data=request_params,
        )
        resp = requests.request(
            method=list_collections_req.method,
            url="https://{}{}".format(
                g_knowledge_base_domain, list_collections_req.path
            ),
            headers=list_collections_req.headers,
            data=list_collections_req.body,
        )

        result = resp.json()
        if result["code"] != 0:
            logger.error(f"Error in list_collections: {result['message']}")
            raise ValueError(f"Error in list_collections: {result['message']}")

        collections = result["data"].get("collection_list", [])
        if len(collections) == 0:
            return False

        collection_list = set()

        for collection in collections:
            collection_list.add(collection["collection_name"])
        # check the collection exist or not
        if collection_name in collection_list:
            return True
        else:
            return False

    def list_chunks(
        self, collection_name: str, offset: int = 0, limit: int = -1
    ) -> list[dict]:
        request_params = {
            "collection_name": collection_name,
            "project": self.config.project,
            "offset": offset,
            "limit": limit,
        }

        list_doc_req = prepare_request(
            method="POST",
            path=list_point_path,
            config=self.config,
            data=request_params,
        )
        resp = requests.request(
            method=list_doc_req.method,
            url="https://{}{}".format(g_knowledge_base_domain, list_doc_req.path),
            headers=list_doc_req.headers,
            data=list_doc_req.body,
        )

        result = resp.json()
        if result["code"] != 0:
            logger.error(f"Error in list_docs: {result['message']}")
            raise ValueError(f"Error in list_docs: {result['message']}")

        if not result["data"].get("point_list", []):
            return []

        data = [
            {
                "id": res["point_id"],
                "content": res["content"],
                "metadata": res["doc_info"],
            }
            for res in result["data"]["point_list"]
        ]
        return data

    def list_docs(
        self, collection_name: str, offset: int = 0, limit: int = -1
    ) -> list[dict]:
        request_params = {
            "collection_name": collection_name,
            "project": self.config.project,
            "offset": offset,
            "limit": limit,
        }

        list_doc_req = prepare_request(
            method="POST",
            path=list_docs_path,
            config=self.config,
            data=request_params,
        )
        resp = requests.request(
            method=list_doc_req.method,
            url="https://{}{}".format(g_knowledge_base_domain, list_doc_req.path),
            headers=list_doc_req.headers,
            data=list_doc_req.body,
        )

        result = resp.json()
        if result["code"] != 0:
            logger.error(f"Error in list_docs: {result['message']}")
            raise ValueError(f"Error in list_docs: {result['message']}")

        if not result["data"].get("doc_list", []):
            return []
        return result["data"]["doc_list"]

    def delete_by_id(self, collection_name: str, id: str) -> bool:
        request_params = {
            "collection_name": collection_name,
            "project": self.config.project,
            "point_id": id,
        }

        delete_by_id_req = prepare_request(
            method="POST",
            path=delete_docs_path,
            config=self.config,
            data=request_params,
        )
        resp = requests.request(
            method=delete_by_id_req.method,
            url="https://{}{}".format(g_knowledge_base_domain, delete_by_id_req.path),
            headers=delete_by_id_req.headers,
            data=delete_by_id_req.body,
        )

        result = resp.json()
        if result["code"] != 0:
            return False
        return True
