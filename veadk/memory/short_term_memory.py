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
from typing import Literal

from google.adk.sessions import DatabaseSessionService, InMemorySessionService

from veadk.config import getenv
from veadk.utils.logger import get_logger

from .short_term_memory_processor import ShortTermMemoryProcessor

logger = get_logger(__name__)

DEFAULT_LOCAL_DATABASE_PATH = "/tmp/veadk_local_database.db"


class ShortTermMemory:
    """
    Short term memory class.

    This class is used to store short term memory.
    """

    def __init__(
        self,
        backend: Literal["local", "database", "mysql"] = "local",
        db_url: str = "",
        enable_memory_optimization: bool = False,
    ):
        self.backend = backend
        self.db_url = db_url

        if self.backend == "mysql":
            host = getenv("DATABASE_MYSQL_HOST")
            user = getenv("DATABASE_MYSQL_USER")
            password = getenv("DATABASE_MYSQL_PASSWORD")
            database = getenv("DATABASE_MYSQL_DATABASE")
            db_url = f"mysql+pymysql://{user}:{password}@{host}/{database}"

            self.db_url = db_url
            self.backend = "database"

        if self.backend == "local":
            logger.warning(
                f"Short term memory backend: {self.backend}, the history will be lost after application shutdown."
            )
            self.session_service = InMemorySessionService()
        elif self.backend == "database":
            if self.db_url == "" or self.db_url is None:
                logger.warning("The `db_url` is an empty or None string.")
                self._use_default_database()
            else:
                try:
                    self.session_service = DatabaseSessionService(db_url=self.db_url)
                    logger.info("Connected to database with db_url.")
                except Exception as e:
                    logger.error(f"Failed to connect to database, error: {e}.")
                    self._use_default_database()
        else:
            raise ValueError(f"Unknown short term memory backend: {self.backend}")

        if enable_memory_optimization and backend == "database":
            self.processor = ShortTermMemoryProcessor()
            intercept_get_session = self.processor.patch()
            self.session_service.get_session = intercept_get_session(
                self.session_service.get_session
            )

    def _use_default_database(self):
        self.db_url = DEFAULT_LOCAL_DATABASE_PATH
        logger.info(f"Using default local database {self.db_url}")
        if not os.path.exists(self.db_url):
            self.create_local_sqlite3_db(self.db_url)
        self.session_service = DatabaseSessionService(db_url="sqlite:///" + self.db_url)

    def create_local_sqlite3_db(self, path: str):
        import sqlite3

        conn = sqlite3.connect(path)
        conn.close()
        logger.debug(f"Create local sqlite3 database {path} done.")

    async def create_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ):
        if isinstance(self.session_service, DatabaseSessionService):
            list_sessions_response = await self.session_service.list_sessions(
                app_name=app_name, user_id=user_id
            )

            logger.debug(
                f"Loaded {len(list_sessions_response.sessions)} sessions from db {self.db_url}."
            )

        if (
            await self.session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
            is None
        ):
            # create a new session for this running
            await self.session_service.create_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
