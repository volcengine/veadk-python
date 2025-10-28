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

from pathlib import Path
from typing import Literal

import click


@click.command()
@click.option(
    "--backend",
    type=click.Choice(
        ["local", "opensearch", "viking", "redis"],
        case_sensitive=False,
    ),
    required=True,
)
@click.option(
    "--app_name",
    default="",
    help="`app_name` for init your knowledgebase",
)
@click.option(
    "--index",
    default="",
    help="Knowledgebase index",
)
@click.option(
    "--path",
    required=True,
    help="Knowledge file or directory path",
)
def add(
    backend: Literal["local", "opensearch", "viking", "redis"],
    app_name: str,
    index: str,
    path: str,
):
    """Add files to knowledgebase.

    This command adds files or directories to a specified knowledgebase backend.
    It supports various backend types including local storage, OpenSearch, Viking,
    and Redis for storing and indexing knowledge content.

    Args:
        backend: The knowledgebase backend type to use for storing and indexing documents.
            Available options:
            - 'local': Local file-based storage using SQLite. Suitable for development
              and small-scale deployments. No external dependencies required.
            - 'opensearch': Elasticsearch-compatible search engine with advanced
              full-text search and vector similarity capabilities. Recommended for
              production environments with large document collections.
            - 'viking': Volcengine's managed vector database service optimized for
              semantic search and RAG applications. Provides high performance and
              automatic scaling on Volcengine cloud platform.
            - 'redis': In-memory data structure store with vector search capabilities.
              Fast retrieval but limited by memory capacity. Good for frequently
              accessed, smaller knowledge bases.
        app_name: Application identifier for organizing and isolating knowledgebase
            data. Used to create logical separation between different applications
            or environments. Must be consistent across operations for the same knowledge base.
        index: Knowledgebase index identifier within the application namespace.
            Acts as a unique name for this specific knowledge collection. Multiple
            indexes can exist under the same app_name for different knowledge domains.
            Index names should be descriptive and follow naming conventions of the chosen backend.
        path: File system path to the knowledge content to be added to the knowledge base.
            Supported formats:
            - Single file: Path to a specific document (PDF, TXT, MD, DOCX, etc.)
            - Directory: Path to a folder containing multiple documents. All supported
              files in the directory will be processed recursively.

    Raises:
        RuntimeError: If the file type is not supported
    """
    _path = Path(path)
    assert _path.exists(), f"Path {path} not exists. Please check your input."

    from veadk.knowledgebase import KnowledgeBase

    knowledgebase = KnowledgeBase(backend=backend, app_name=app_name, index=index)

    if _path.is_file():
        knowledgebase.add_from_files(files=[path])
    elif _path.is_dir():
        knowledgebase.add_from_directory(directory=path)
    else:
        raise RuntimeError(
            "Unsupported knowledgebase file type, only support a single file and a directory."
        )


@click.group()
def kb():
    """VeADK Knowledgebase management"""
    pass


kb.add_command(add)
