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

from __future__ import annotations

from typing import Any

import pymysql
from pydantic import BaseModel, Field
from typing_extensions import override

from veadk.config import getenv
from veadk.utils.logger import get_logger

from ..base_database import BaseDatabase

logger = get_logger(__name__)


class MysqlDatabaseConfig(BaseModel):
    host: str = Field(
        default_factory=lambda: getenv("DATABASE_MYSQL_HOST"),
        description="Mysql host",
    )
    user: str = Field(
        default_factory=lambda: getenv("DATABASE_MYSQL_USER"),
        description="Mysql user",
    )
    password: str = Field(
        default_factory=lambda: getenv("DATABASE_MYSQL_PASSWORD"),
        description="Mysql password",
    )
    database: str = Field(
        default_factory=lambda: getenv("DATABASE_MYSQL_DATABASE"),
        description="Mysql database",
    )
    charset: str = Field(
        default_factory=lambda: getenv("DATABASE_MYSQL_CHARSET", "utf8mb4"),
        description="Mysql charset",
    )


class MysqlDatabase(BaseModel, BaseDatabase):
    config: MysqlDatabaseConfig = Field(default_factory=MysqlDatabaseConfig)

    def model_post_init(self, context: Any, /) -> None:
        self._connection = pymysql.connect(
            host=self.config.host,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            charset=self.config.charset,
            cursorclass=pymysql.cursors.DictCursor,
        )
        self._connection.ping()
        logger.info("Connected to MySQL successfully.")

        self._type = "mysql"

    def table_exists(self, table: str) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (self.config.database, table),
            )
            result = cursor.fetchone()
            return result is not None

    @override
    def add(self, sql: str, params=None, **kwargs):
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            self._connection.commit()

    @override
    def query(self, sql: str, params=None, **kwargs) -> tuple[dict[str, Any], ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    @override
    def delete(self, **kwargs):
        table = kwargs.get("table")
        if table is None:
            app_name = kwargs.get("app_name", "default")
            table = app_name

        if not self.table_exists(table):
            logger.warning(f"Table {table} does not exist. Skipping delete operation.")
            return

        try:
            with self._connection.cursor() as cursor:
                # Drop the table directly
                sql = f"DROP TABLE `{table}`"
                cursor.execute(sql)
                self._connection.commit()
                logger.info(f"Dropped table {table}")
        except Exception as e:
            logger.error(f"Failed to drop table {table}: {e}")
            raise e

    def is_empty(self):
        pass
