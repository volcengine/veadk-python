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

from typing import Any
from typing_extensions import override
from pydantic import Field

from veadk.configs.database_configs import Mem0Config


from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from mem0 import MemoryClient

except ImportError:
    logger.error(
        "Failed to import mem0 or dotenv. Please install them with 'pip install mem0 '"
    )
    raise ImportError("Required packages not installed: mem0")


class Mem0LTMBackend(BaseLongTermMemoryBackend):
    """Mem0 long term memory backend implementation"""

    mem0_config: Mem0Config = Field(default_factory=Mem0Config)

    def model_post_init(self, __context: Any) -> None:
        """Initialize Mem0 client"""

        try:
            self._mem0_client = MemoryClient(
                host=self.mem0_config.base_url,  # mem0 endpoint
                api_key=self.mem0_config.api_key,  # mem0 API key
            )
            logger.info(
                f"Initialized Mem0 client for host: {self.mem0_config.base_url}"
            )
            logger.info(f"Initialized Mem0 client for index: {self.index}")
        except Exception as e:
            logger.error(
                f"Failed to initialize Mem0 client for host {self.mem0_config.base_url} : {str(e)}"
            )
            raise

    def precheck_index_naming(self):
        """Check if the index name is valid
        For Mem0, there are no specific naming constraints
        """
        pass

    @override
    def save_memory(self, event_strings: list[str], **kwargs) -> bool:
        """Save memory to Mem0

        Args:
            event_strings: List of event strings to save
            **kwargs: Additional parameters, including 'user_id' for Mem0

        Returns:
            bool: True if saved successfully, False otherwise
        """
        user_id = kwargs.get("user_id", "default_user")

        try:
            logger.info(
                f"Saving {len(event_strings)} events to Mem0 for user: {user_id}"
            )

            for event_string in event_strings:
                # Save event string to Mem0
                result = self._mem0_client.add(
                    [{"role": "user", "content": event_string}],
                    user_id=user_id,
                    output_format="v1.1",
                )
                logger.debug(f"Saved memory result: {result}")

            logger.info(f"Successfully saved {len(event_strings)} events to Mem0")
            return True
        except Exception as e:
            logger.error(f"Failed to save memory to Mem0: {str(e)}")
            return False

    @override
    def search_memory(self, query: str, top_k: int, **kwargs) -> list[str]:
        """Search memory from Mem0

        Args:
            query: Search query
            top_k: Number of results to return
            **kwargs: Additional parameters, including 'user_id' for Mem0

        Returns:
            list[str]: List of memory strings
        """
        user_id = kwargs.get("user_id", "default_user")

        try:
            logger.info(
                f"Searching Mem0 for query: {query}, user: {user_id}, top_k: {top_k}"
            )

            memories = self._mem0_client.search(
                query, user_id=user_id, output_format="v1.1", top_k=top_k
            )

            memory_list = []
            if memories.get("results", []):
                for mem in memories["results"]:
                    if "memory" in mem:
                        memory_list.append(mem["memory"])

            logger.info(f"Found {len(memory_list)} memories matching query: {query}")
            return memory_list
        except Exception as e:
            logger.error(f"Failed to search memory from Mem0: {str(e)}")
            return []
