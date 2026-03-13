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

from typing import Optional, List
from veadk.tools.vanna_tools.vikingdb_agent_memory import VikingDBAgentMemory
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class VannaTrainer:
    """
    Vanna 1.0 style trainer for VeADK.

    This class provides a simple API for training Vanna models using VikingDB as the backend.
    It mimics the Vanna 1.0 `train()` method interface.

    Example:
        ```python
        from veadk.tools.vanna_tools.vanna_trainer import VannaTrainer

        # Initialize trainer
        trainer = VannaTrainer(
            collection_prefix="my_vanna_project",
            region="cn-beijing"
        )

        # Train with DDL
        trainer.train(ddl="CREATE TABLE customers (id INT, name VARCHAR(100), email VARCHAR(100))")

        # Train with documentation
        trainer.train(documentation="The customers table contains all customer information")

        # Train with question-SQL pairs
        trainer.train(
            question="Who are the top 10 customers by sales?",
            sql="SELECT name, SUM(sales) as total FROM customers GROUP BY name ORDER BY total DESC LIMIT 10"
        )

        # Get the agent memory for use in VannaToolSet
        agent_memory = trainer.get_agent_memory()
        ```
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
        """
        Initialize VannaTrainer with VikingDB backend.

        Args:
            volcengine_access_key: Volcengine access key (defaults to env var)
            volcengine_secret_key: Volcengine secret key (defaults to env var)
            session_token: Optional session token for temporary credentials
            region: VikingDB region (defaults to cn-beijing)
            host: VikingDB host (auto-generated from region if not provided)
            collection_prefix: Prefix for collection names (default: "vanna_train")
            embedding_model: Embedding model to use (default: "bge-large-zh")
            cloud_provider: Cloud provider (volces or byteplus)
        """
        self.agent_memory = VikingDBAgentMemory(
            volcengine_access_key=volcengine_access_key,
            volcengine_secret_key=volcengine_secret_key,
            session_token=session_token,
            region=region,
            host=host,
            collection_prefix=collection_prefix,
            embedding_model=embedding_model,
            cloud_provider=cloud_provider,
        )

        logger.info(
            f"VannaTrainer initialized with collection_prefix='{collection_prefix}'"
        )

    def train(
        self,
        question: Optional[str] = None,
        sql: Optional[str] = None,
        ddl: Optional[str] = None,
        documentation: Optional[str] = None,
    ) -> str:
        """
        Train Vanna with different types of data (Vanna 1.0 style API).

        This method mimics the Vanna 1.0 `train()` method interface. You can call it with:
        - `ddl`: Train with table schema
        - `documentation`: Train with contextual information
        - `question` + `sql`: Train with question-SQL pairs

        Args:
            question: User question (must be provided with sql)
            sql: SQL query (must be provided with question)
            ddl: DDL statement for table schema
            documentation: Documentation or contextual information

        Returns:
            ID of the saved training data

        Raises:
            ValueError: If invalid arguments are provided

        Examples:
            ```python
            # Train with DDL
            trainer.train(ddl="CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100))")

            # Train with documentation
            trainer.train(documentation="The users table stores user profile information")

            # Train with question-SQL pair
            trainer.train(
                question="How many users do we have?",
                sql="SELECT COUNT(*) FROM users"
            )
            ```
        """
        # Validate arguments
        if question and not sql:
            raise ValueError(
                "Please also provide a SQL query when training with a question"
            )

        if sql and not question:
            logger.warning(
                "SQL provided without question - generating default question"
            )
            question = f"Query: {sql[:50]}..."

        # Train based on provided data type
        if documentation:
            logger.info("Training with documentation...")
            return self.agent_memory.train_documentation(documentation)

        if sql and question:
            logger.info(f"Training with question-SQL pair: {question[:50]}...")
            return self.agent_memory.train_question_sql(question, sql)

        if ddl:
            logger.info(f"Training with DDL: {ddl[:50]}...")
            return self.agent_memory.train_ddl(ddl)

        raise ValueError(
            "You must provide one of the following:\n"
            "- ddl: for table schemas\n"
            "- documentation: for contextual information\n"
            "- question + sql: for training examples"
        )

    def train_bulk(
        self,
        ddls: Optional[List[str]] = None,
        documentations: Optional[List[str]] = None,
        question_sql_pairs: Optional[List[tuple[str, str]]] = None,
    ) -> dict:
        """
        Train with multiple items in bulk.

        Args:
            ddls: List of DDL statements
            documentations: List of documentation strings
            question_sql_pairs: List of (question, sql) tuples

        Returns:
            Dictionary with counts of trained items

        Example:
            ```python
            trainer.train_bulk(
                ddls=[
                    "CREATE TABLE customers (...)",
                    "CREATE TABLE orders (...)",
                ],
                documentations=[
                    "The customers table contains...",
                    "The orders table contains...",
                ],
                question_sql_pairs=[
                    ("Who are the top customers?", "SELECT * FROM customers..."),
                    ("What are recent orders?", "SELECT * FROM orders..."),
                ]
            )
            ```
        """
        results = {
            "ddl_count": 0,
            "documentation_count": 0,
            "question_sql_count": 0,
        }

        if ddls:
            for ddl in ddls:
                try:
                    self.agent_memory.train_ddl(ddl)
                    results["ddl_count"] += 1
                except Exception as e:
                    logger.error(f"Failed to train DDL: {e}")

        if documentations:
            for doc in documentations:
                try:
                    self.agent_memory.train_documentation(doc)
                    results["documentation_count"] += 1
                except Exception as e:
                    logger.error(f"Failed to train documentation: {e}")

        if question_sql_pairs:
            for question, sql in question_sql_pairs:
                try:
                    self.agent_memory.train_question_sql(question, sql)
                    results["question_sql_count"] += 1
                except Exception as e:
                    logger.error(f"Failed to train question-SQL pair: {e}")

        logger.info(f"Bulk training completed: {results}")
        return results

    def get_agent_memory(self) -> VikingDBAgentMemory:
        """
        Get the underlying VikingDB agent memory instance.

        This can be used to initialize VannaToolSet with the trained data.

        Returns:
            VikingDBAgentMemory instance

        Example:
            ```python
            trainer = VannaTrainer(collection_prefix="my_project")
            trainer.train(ddl="...")

            # Use the trained memory in VannaToolSet
            vanna_toolset = VannaToolSet(
                connection_string="sqlite:///db.sqlite",
                agent_memory=trainer.get_agent_memory()
            )
            ```
        """
        return self.agent_memory

    def get_related_ddl(self, question: str, limit: int = 5) -> List[str]:
        """
        Get related DDL for a question (for debugging/testing).

        Args:
            question: User question
            limit: Maximum results

        Returns:
            List of related DDL statements
        """
        return self.agent_memory.get_related_ddl(question, limit)

    def get_related_documentation(self, question: str, limit: int = 5) -> List[str]:
        """
        Get related documentation for a question (for debugging/testing).

        Args:
            question: User question
            limit: Maximum results

        Returns:
            List of related documentation
        """
        return self.agent_memory.get_related_documentation(question, limit)
