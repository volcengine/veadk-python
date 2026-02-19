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

import json
import os
import uuid
import tempfile
import shutil
from typing import Any
from urllib.parse import urlparse
from pathlib import Path
from pydantic import Field
from typing_extensions import override

import veadk.config  # noqa E401
from veadk.knowledgebase.backends.base_backend import BaseKnowledgebaseBackend
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request
import requests

logger = get_logger(__name__)


class ContextSearchBackend(BaseKnowledgebaseBackend):
    """Context Search backend implementation for knowledge base operations.

    This backend integrates with Volcengine Context Search service to provide
    document indexing, storage, and semantic search capabilities. It supports
    multiple data sources including files, directories, and raw text.

    Attributes:
        volcengine_access_key: Volcengine access key for API authentication.
        volcengine_secret_key: Volcengine secret key for API authentication.
        volcengine_session_token: Optional session token for temporary credentials.
        context_search_region: Region where the Context Search service is deployed.
        context_search_project: Project name in Context Search.
        context_search_engine_id: Engine ID for the search endpoint.
        context_search_engine_endpoint: Full URL of the search endpoint.
        context_search_engine_apikey: API key for search operations.
        context_search_service: Service identifier for API requests.
        context_search_version: API version string.
        context_search_host: Hostname for the Context Search API.
        context_search_scheme: Protocol scheme (http or https).

    Example:
        >>> backend = ContextSearchBackend(
        ...     index="123456789",
        ...     volcengine_access_key="your-ak",
        ...     volcengine_secret_key="your-sk",
        ... )
        >>> backend.add_from_text("Sample document content")
        >>> results = backend.search("query", top_k=5)

    Note:
        Configuration can be provided via constructor parameters or environment
        variables. Environment variables take precedence over config file values.
    """

    volcengine_access_key: str | None = Field(
        default_factory=lambda: os.getenv("VOLCENGINE_ACCESS_KEY")
    )
    volcengine_secret_key: str | None = Field(
        default_factory=lambda: os.getenv("VOLCENGINE_SECRET_KEY")
    )
    volcengine_session_token: str | None = Field(
        default_factory=lambda: os.getenv("VOLCENGINE_SESSION_TOKEN")
    )

    context_search_region: str | None = Field(
        default_factory=lambda: os.getenv("DATABASE_CONTEXT_SEARCH_REGION")
    )
    context_search_project: str | None = Field(
        default_factory=lambda: os.getenv("DATABASE_CONTEXT_SEARCH_PROJECT")
    )
    context_search_engine_id: str | None = Field(
        default_factory=lambda: os.getenv("DATABASE_CONTEXT_SEARCH_ENGINE_ID")
    )
    context_search_engine_endpoint: str | None = Field(
        default_factory=lambda: os.getenv("DATABASE_CONTEXT_SEARCH_ENGINE_ENDPOINT")
    )
    context_search_engine_apikey: str | None = Field(
        default_factory=lambda: os.getenv("DATABASE_CONTEXT_SEARCH_ENGINE_APIKEY")
    )

    context_search_service: str = "ctxsearch"
    context_search_version: str = "2025-09-01"
    context_search_host: str = "ctxsearch.volcengineapi.com"
    context_search_scheme: str = "https"

    def model_post_init(self, __context: Any) -> None:
        """Initialize additional attributes after model instantiation.

        This method is automatically called after the model is initialized.
        It handles cloud provider-specific configurations and sets default
        values for region and project if not provided.

        Args:
            __context: Pydantic internal context (unused).
        """
        provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
        is_byteplus = provider == "byteplus"
        if is_byteplus and "volcengineapi.com" in self.context_search_host:
            self.context_search_host = self.context_search_host.replace(
                "volcengineapi.com",
                "byteplusapi.com",
            )
        if not self.context_search_region:
            self.context_search_region = (
                "ap-southeast-1" if is_byteplus else "cn-beijing"
            )
        if not self.context_search_project:
            self.context_search_project = "default"

    def _get_scene_id(self) -> str:
        """Retrieve the scene ID for Context Search operations.

        Returns the scene identifier used for API requests. Prefers
        context_search_engine_id if set, otherwise falls back to index.

        Returns:
            str: The scene ID as a numeric string.
        """
        return self.context_search_engine_id or self.index

    def _do_request(
        self,
        action: str,
        method: str = "POST",
        query: dict | None = None,
        request_body: dict | None = None,
    ) -> dict:
        """Execute a signed request to the Context Search API.

        This internal method handles the authentication and communication
        with the Context Search service. It automatically signs requests
        using Volcengine credentials and handles error responses.

        Args:
            action: The API action/operation name (e.g., "GetScene", "AddSceneData").
            method: HTTP method for the request. Defaults to "POST".
            query: Optional query parameters for GET requests.
            request_body: Optional JSON body for POST/PUT requests.

        Returns:
            dict: The "Result" field from the API response.

        Raises:
            ValueError: If the API returns an error response.

        Example:
            >>> result = self._do_request(
            ...     action="GetScene",
            ...     method="GET",
            ...     query={"Project": "default", "Id": "12345"}
            ... )
        """
        header = {}
        if self.volcengine_session_token:
            header["X-Security-Token"] = self.volcengine_session_token

        res = ve_request(
            request_body=request_body or {},
            action=action,
            ak=self.volcengine_access_key,
            sk=self.volcengine_secret_key,
            service=self.context_search_service,
            version=self.context_search_version,
            region=self.context_search_region,
            host=self.context_search_host,
            scheme=self.context_search_scheme,
            query=query or {},
            header=header,
            method=method,
        )

        if res.get("ResponseMetadata", {}).get("Error"):
            error = res["ResponseMetadata"]["Error"]
            raise ValueError(
                f"Context Search API Error (Action: {action}): {error.get('Message')} (Code: {error.get('Code')})"
            )

        return res.get("Result")

    @override
    def precheck_index_naming(self) -> None:
        """Validate the index format and verify its existence in Context Search.

        This method performs two checks:
        1. Validates that the scene ID is a numeric string (required by Context Search)
        2. Makes an API call to verify the scene exists and is accessible

        Raises:
            ValueError: If the scene ID is not a numeric string or if the scene
                does not exist in Context Search.

        Example:
            >>> backend = ContextSearchBackend(index="123456789", ...)
            >>> backend.precheck_index_naming()  # Validates and verifies the scene
            # Logs: Successfully verified index '123456789' via GetScene.
        """
        scene_id = self._get_scene_id()
        if not (isinstance(scene_id, str) and scene_id.isdigit()):
            raise ValueError(
                f"The index name (Scene Id) must be a numeric string (long), got: {scene_id}"
            )

        self._do_request(
            action="GetScene",
            method="GET",
            query={
                "Project": self.context_search_project,
                "SceneType": "RAG",
                "Id": scene_id,
            },
        )

        logger.info(f"Successfully verified index '{scene_id}' via GetScene.")

    @override
    def add_from_directory(self, directory: str, *args, **kwargs) -> bool:
        """Index all files from a directory into the knowledge base.

        Recursively scans the specified directory and indexes all files found.
        The files are uploaded to Context Search for processing and embedding.

        Args:
            directory: Path to the directory containing files to index.
            *args: Additional positional arguments passed to add_from_files.
            **kwargs: Additional keyword arguments passed to add_from_files.

        Returns:
            bool: True if all files were successfully queued for indexing.

        Raises:
            ValueError: If the directory does not exist, is not a directory,
                or contains no files.

        Example:
            >>> backend.add_from_directory("/path/to/documents")
            # Indexes all files in the directory recursively
        """
        logger.info(f"Adding from directory: {directory}")
        dir_path = Path(directory)
        if not dir_path.exists() or not dir_path.is_dir():
            raise ValueError(f"Directory not found: {directory}")
        files = [str(path) for path in dir_path.rglob("*") if path.is_file()]
        if not files:
            raise ValueError(f"No files found in directory: {directory}")
        return self.add_from_files(files, *args, **kwargs)

    @override
    def add_from_files(self, files: list[str], *args, **kwargs) -> bool:
        """Index a list of files into the knowledge base.

        Uploads files to Context Search for processing and embedding generation.
        The upload process involves:
        1. Validating all files exist
        2. Obtaining pre-signed upload URLs from Context Search
        3. Uploading files directly to TOS (Volcengine Object Storage)
        4. Registering the uploaded files with Context Search for indexing

        Note:
            This operation is asynchronous. Files are queued for indexing and
            may not be immediately searchable. Use search() after a reasonable
            delay to allow indexing to complete.

        Args:
            files: List of file paths to index.
            *args: Additional positional arguments (reserved for future use).
            **kwargs: Additional keyword arguments (reserved for future use).

        Returns:
            bool: True if files were successfully uploaded and queued for indexing.

        Raises:
            ValueError: If any file does not exist or if the upload fails.

        Example:
            >>> files = ["/docs/doc1.pdf", "/docs/doc2.txt"]
            >>> backend.add_from_files(files)
            # Files uploaded asynchronously. Wait for Context Search indexing...
        """
        logger.info(f"Adding from files: {files}")
        self._validate_files(files)

        uuid_prefix, upload_infos = self._get_upload_url(files)
        file_info_list = []
        for upload in upload_infos:
            file_path = upload.get("file_path")
            tos_path = upload.get("tos_path")
            upload_url = upload.get("upload_url")
            headers = upload.get("headers") or {}
            self._upload_file(file_path, upload_url, headers)
            file_info_list.append(
                json.dumps(
                    {
                        "file_path": tos_path,
                    }
                )
            )

        self._do_request(
            action="AddSceneData",
            method="POST",
            request_body={
                "Project": self.context_search_project,
                "SceneType": "RAG",
                "SceneId": self._get_scene_id(),
                "Type": "LOCAL",
                "FileInfoList": file_info_list,
                "TosConfig": {
                    "Prefix": uuid_prefix,
                },
            },
        )

        logger.info(
            f"Files uploaded asynchronously. Wait for Context Search indexing to complete before searching. files={files}"
        )

        return True

    @override
    def add_from_text(self, text: str | list[str], *args, **kwargs) -> bool:
        """Index raw text content into the knowledge base.

        Converts text content into temporary files and indexes them. This is useful
        for indexing content that is generated dynamically or retrieved from
        external sources without persisting to disk first.

        Note:
            Temporary files are created in a system temp directory and are
            automatically cleaned up after indexing, regardless of success or failure.

        Args:
            text: Single text string or list of text strings to index.
            *args: Additional positional arguments passed to add_from_files.
            **kwargs: Additional keyword arguments passed to add_from_files.

        Returns:
            bool: True if text was successfully queued for indexing.

        Raises:
            ValueError: If text is empty or if file operations fail.

        Example:
            >>> backend.add_from_text("This is a sample document.")
            >>> backend.add_from_text(["Doc 1 content", "Doc 2 content"])
        """
        if isinstance(text, str):
            texts = [text]
        else:
            texts = text

        file_paths = []
        temp_dir = tempfile.mkdtemp()
        try:
            for i, t in enumerate(texts):
                file_path = Path(temp_dir) / f"text_{uuid.uuid4().hex}_{i}.txt"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(t)
                file_paths.append(str(file_path))

            return self.add_from_files(file_paths, *args, **kwargs)
        finally:
            shutil.rmtree(temp_dir)

    @override
    def search(self, query: str, top_k: int = 5) -> list[str]:
        """Perform semantic search against the indexed knowledge base.

        Sends a search query to the Context Search engine and returns relevant
        document chunks based on semantic similarity. The search uses the
        configured engine endpoint and API key for authentication.

        Args:
            query: The search query string.
            top_k: Maximum number of results to return. Defaults to 5.

        Returns:
            list[str]: List of document content strings matching the query,
                ordered by relevance (most relevant first).

        Raises:
            ValueError: If the engine endpoint or API key is not configured,
                if the API returns an error, or if the response is invalid.

        Example:
            >>> results = backend.search("machine learning", top_k=3)
            >>> for doc in results:
            ...     print(doc)
        """
        if not self.context_search_engine_endpoint:
            raise ValueError("Context Search engine endpoint is not set.")
        if not self.context_search_engine_apikey:
            raise ValueError("Context Search engine apikey is not set.")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.context_search_engine_apikey}",
        }
        url = f"{self.context_search_engine_endpoint}/v2/search"
        json_data = {"text": query, "size": top_k}
        response = requests.post(url, json=json_data, headers=headers)
        try:
            result = response.json()
        except ValueError:
            text = response.text.strip()
            raise ValueError(
                f"Context Search response is not JSON. status={response.status_code}, body={text[:500]}"
            )
        if result.get("error"):
            raise ValueError(result.get("error").get("message"))
        return [
            doc.get("content").get("sys.content") or ""
            for doc in result.get("documents", [])
        ]

    def _get_upload_url(self, files: list[str]) -> tuple[str, list[dict]]:
        """Obtain pre-signed upload URLs for file indexing.

        Requests upload URLs from Context Search API for the specified files.
        The returned URLs are pre-signed for direct upload to TOS (Volcengine
        Object Storage) without requiring additional authentication.

        Args:
            files: List of file paths to be uploaded.

        Returns:
            tuple[str, list[dict]]: A tuple containing:
                - UUID prefix string used for organizing uploads
                - List of upload information dictionaries with keys:
                  file_path, file_name, upload_url, tos_path, headers

        Raises:
            ValueError: If the files list is empty or if the API response
                is missing required upload information.

        Note:
            This is an internal method typically called by add_from_files().
        """
        if not files:
            raise ValueError("Files list is empty.")

        uuid_prefix = str(uuid.uuid4())
        res = self._do_request(
            action="GetIndexerUploadFileInfo",
            method="POST",
            request_body={
                "UuidPrefix": uuid_prefix,
                "SseEnabled": False,
                "FileInfos": self._build_file_infos(files),
            },
        )
        upload_file_infos = res.get("UploadFileInfos") or []
        if not upload_file_infos:
            raise ValueError("UploadFileInfos is empty.")

        results = []
        for index, info in enumerate(upload_file_infos):
            upload_url = info.get("UploadUrl")
            if not upload_url:
                raise ValueError("UploadUrl is missing in UploadFileInfos.")
            if index >= len(files):
                raise ValueError("UploadFileInfos size does not match files list.")
            file_path = files[index]
            file_name = os.path.basename(file_path)
            tos_path = self._build_tos_path(upload_url, file_path)
            results.append(
                {
                    "file_path": file_path,
                    "file_name": file_name,
                    "upload_url": upload_url,
                    "tos_path": tos_path,
                    "headers": self._normalize_headers(info.get("Headers")),
                }
            )
        return uuid_prefix, results

    def _validate_files(self, files: list[str]) -> None:
        """Validate that all files in the list exist and are accessible.

        Performs existence checks on all file paths before attempting upload.
        This prevents partial uploads and provides clear error messages for
        missing files.

        Args:
            files: List of file paths to validate.

        Raises:
            ValueError: If the files list is empty or if any file does not exist.

        Note:
            This is an internal method called by add_from_files() to ensure
            all files are available before initiating the upload process.
        """
        if not files:
            raise ValueError("Files list is empty.")
        for path in files:
            if not Path(path).exists():
                raise ValueError(f"File not found: {path}")

    def _build_file_infos(self, files: list[str]) -> list[dict]:
        """Build file metadata for upload requests.

        Extracts file name and size information required by the Context Search
        API when requesting upload URLs.

        Args:
            files: List of file paths to extract metadata from.

        Returns:
            list[dict]: List of file info dictionaries containing:
                - Name: The base filename
                - Size: File size in bytes

        Note:
            This is an internal method used by _get_upload_url() to construct
            the request body for the GetIndexerUploadFileInfo API call.
        """
        return [
            {
                "Name": os.path.basename(file),
                "Size": os.path.getsize(file),
            }
            for file in files
        ]

    def _normalize_headers(self, headers: object) -> dict:
        """Normalize HTTP headers from various formats to a dictionary.

        Context Search API may return headers in different formats (dict or list
        of key-value pairs). This method normalizes them into a standard
        dictionary format for use with the requests library.

        Args:
            headers: Headers in various formats (None, dict, or list of dicts).
                List format may contain {"Key": "...", "Value": "..."} objects
                or direct key-value mappings.

        Returns:
            dict: Normalized headers as a dictionary mapping header names to values.

        Raises:
            ValueError: If headers is in an unrecognized format.

        Note:
            This is an internal method used by _get_upload_url() to process
            the Headers field from the GetIndexerUploadFileInfo API response.
        """
        if not headers:
            return {}
        if isinstance(headers, dict):
            return headers
        if not isinstance(headers, list):
            raise ValueError("Headers format is invalid.")
        normalized_headers: dict[str, str] = {}
        for item in headers:
            if not isinstance(item, dict):
                continue
            if "Key" in item and "Value" in item:
                normalized_headers[item["Key"]] = item["Value"]
                continue
            for key, value in item.items():
                normalized_headers[key] = value
        return normalized_headers

    def _upload_file(self, file_path: str, upload_url: str, headers: dict) -> None:
        """Upload a single file to TOS using a pre-signed URL.

        Performs a direct HTTP PUT upload to Volcengine Object Storage (TOS)
        using a pre-signed URL obtained from Context Search. The pre-signed
        URL contains temporary authentication credentials.

        Args:
            file_path: Local path to the file to upload.
            upload_url: Pre-signed URL for uploading to TOS.
            headers: HTTP headers required for the upload (e.g., Content-Type).

        Raises:
            ValueError: If the upload fails (non-2xx status code).

        Note:
            This is an internal method called by add_from_files() for each file.
            The file is opened in binary mode and streamed to minimize memory usage.
        """
        with open(file_path, "rb") as file_handle:
            response = requests.put(upload_url, data=file_handle, headers=headers)
        if response.status_code not in (200, 201, 204):
            raise ValueError(
                f"Upload failed for {file_path}: {response.status_code} {response.text}"
            )

    def _build_tos_path(self, upload_url: str, file_path: str) -> str:
        """Construct a TOS (Tinder Object Storage) URI from an upload URL.

        Parses the pre-signed upload URL to extract the bucket name and object
        key prefix, then constructs a TOS URI in the format:
        tos://{bucket}/{prefix}/{filename}

        Args:
            upload_url: The pre-signed URL from Context Search API.
            file_path: Original local file path (used for filename extraction).

        Returns:
            str: TOS URI in the format "tos://bucket/prefix/filename".

        Raises:
            ValueError: If the upload URL is missing hostname or path components.

        Example:
            >>> url = "https://mybucket.tos-cn-beijing.volces.com/prefix/obj?token=xxx"
            >>> backend._build_tos_path(url, "/local/path/file.txt")
            'tos://mybucket/prefix/file.txt'

        Note:
            This is an internal method used by _get_upload_url() to construct
            the TOS path for registering uploaded files with Context Search.
        """
        parsed_url = urlparse(upload_url)
        hostname = parsed_url.hostname or ""
        if not hostname:
            raise ValueError("UploadUrl hostname is missing.")
        bucket = hostname.split(".")[0]
        path_segments = parsed_url.path.lstrip("/").split("/")
        if not path_segments or not path_segments[0]:
            raise ValueError("UploadUrl path is missing.")
        return f"tos://{bucket}/{path_segments[0]}/{os.path.basename(file_path)}"
