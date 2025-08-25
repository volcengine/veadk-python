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
from veadk.config import getenv
from veadk.utils.logger import get_logger
import tos
import asyncio
from typing import Literal, Union
from pydantic import BaseModel, Field
from typing import Optional, Any

logger = get_logger(__name__)


class TOSConfig(BaseModel):
    region: str = Field(
        default_factory=lambda: getenv("DATABASE_TOS_REGION"),
        description="TOS region",
    )
    ak: str = Field(
        default_factory=lambda: getenv("VOLCENGINE_ACCESS_KEY"),
        description="Volcengine access key",
    )
    sk: str = Field(
        default_factory=lambda: getenv("VOLCENGINE_SECRET_KEY"),
        description="Volcengine secret key",
    )
    bucket_name: str = Field(
        default_factory=lambda: getenv("DATABASE_TOS_BUCKET"),
        description="TOS bucket name",
    )


class TOSClient(BaseModel):
    config: TOSConfig = Field(default_factory=TOSConfig)
    client: Optional[Any] = Field(default=None, description="TOS client instance")

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.client = self._init()

    def _init(self):
        """initialize TOS client"""
        try:
            return tos.TosClientV2(
                self.config.ak,
                self.config.sk,
                endpoint=f"tos-{self.config.region}.volces.com",
                region=self.config.region,
            )
        except Exception as e:
            logger.error(f"Client initialization failed:{e}")
            return None

    def create_bucket(self) -> bool:
        """If the bucket does not exist, create it"""
        try:
            self.client.head_bucket(self.config.bucket_name)
            logger.info(f"Bucket {self.config.bucket_name} already exists")
            return True
        except tos.exceptions.TosServerError as e:
            if e.status_code == 404:
                self.client.create_bucket(
                    bucket=self.config.bucket_name,
                    storage_class=tos.StorageClassType.Storage_Class_Standard,
                    acl=tos.ACLType.ACL_Private,
                )
                logger.info(f"Bucket {self.config.bucket_name} created successfully")
                return True
        except Exception as e:
            logger.error(f"Bucket creation failed: {str(e)}")
            return False

    def upload(
        self,
        object_key: str,
        data: Union[str, bytes],
        data_type: Literal["file", "bytes"],
    ):
        if data_type not in ("file", "bytes"):
            error_msg = f"Upload failed: data_type error. Only 'file' and 'bytes' are supported, got {data_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        if data_type == "file":
            return asyncio.to_thread(self._do_upload_file, object_key, data)
        elif data_type == "bytes":
            return asyncio.to_thread(self._do_upload_bytes, object_key, data)

    def _do_upload_bytes(self, object_key: str, bytes: bytes) -> bool:
        try:
            if not self.client:
                return False
            if not self.create_bucket():
                return False

            self.client.put_object(
                bucket=self.config.bucket_name, key=object_key, content=bytes
            )
            return True
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False

    def _do_upload_file(self, object_key: str, file_path: str) -> bool:
        client = self._init_tos_client()
        try:
            if not client:
                return False
            if not self.create_bucket(client, self.config.bucket_name):
                return False

            client.put_object_from_file(
                bucket=self.config.bucket_name, key=object_key, file_path=file_path
            )
            return True
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False

    def download(self, object_key: str, save_path: str) -> bool:
        """download image from TOS"""
        try:
            object_stream = self.client.get_object(self.config.bucket_name, object_key)

            save_dir = os.path.dirname(save_path)
            if save_dir and not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)

            with open(save_path, "wb") as f:
                for chunk in object_stream:
                    f.write(chunk)

            logger.debug(f"Image download success, saved to: {save_path}")
            return True

        except Exception as e:
            logger.error(f"Image download failed: {str(e)}")

            return False

    def close_client(self):
        if self.client:
            self.client.close()
