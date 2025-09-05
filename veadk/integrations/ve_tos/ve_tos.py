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
import asyncio
from typing import Union
from pydantic import BaseModel, Field
from typing import Any
from urllib.parse import urlparse
from datetime import datetime

# Initialize logger before using it
logger = get_logger(__name__)

# Try to import tos module, and provide helpful error message if it fails
try:
    import tos
except ImportError as e:
    logger.error(
        "Failed to import 'tos' module. Please install it using: pip install tos\n"
    )
    raise ImportError(
        "Missing 'tos' module. Please install it using: pip install tos\n"
    ) from e


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


class VeTOS(BaseModel):
    config: TOSConfig = Field(default_factory=TOSConfig)

    def model_post_init(self, __context: Any) -> None:
        try:
            self._client = tos.TosClientV2(
                self.config.ak,
                self.config.sk,
                endpoint=f"tos-{self.config.region}.volces.com",
                region=self.config.region,
            )
            logger.info("Connected to TOS successfully.")
        except Exception as e:
            logger.error(f"Client initialization failed:{e}")
            self._client = None

    def _refresh_client(self):
        try:
            if self._client:
                self._client.close()
            self._client = tos.TosClientV2(
                self.config.ak,
                self.config.sk,
                endpoint=f"tos-{self.config.region}.volces.com",
                region=self.config.region,
            )
            logger.info("refreshed client successfully.")
        except Exception as e:
            logger.error(f"Failed to refresh client: {str(e)}")
            self._client = None

    def create_bucket(self) -> bool:
        """If the bucket does not exist, create it and set CORS rules"""
        if not self._client:
            logger.error("TOS client is not initialized")
            return False
        try:
            self._client.head_bucket(self.config.bucket_name)
            logger.info(f"Bucket {self.config.bucket_name} already exists")
        except tos.exceptions.TosServerError as e:
            if e.status_code == 404:
                try:
                    self._client.create_bucket(
                        bucket=self.config.bucket_name,
                        storage_class=tos.StorageClassType.Storage_Class_Standard,
                        acl=tos.ACLType.ACL_Public_Read,  # 公开读
                    )
                    logger.info(
                        f"Bucket {self.config.bucket_name} created successfully"
                    )
                    self._refresh_client()
                except Exception as create_error:
                    logger.error(f"Bucket creation failed: {str(create_error)}")
                    return False
            else:
                logger.error(f"Bucket check failed: {str(e)}")
                return False
        except Exception as e:
            logger.error(f"Bucket check failed: {str(e)}")
            return False

        # 确保在所有路径上返回布尔值
        return self._set_cors_rules()

    def _set_cors_rules(self) -> bool:
        if not self._client:
            logger.error("TOS client is not initialized")
            return False
        try:
            rule = tos.models2.CORSRule(
                allowed_origins=["*"],
                allowed_methods=["GET", "HEAD"],
                allowed_headers=["*"],
                max_age_seconds=1000,
            )
            self._client.put_bucket_cors(self.config.bucket_name, [rule])
            logger.info(
                f"CORS rules for bucket {self.config.bucket_name} set successfully"
            )
            return True
        except Exception as e:
            logger.error(
                f"Failed to set CORS rules for bucket {self.config.bucket_name}: {str(e)}"
            )
            return False

    def build_tos_url(
        self, user_id: str, app_name: str, session_id: str, data_path: str
    ) -> tuple[str, str]:
        """generate TOS object key"""
        parsed_url = urlparse(data_path)

        if parsed_url.scheme and parsed_url.scheme in ("http", "https", "ftp", "ftps"):
            file_name = os.path.basename(parsed_url.path)
        else:
            file_name = os.path.basename(data_path)

        timestamp: str = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
        object_key: str = f"{app_name}-{user_id}-{session_id}/{timestamp}-{file_name}"
        tos_url: str = f"https://{self.config.bucket_name}.tos-{self.config.region}.volces.com/{object_key}"

        return object_key, tos_url

    def upload(
        self,
        object_key: str,
        data: Union[str, bytes],
    ):
        if isinstance(data, str):
            # data is a file path
            return asyncio.to_thread(self._do_upload_file, object_key, data)
        elif isinstance(data, bytes):
            # data is bytes content
            return asyncio.to_thread(self._do_upload_bytes, object_key, data)
        else:
            error_msg = f"Upload failed: data type error. Only str (file path) and bytes are supported, got {type(data)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    def _do_upload_bytes(self, object_key: str, data: bytes) -> None:
        try:
            if not self._client:
                return
            if not self.create_bucket():
                return
            self._client.put_object(
                bucket=self.config.bucket_name, key=object_key, content=data
            )
            logger.debug(f"Upload success, object_key: {object_key}")
            self._close()
            return
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            self._close()
            return

    def _do_upload_file(self, object_key: str, file_path: str) -> None:
        try:
            if not self._client:
                return
            if not self.create_bucket():
                return
            self._client.put_object_from_file(
                bucket=self.config.bucket_name, key=object_key, file_path=file_path
            )
            self._close()
            logger.debug(f"Upload success, object_key: {object_key}")
            return
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            self._close()
            return

    def download(self, object_key: str, save_path: str) -> bool:
        """download image from TOS"""
        if not self._client:
            logger.error("TOS client is not initialized")
            return False
        try:
            object_stream = self._client.get_object(self.config.bucket_name, object_key)

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

    def _close(self):
        if self._client:
            self._client.close()
