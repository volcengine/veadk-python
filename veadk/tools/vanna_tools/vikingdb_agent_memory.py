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

import os
import json
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from volcengine.viking_db import (
    VikingDBService,
    Field,
    FieldType,
    VectorIndexParams,
    DistanceType,
    IndexType,
    QuantType,
    RawData,
    EmbModel,
    Data,
)

from vanna.capabilities.agent_memory import (
    AgentMemory,
    TextMemory,
    TextMemorySearchResult,
    ToolMemory,
    ToolMemorySearchResult,
)
from vanna.core.tool import ToolContext

from veadk.utils.logger import get_logger
from veadk.auth.veauth.utils import get_credential_from_vefaas_iam

logger = get_logger(__name__)


class VikingDBAgentMemory(AgentMemory):
    """
    VikingDB-based implementation of AgentMemory for Vanna training data.

    This stores three types of training data:
    1. DDL (table schemas)
    2. Documentation (contextual information)
    3. Question-SQL pairs (training examples)

    Each type is stored in a separate VikingDB collection for efficient retrieval.

    Args:
        volcengine_access_key: Volcengine access key (defaults to env var)
        volcengine_secret_key: Volcengine secret key (defaults to env var)
        session_token: Optional session token for temporary credentials
        region: VikingDB region (defaults to cn-beijing)
        host: VikingDB host (auto-generated from region if not provided)
        collection_prefix: Prefix for collection names (default: "vanna_train")
        embedding_model: Embedding model to use (default: "bge-large-zh")
    """

    def __init__(
        self,
        volcengine_access_key: Optional[str] = None,
        volcengine_secret_key: Optional[str] = None,
        session_token: str = "",
        region: str = "cn-beijing",
        host: Optional[str] = None,
        collection_prefix: str = "vanna_train",
        embedding_model: str = "doubao-embedding",
        cloud_provider: str = "volces",
    ):
        self.volcengine_access_key = volcengine_access_key or os.getenv(
            "VOLCENGINE_ACCESS_KEY"
        )
        self.volcengine_secret_key = volcengine_secret_key or os.getenv(
            "VOLCENGINE_SECRET_KEY"
        )
        self.session_token = session_token
        self.region = region
        self.cloud_provider = cloud_provider.lower()

        # Auto-generate host based on cloud provider
        if not host:
            if self.cloud_provider == "byteplus":
                self.host = "api-vikingdb.mlp.ap-mya.byteplus.com"
            else:
                if region == "cn-beijing":
                    self.host = "api-vikingdb.volces.com"
                else:
                    self.host = "api-vikingdb.mlp.cn-shanghai.volces.com"
        else:
            self.host = host

        self.collection_prefix = collection_prefix
        self.embedding_model = embedding_model

        # Collection names for different training data types
        self.ddl_collection = f"{collection_prefix}_ddl"
        self.doc_collection = f"{collection_prefix}_doc"
        self.sql_collection = f"{collection_prefix}_sql"

        self._client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize VikingDB client with authentication."""
        ak = self.volcengine_access_key
        sk = self.volcengine_secret_key
        sts_token = self.session_token

        # Try to get credentials from VeFaaS IAM if not provided
        if not (ak and sk):
            try:
                cred = get_credential_from_vefaas_iam()
                ak = cred.access_key_id
                sk = cred.secret_access_key
                sts_token = cred.session_token
                logger.info("Using VeFaaS IAM credentials for VikingDB")
            except Exception as e:
                logger.warning(f"Failed to get VeFaaS credentials: {e}")

        if not (ak and sk):
            raise ValueError(
                "Volcengine credentials not found. Please set VOLCENGINE_ACCESS_KEY "
                "and VOLCENGINE_SECRET_KEY environment variables."
            )

        self._client = VikingDBService(
            host=self.host,
            region=self.region,
            ak=ak,
            sk=sk,
            scheme="https",
        )
        self._client.set_session_token(session_token=sts_token)

        # Ensure collections exist
        self._ensure_collections()

    def _ensure_collections(self):
        """Create collections if they don't exist."""
        collections_to_create = [
            (self.ddl_collection, "DDL and table schemas"),
            (self.doc_collection, "Documentation and context"),
            (self.sql_collection, "Question-SQL training pairs"),
        ]

        for collection_name, description in collections_to_create:
            try:
                # Check if collection exists
                self._client.get_collection(collection_name)
                logger.info(f"Collection {collection_name} already exists")
            except Exception:
                # Create collection
                logger.info(f"Creating collection: {collection_name}")
                try:
                    self._client.create_collection(
                        collection_name=collection_name,
                        fields=[
                            Field(
                                field_name="id",
                                field_type=FieldType.String,
                                default_val="",
                            ),
                            Field(
                                field_name="content",
                                field_type=FieldType.Text,
                            ),
                            Field(
                                field_name="vector",
                                field_type=FieldType.Vector,
                                dim=2048,
                            ),
                            Field(
                                field_name="metadata",
                                field_type=FieldType.String,
                                default_val="{}",
                            ),
                        ],
                        description=description,
                    )
                    logger.info(f"Successfully created collection: {collection_name}")

                    vector_index = VectorIndexParams(
                        distance=DistanceType.COSINE,
                        index_type=IndexType.HNSW,
                        quant=QuantType.Float,
                    )

                    try:
                        self._client.create_index(
                            collection_name,
                            f"{collection_name}_index",
                            vector_index,
                            cpu_quota=2,
                            description=description,
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to create index for collection {collection_name}: {e}"
                        )
                        raise
                except Exception as e:
                    logger.error(f"Failed to create collection {collection_name}: {e}")
                    raise

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using VikingDB embedding service."""
        try:
            raw_data = [RawData("text", text)]
            response = self._client.embedding_v2(
                emb_model=EmbModel(self.embedding_model), raw_data=raw_data
            )
            if response and response.get("sentence_dense_embedding"):
                return response["sentence_dense_embedding"][0]
            else:
                raise ValueError(f"Invalid embedding response: {response}")
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    async def save_tool_usage(
        self,
        question: str,
        tool_name: str,
        args: Dict[str, Any],
        context: ToolContext,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Save a tool usage pattern.

        - If tool is run_sql: saves to sql_collection (question-SQL pairs)
        - If tool is other: saves to doc_collection (general tool usage documentation)

        Args:
            question: The user question
            tool_name: Name of the tool
            args: Tool arguments
            context: Tool execution context
            success: Whether execution was successful
            metadata: Additional metadata
        """
        # Generate ID
        doc_id = str(uuid.uuid4())

        # Prepare metadata
        meta = metadata or {}
        meta.update(
            {
                "question": question,
                "tool_name": tool_name,
                "success": success,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # Handle run_sql tool separately
        if tool_name == "run_sql" and "sql" in args:
            sql = args["sql"]

            # Create content for embedding (combine question and SQL)
            content = json.dumps({"question": question, "sql": sql}, ensure_ascii=False)

            meta["sql"] = sql
            meta["type"] = "question_sql"

            # Generate embedding
            vector = self._generate_embedding(content)

            # Insert into SQL collection
            field = {
                "id": doc_id,
                "content": content,
                "vector": vector,
                "metadata": json.dumps(meta, ensure_ascii=False),
            }

            data = Data(field)

            try:
                collection = self._client.get_collection(self.sql_collection)
                collection.upsert_data(data=[data])
                logger.info(
                    f"Saved question-SQL pair to sql_collection: {question[:50]}..."
                )
            except Exception as e:
                logger.error(f"Failed to save SQL tool usage: {e}")
                raise
        else:
            # For other tools, save to doc_collection as documentation
            # Create a descriptive content
            content = json.dumps(
                {
                    "question": question,
                    "tool_name": tool_name,
                    "args": args,
                    "description": f"User asked '{question}' and used tool '{tool_name}' with args: {args}",
                },
                ensure_ascii=False,
            )

            meta["args"] = args
            meta["type"] = "tool_usage"

            # Generate embedding
            vector = self._generate_embedding(content)

            # Insert into documentation collection
            field = {
                "id": doc_id,
                "content": content,
                "vector": vector,
                "metadata": json.dumps(meta, ensure_ascii=False),
            }

            data = Data(field)

            try:
                collection = self._client.get_collection(self.doc_collection)
                collection.upsert_data(data=[data])
                logger.info(
                    f"Saved tool usage to doc_collection: {tool_name} for question '{question[:50]}...'"
                )
            except Exception as e:
                logger.error(f"Failed to save tool usage to doc_collection: {e}")
                raise

    async def search_similar_usage(
        self,
        question: str,
        context: ToolContext,
        *,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        tool_name_filter: Optional[str] = None,
    ) -> List[ToolMemorySearchResult]:
        """
        Search for similar question-SQL pairs.

        Args:
            question: The question to search for
            context: Tool execution context
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score
            tool_name_filter: Filter by tool name

        Returns:
            List of similar tool usage patterns
        """
        # Generate embedding for query
        vector = self._generate_embedding(question)

        # Search in VikingDB
        try:
            index = self._client.get_index(
                self.sql_collection, f"{self.sql_collection}_index"
            )
            response = index.search_by_vector(
                vector=vector,
                limit=limit,
            )

            results = []
            for idx, item in enumerate(response):
                score = item.score

                # Apply similarity threshold
                if score < similarity_threshold:
                    continue

                # Parse metadata
                metadata = json.loads(item.fields.get("metadata", "{}"))

                # Apply tool name filter
                if tool_name_filter and metadata.get("tool_name") != tool_name_filter:
                    continue

                # Create ToolMemory object
                tool_memory = ToolMemory(
                    memory_id=item.fields.get("id"),
                    question=metadata.get("question", ""),
                    tool_name=metadata.get("tool_name", "run_sql"),
                    args={"sql": metadata.get("sql", "")},
                    success=metadata.get("success", True),
                )

                results.append(
                    ToolMemorySearchResult(
                        memory=tool_memory,
                        similarity_score=score,
                        rank=idx + 1,
                    )
                )

            return results
        except Exception as e:
            logger.error(f"Failed to search similar usage: {e}")
            return []

    async def save_text_memory(self, content: str, context: ToolContext) -> TextMemory:
        """Save a text memory."""

        # Generate ID
        doc_id = str(uuid.uuid4())

        # Generate embedding
        vector = self._generate_embedding(content)

        # Prepare metadata
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "type": "documentation",
        }

        # Insert into VikingDB
        field = {
            "id": doc_id,
            "content": content,
            "vector": vector,
            "metadata": json.dumps(metadata, ensure_ascii=False),
        }

        data = Data(field)

        try:
            collection = self._client.get_collection(self.doc_collection)
            collection.upsert_data(data=[data])
            logger.info(f"Saved documentation: {content[:50]}...")

            return TextMemory(
                memory_id=doc_id,
                content=content,
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            logger.error(f"Failed to save text memory: {e}")
            raise

    async def search_text_memories(
        self,
        query: str,
        context: ToolContext,
        *,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        include_ddl: bool = True,
    ) -> List[TextMemorySearchResult]:
        """
        Search documentation and DDL memories.

        This method searches both doc_collection and ddl_collection to provide
        comprehensive context including table schemas and documentation.

        Args:
            query: Query string
            context: Tool execution context
            limit: Maximum results per collection
            similarity_threshold: Minimum similarity score
            include_ddl: Whether to include DDL results (default: True)

        Returns:
            List of matching text memories (documentation + DDL)
        """
        results = []
        vector = self._generate_embedding(query)

        # Search documentation collection
        try:
            doc_index = self._client.get_index(
                self.doc_collection, f"{self.doc_collection}_index"
            )
            doc_response = doc_index.search_by_vector(
                vector=vector,
                limit=limit,
            )

            for idx, item in enumerate(doc_response):
                score = item.score

                if score < similarity_threshold:
                    continue

                content = item.fields.get("content", "")
                memory_id = item.fields.get("id")

                text_memory = TextMemory(
                    memory_id=memory_id,
                    content=content,
                    timestamp=None,
                )

                results.append(
                    TextMemorySearchResult(
                        memory=text_memory,
                        similarity_score=score,
                        rank=len(results) + 1,
                    )
                )
        except Exception as e:
            logger.error(f"Failed to search documentation: {e}")

        # Search DDL collection if requested
        if include_ddl:
            try:
                ddl_index = self._client.get_index(
                    self.ddl_collection, f"{self.ddl_collection}_index"
                )
                ddl_response = ddl_index.search_by_vector(
                    vector=vector,
                    limit=limit,
                )

                for idx, item in enumerate(ddl_response):
                    score = item.score

                    if score < similarity_threshold:
                        continue

                    content = item.fields.get("content", "")
                    memory_id = item.fields.get("id")

                    # Mark DDL content with a prefix for clarity
                    text_memory = TextMemory(
                        memory_id=memory_id,
                        content=f"[DDL Schema]\n{content}",
                        timestamp=None,
                    )

                    results.append(
                        TextMemorySearchResult(
                            memory=text_memory,
                            similarity_score=score,
                            rank=len(results) + 1,
                        )
                    )
            except Exception as e:
                logger.error(f"Failed to search DDL: {e}")

        # Sort by similarity score (descending)
        results.sort(key=lambda x: x.similarity_score, reverse=True)

        # Update ranks after sorting
        for idx, result in enumerate(results):
            result.rank = idx + 1

        return results[
            : limit * 2
        ]  # Return up to limit*2 results (from both collections)

    def train_ddl(self, ddl: str) -> str:
        """
        Train with DDL (table schema).

        Args:
            ddl: DDL statement

        Returns:
            ID of the saved DDL
        """
        doc_id = str(uuid.uuid4())
        vector = self._generate_embedding(ddl)

        metadata = {
            "timestamp": datetime.now().isoformat(),
            "type": "ddl",
        }

        field = {
            "id": doc_id,
            "content": ddl,
            "vector": vector,
            "metadata": json.dumps(metadata, ensure_ascii=False),
        }

        data = Data(field)

        try:
            collection = self._client.get_collection(self.ddl_collection)
            collection.upsert_data(data=[data])
            logger.info(f"Trained DDL: {ddl[:50]}...")
            return doc_id
        except Exception as e:
            logger.error(f"Failed to train DDL: {e}")
            raise

    def train_documentation(self, documentation: str) -> str:
        """
        Train with documentation.

        Args:
            documentation: Documentation text

        Returns:
            ID of the saved documentation
        """
        doc_id = str(uuid.uuid4())
        vector = self._generate_embedding(documentation)

        metadata = {
            "timestamp": datetime.now().isoformat(),
            "type": "documentation",
        }

        field = {
            "id": doc_id,
            "content": documentation,
            "vector": vector,
            "metadata": json.dumps(metadata, ensure_ascii=False),
        }

        data = Data(field)

        try:
            collection = self._client.get_collection(self.doc_collection)
            collection.upsert_data(data=[data])
            logger.info(f"Trained documentation: {documentation[:50]}...")
            return doc_id
        except Exception as e:
            logger.error(f"Failed to train documentation: {e}")
            raise

    def train_question_sql(self, question: str, sql: str) -> str:
        """
        Train with question-SQL pair.

        Args:
            question: User question
            sql: SQL query

        Returns:
            ID of the saved pair
        """
        content = json.dumps({"question": question, "sql": sql}, ensure_ascii=False)

        doc_id = str(uuid.uuid4())
        vector = self._generate_embedding(content)

        metadata = {
            "question": question,
            "sql": sql,
            "timestamp": datetime.now().isoformat(),
            "type": "question_sql",
        }

        field = {
            "id": doc_id,
            "content": content,
            "vector": vector,
            "metadata": json.dumps(metadata, ensure_ascii=False),
        }

        data = Data(field)

        try:
            collection = self._client.get_collection(self.sql_collection)
            collection.upsert_data(data=[data])
            logger.info(f"Trained question-SQL: {question[:50]}...")
            return doc_id
        except Exception as e:
            logger.error(f"Failed to train question-SQL: {e}")
            raise

    def get_related_ddl(self, question: str, limit: int = 5) -> List[str]:
        """
        Get related DDL for a question.

        Args:
            question: User question
            limit: Maximum results

        Returns:
            List of related DDL statements
        """
        vector = self._generate_embedding(question)

        try:
            index = self._client.get_index(
                self.ddl_collection, f"{self.ddl_collection}_index"
            )
            response = index.search_by_vector(
                vector=vector,
                limit=limit,
            )
            return [
                item.get("fields", {}).get("content", "")
                for item in response.get("items", [])
            ]
        except Exception as e:
            logger.error(f"Failed to get related DDL: {e}")
            return []

    def get_related_documentation(self, question: str, limit: int = 5) -> List[str]:
        """
        Get related documentation for a question.

        Args:
            question: User question
            limit: Maximum results

        Returns:
            List of related documentation
        """
        vector = self._generate_embedding(question)

        try:
            index = self._client.get_index(
                self.doc_collection, f"{self.doc_collection}_index"
            )
            response = index.search_by_vector(
                vector=vector,
                limit=limit,
            )
            return [
                item.get("fields", {}).get("content", "")
                for item in response.get("items", [])
            ]
        except Exception as e:
            logger.error(f"Failed to get related documentation: {e}")
            return []

    async def get_recent_memories(
        self, context: ToolContext, limit: int = 10
    ) -> List[ToolMemory]:
        """Get recent tool memories (not implemented for VikingDB)."""
        return []

    async def get_recent_text_memories(
        self, context: ToolContext, limit: int = 10
    ) -> List[TextMemory]:
        """Get recent text memories (not implemented for VikingDB)."""
        return []

    async def delete_by_id(self, context: ToolContext, memory_id: str) -> bool:
        """Delete memory by ID (not implemented for VikingDB)."""
        return False

    async def delete_text_memory(self, context: ToolContext, memory_id: str) -> bool:
        """Delete text memory by ID (not implemented for VikingDB)."""
        return False

    async def clear_memories(
        self,
        context: ToolContext,
        tool_name: Optional[str] = None,
        before_date: Optional[str] = None,
    ) -> int:
        """Clear memories (not implemented for VikingDB)."""
        return 0
