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

try:
    from typing_extensions import override
except ImportError:
    from typing import override
from typing import List, Optional
from veadk.tools.vanna_tools.file_system import (
    WriteFileTool,
    ReadFileTool,
    ListFilesTool,
    SearchFilesTool,
    EditFileTool,
)
from veadk.tools.vanna_tools.agent_memory import (
    SaveQuestionToolArgsTool,
    SearchSavedCorrectToolUsesTool,
    SaveTextMemoryTool,
)
from veadk.tools.vanna_tools.run_sql import RunSqlTool
from veadk.tools.vanna_tools.visualize_data import VisualizeDataTool
from veadk.tools.vanna_tools.summarize_data import SummarizeDataTool
from veadk.tools.vanna_tools.python import RunPythonFileTool, PipInstallTool
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import BaseTool
from google.adk.tools.base_toolset import BaseToolset


class VannaToolSet(BaseToolset):
    def __init__(self, connection_string: str, file_storage: str = "/tmp/data"):
        super().__init__()
        self.connection_string = connection_string
        self.file_storage = file_storage
        self._post_init()

    def _post_init(self):
        """
        Initialize the VannaToolkit with the connection string and file storage.

        Args:
            connection_string (str): The connection string for the database.
                Supported formats:
                - sqlite:///path/to/database.db
                - postgresql://user:password@host:port/database
                - mysql://user:password@host:port/database
            file_storage (str, optional): The directory to store files. Defaults to "/tmp/data".
        """

        from vanna.integrations.sqlite import SqliteRunner
        from vanna.integrations.postgres import PostgresRunner
        from vanna.integrations.mysql import MySQLRunner
        from vanna.tools import LocalFileSystem
        from vanna.integrations.local.agent_memory import DemoAgentMemory

        # 验证连接字符串格式
        if not self.connection_string:
            raise ValueError("Connection string cannot be empty")

        # 检查连接字符串格式
        if self.connection_string.startswith("sqlite://"):
            if len(self.connection_string) <= len("sqlite://"):
                raise ValueError(
                    "Invalid SQLite connection string format. Expected: sqlite:///path/to/database.db"
                )
            self.runner = SqliteRunner(
                database_path=self.connection_string[len("sqlite://") :]
            )
        elif self.connection_string.startswith("postgresql://"):
            if "@" not in self.connection_string or "/" not in self.connection_string:
                raise ValueError(
                    "Invalid PostgreSQL connection string format. Expected: postgresql://user:password@host:port/database"
                )
            self.runner = PostgresRunner(connection_string=self.connection_string)
        elif self.connection_string.startswith("mysql://"):
            if "@" not in self.connection_string or "/" not in self.connection_string:
                raise ValueError(
                    "Invalid MySQL connection string format. Expected: mysql://user:password@host:port/database"
                )
            try:
                host = (
                    self.connection_string[len("mysql://") :]
                    .split("@")[1]
                    .split("/")[0]
                    .split(":")[0]
                )
                database = (
                    self.connection_string[len("mysql://") :]
                    .split("@")[1]
                    .split("/")[1]
                )
                user = (
                    self.connection_string[len("mysql://") :]
                    .split("@")[0]
                    .split(":")[0]
                )
                password = (
                    self.connection_string[len("mysql://") :]
                    .split("@")[0]
                    .split(":")[1]
                )
                port_str = (
                    self.connection_string[len("mysql://") :]
                    .split("@")[1]
                    .split("/")[0]
                    .split(":")[1]
                )
                port = int(port_str)
                self.runner = MySQLRunner(
                    host=host,
                    database=database,
                    user=user,
                    password=password,
                    port=port,
                )
            except (IndexError, ValueError) as e:
                raise ValueError(f"Invalid MySQL connection string format: {e}") from e
        else:
            raise ValueError(
                "Unsupported connection string format. Please use sqlite://, postgresql://, or mysql://"
            )

        if not os.path.exists(self.file_storage):
            os.makedirs(self.file_storage, exist_ok=True)

        self.file_system = LocalFileSystem(working_directory=self.file_storage)
        self.agent_memory = DemoAgentMemory(max_items=1000)

        self._tools = {
            "SaveQuestionToolArgsTool": SaveQuestionToolArgsTool(
                agent_memory=self.agent_memory,
            ),
            "SearchSavedCorrectToolUsesTool": SearchSavedCorrectToolUsesTool(
                agent_memory=self.agent_memory,
            ),
            "SaveTextMemoryTool": SaveTextMemoryTool(
                agent_memory=self.agent_memory,
            ),
            "WriteFileTool": WriteFileTool(
                file_system=self.file_system,
                agent_memory=self.agent_memory,
            ),
            "ReadFileTool": ReadFileTool(
                file_system=self.file_system,
                agent_memory=self.agent_memory,
            ),
            "ListFilesTool": ListFilesTool(
                file_system=self.file_system,
                agent_memory=self.agent_memory,
            ),
            "SearchFilesTool": SearchFilesTool(
                file_system=self.file_system,
                agent_memory=self.agent_memory,
            ),
            "EditFileTool": EditFileTool(
                file_system=self.file_system,
                agent_memory=self.agent_memory,
            ),
            "RunPythonFileTool": RunPythonFileTool(
                file_system=self.file_system,
                agent_memory=self.agent_memory,
            ),
            "PipInstallTool": PipInstallTool(
                file_system=self.file_system,
                agent_memory=self.agent_memory,
            ),
            "RunSqlTool": RunSqlTool(
                sql_runner=self.runner,
                file_system=self.file_system,
                agent_memory=self.agent_memory,
            ),
            "SummarizeDataTool": SummarizeDataTool(
                file_system=self.file_system,
                agent_memory=self.agent_memory,
            ),
            "VisualizeDataTool": VisualizeDataTool(
                file_system=self.file_system,
                agent_memory=self.agent_memory,
            ),
        }

    @override
    async def get_tools(
        self, readonly_context: Optional[ReadonlyContext] = None
    ) -> List[BaseTool]:
        return list(self._tools.values())
