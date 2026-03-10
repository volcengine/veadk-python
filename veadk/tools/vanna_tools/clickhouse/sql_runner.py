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

import pandas as pd

from vanna.capabilities.sql_runner import SqlRunner, RunSqlToolArgs
from vanna.core.tool import ToolContext


class ClickHouseRunner(SqlRunner):
    """ClickHouse implementation of the SqlRunner interface."""

    def __init__(
        self,
        host: str,
        database: str,
        user: str,
        password: str,
        port: int = 9000,
        **kwargs,
    ):
        """Initialize with ClickHouse connection parameters.

        Args:
            host: Database host address
            database: Database name
            user: Database user
            password: Database password
            port: Database port (default: 9000 for native protocol)
            **kwargs: Additional clickhouse_driver connection parameters
        """
        try:
            from clickhouse_driver import Client

            self.Client = Client
        except ImportError as e:
            raise ImportError(
                "clickhouse-driver package is required. "
                "Install with: pip install clickhouse-driver"
            ) from e

        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.kwargs = kwargs

    async def run_sql(self, args: RunSqlToolArgs, context: ToolContext) -> pd.DataFrame:
        """Execute SQL query against ClickHouse database and return results as DataFrame.

        Args:
            args: SQL query arguments
            context: Tool execution context

        Returns:
            DataFrame with query results

        Raises:
            Exception: If query execution fails
        """
        # Connect to the database
        client = self.Client(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            **self.kwargs,
        )

        try:
            # Execute the query
            result = client.execute(args.sql, with_column_types=True)

            # result is a tuple: (data, [(column_name, column_type), ...])
            data = result[0]
            columns = [col[0] for col in result[1]]

            # Create a pandas dataframe from the results
            df = pd.DataFrame(data, columns=columns)
            return df

        finally:
            client.disconnect()
