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
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from io import StringIO
import asyncio
import os
from datetime import datetime
from typing import TYPE_CHECKING, Union, List, Optional
from urllib.parse import urlparse

from veadk.consts import DEFAULT_TOS_BUCKET_NAME
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    pass


# Initialize logger before using it
logger = get_logger(__name__)


class VeTOS:
    def __init__(
        self,
        ak: str = "",
        sk: str = "",
        region: str = "cn-beijing",
        bucket_name: str = DEFAULT_TOS_BUCKET_NAME,
    ) -> None:
        self.ak = ak if ak else os.getenv("VOLCENGINE_ACCESS_KEY", "")
        self.sk = sk if sk else os.getenv("VOLCENGINE_SECRET_KEY", "")
        # Add empty value validation
        if not self.ak or not self.sk:
            raise ValueError(
                "VOLCENGINE_ACCESS_KEY and VOLCENGINE_SECRET_KEY must be provided "
                "either via parameters or environment variables."
            )
            
        self.region = region
        self.bucket_name = bucket_name
        self._tos_module = None

        try:
            import tos

            self._tos_module = tos
        except ImportError as e:
            logger.error(
                "Failed to import 'tos' module. Please install it using: pip install tos\n"
            )
            raise ImportError(
                "Missing 'tos' module. Please install it using: pip install tos\n"
            ) from e

        self._client = None
        try:
            self._client = self._tos_module.TosClientV2(
                ak=self.ak,
                sk=self.sk,
                endpoint=f"tos-{self.region}.volces.com",
                region=self.region,
            )
            logger.info("Init TOS client.")
        except Exception as e:
            logger.error(f"Client initialization failed: {e}")

    def _refresh_client(self):
        try:
            if self._client:
                self._client.close()
            self._client = self._tos_module.TosClientV2(
                self.ak,
                self.sk,
                endpoint=f"tos-{self.region}.volces.com",
                region=self.region,
            )
            logger.info("refreshed client successfully.")
        except Exception as e:
            logger.error(f"Failed to refresh client: {str(e)}")
            self._client = None

    def _check_bucket_name(self, bucket_name: str = None) -> str:
        if not bucket_name:
            bucket_name = self.bucket_name
        return bucket_name
            
    def bucket_exists(self, bucket_name: str) -> bool:
        """Check if bucket exists
        
        Args:
            bucket_name: Bucket name
            
        Returns:
            bool: True if bucket exists, False otherwise
        """
        bucket_name = self._check_bucket_name(bucket_name)
        if not self._client:
            logger.error("TOS client is not initialized")
            return False
            
        try:
            self._client.head_bucket(bucket_name)
            logger.debug(f"Bucket {bucket_name} exists")
            return True
        except self._tos_module.exceptions.TosServerError as e:
            if e.status_code == 404:
                logger.debug(f"Bucket {bucket_name} does not exist")
                return False
            elif e.status_code == 403:
                logger.error(f"Access denied when checking bucket {bucket_name}: {str(e)}")
                return False
            else:
                logger.error(f"Failed to check bucket {bucket_name}: status_code={e.status_code}, {str(e)}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error when checking bucket {bucket_name}: {str(e)}")
            return False

    def create_bucket(self, bucket_name: str = None) -> bool:
        """Create bucket (if not exists)
        
        Args:
            bucket_name: Bucket name
            
        Returns:
            bool: True if bucket exists or created successfully, False otherwise
        """
        bucket_name = self._check_bucket_name(bucket_name)
        if not self._client:
            logger.error("TOS client is not initialized")
            return False
        
        # Check if bucket already exists
        if self.bucket_exists(bucket_name):
            logger.info(f"Bucket {bucket_name} already exists, no need to create")
            return True
        
        # Try to create bucket
        try:
            logger.info(f"Attempting to create bucket: {bucket_name}")
            self._client.create_bucket(
                bucket=bucket_name,
                storage_class=self._tos_module.StorageClassType.Storage_Class_Standard,
                acl=self._tos_module.ACLType.ACL_Public_Read,
            )
            logger.info(f"Bucket {bucket_name} created successfully")
            self._refresh_client()
        except self._tos_module.exceptions.TosServerError as e:
            logger.error(f"Failed to create bucket {bucket_name}: status_code={e.status_code}, {str(e)}")
            return False
            
        # Set CORS rules
        return self._set_cors_rules(bucket_name)

    def _set_cors_rules(self, bucket_name: str) -> bool:
        bucket_name = self._check_bucket_name(bucket_name)
            
        if not self._client:
            logger.error("TOS client is not initialized")
            return False
        try:
            rule = self._tos_module.models2.CORSRule(
                allowed_origins=["*"],
                allowed_methods=["GET", "HEAD"],
                allowed_headers=["*"],
                max_age_seconds=1000,
            )
            self._client.put_bucket_cors(bucket_name, [rule])
            logger.info(f"CORS rules for bucket {bucket_name} set successfully")
            return True
        except Exception as e:
            logger.error(
                f"Failed to set CORS rules for bucket {bucket_name}: {str(e)}"
            )
            return False

    def _build_object_key_for_file(
        self, data_path: str
    ) -> str:
        """generate TOS object key"""
        parsed_url = urlparse(data_path)
    
        # Generate object key
        if parsed_url.scheme in ("http", "https", "ftp", "ftps"):
            # For URL, remove protocol part, keep domain and path
            object_key = f"{parsed_url.netloc}{parsed_url.path}"
        else:
            # For local files, use path relative to current working directory
            abs_path = os.path.abspath(data_path)
            cwd = os.getcwd()
            # If file is in current working directory or its subdirectories, use relative path
            try:
                rel_path = os.path.relpath(abs_path, cwd)
                # Check if path contains relative path symbols (../, ./ etc.)
                if (not rel_path.startswith('../') and 
                    not rel_path.startswith('..\\') and 
                    not rel_path.startswith('./') and 
                    not rel_path.startswith('.\\')):
                    object_key = rel_path
                else:
                    # If path contains relative path symbols, use only filename
                    object_key = os.path.basename(data_path)
            except ValueError:
                # If unable to calculate relative path (cross-volume), use filename
                object_key = os.path.basename(data_path)
            
            # Remove leading slash to avoid signature errors
            if object_key.startswith('/'):
                object_key = object_key[1:]
                
            # If object key is empty or contains unsafe path symbols, use filename
            if (not object_key or 
                '../' in object_key or 
                '..\\' in object_key or 
                './' in object_key or 
                '.\\' in object_key):
                object_key = os.path.basename(data_path)

        return object_key
    
    def _build_object_key_for_text(
        self
    ) -> str:
        """generate TOS object key"""

        object_key: str = f"{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"

        return object_key
    
    def _build_object_key_for_bytes(self) -> str:
        
        object_key: str = f"{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return object_key
    
    def build_tos_url(self, object_key: str, bucket_name: str=None) -> str:
        bucket_name = self._check_bucket_name(bucket_name)
        tos_url: str = (
            f"https://{bucket_name}.tos-{self.region}.volces.com/{object_key}"
        )
        return tos_url

    # def upload(
    #     self,
    #     data: Union[str, bytes],
    #     bucket_name: str,
    #     object_key: str
    # ):
    #     if not bucket_name:
    #         bucket_name = self.bucket_name
    #     if isinstance(data, str):
    #         # data is a file path
    #         return asyncio.to_thread(self.upload_file, data, bucket_name, object_key)
    #     elif isinstance(data, bytes):
    #         # data is bytes content
    #         return asyncio.to_thread(self.upload_bytes, data, bucket_name, object_key)
    #     else:
    #         error_msg = f"Upload failed: data type error. Only str (file path) and bytes are supported, got {type(data)}"
    #         logger.error(error_msg)
    #         raise ValueError(error_msg)
        
    def _ensure_client_and_bucket(self, bucket_name: str) -> bool:
        """Ensure TOS client is initialized and bucket exists
        
        Args:
            bucket_name: Bucket name
            
        Returns:
            bool: True if client is initialized and bucket exists, False otherwise
        """
        if not self._client:
            logger.error("TOS client is not initialized")
            return False
        if not self.create_bucket(bucket_name):
            logger.error(f"Failed to create or access bucket: {bucket_name}")
            return False
        return True

    def upload_text(self, text: str, bucket_name: str=None , object_key: str=None) -> None:
        """Upload text content to TOS bucket
        
        Args:
            text: Text content to upload
            bucket_name: TOS bucket name
            object_key: Object key, auto-generated if None
        """
        bucket_name = self._check_bucket_name(bucket_name)
        if not object_key:
            object_key = self._build_object_key_for_text()
        
        if not self._ensure_client_and_bucket(bucket_name):
            return
        data = StringIO(text)
        try:
            self._client.put_object(
                bucket=bucket_name, key=object_key, content=data
            )
            logger.debug(f"Upload success, object_key: {object_key}")
            return 
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return 
        finally:
            data.close()

    async def async_upload_text(self, text: str, bucket_name: str=None, object_key: str=None) -> None:
        """Asynchronously upload text content to TOS bucket
        
        Args:
            text: Text content to upload
            bucket_name: TOS bucket name
            object_key: Object key, auto-generated if None
        """
        bucket_name = self._check_bucket_name(bucket_name)
        if not object_key:
            object_key = self._build_object_key_for_text()
        # Use common function to check client and bucket
        if not self._ensure_client_and_bucket(bucket_name):
            return
        data = StringIO(text)
        try:
            # Use asyncio.to_thread to execute blocking TOS operations in thread
            await asyncio.to_thread(
                self._client.put_object,
                bucket=bucket_name, 
                key=object_key, 
                content=data
            )
            logger.debug(f"Async upload success, object_key: {object_key}")
            return 
        except Exception as e:
            logger.error(f"Async upload failed: {e}")
            return 
        finally:
            data.close()

    def upload_bytes(self, data: bytes, bucket_name: str=None, object_key: str=None) -> None:
        """Upload byte data to TOS bucket
        
        Args:
            data: Byte data to upload
            bucket_name: TOS bucket name
            object_key: Object key, auto-generated if None
        """
        bucket_name = self._check_bucket_name(bucket_name)
        if not object_key:
            object_key = self._build_object_key_for_bytes()
        # Use common function to check client and bucket
        if not self._ensure_client_and_bucket(bucket_name):
            return
        try:
            self._client.put_object(
                bucket=bucket_name, key=object_key, content=data
            )
            logger.debug(f"Upload success, object_key: {object_key}")
            return
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return
        
    async def async_upload_bytes(self, data: bytes, bucket_name: str=None, object_key: str=None) -> None:
        """Asynchronously upload byte data to TOS bucket
        
        Args:
            data: Byte data to upload
            bucket_name: TOS bucket name
            object_key: Object key, auto-generated if None
        """
        bucket_name = self._check_bucket_name(bucket_name)
        if not object_key:
            object_key = self._build_object_key_for_bytes()
        # Use common function to check client and bucket
        if not self._ensure_client_and_bucket(bucket_name):
            return
        try:
            # Use asyncio.to_thread to execute blocking TOS operations in thread
            await asyncio.to_thread(
                self._client.put_object,
                bucket=bucket_name, 
                key=object_key, 
                content=data
            )
            logger.debug(f"Async upload success, object_key: {object_key}")
            return
        except Exception as e:
            logger.error(f"Async upload failed: {e}")
            return
        
    def upload_file(self, file_path: str, bucket_name: str=None, object_key: str = None) -> None:
        """Upload file to TOS bucket
        
        Args:
            file_path: Local file path
            bucket_name: TOS bucket name
            object_key: Object key, auto-generated if None
        """
        bucket_name = self._check_bucket_name(bucket_name)
        if not object_key:
            object_key = self._build_object_key_for_file(file_path)
        # Use common function to check client and bucket
        if not self._ensure_client_and_bucket(bucket_name):
            return
        try:
            self._client.put_object_from_file(
                bucket=bucket_name, key=object_key, file_path=file_path
            )
            logger.debug(f"Upload success, object_key: {object_key}")
            return
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return
        
    async def async_upload_file(self, file_path: str, bucket_name: str=None, object_key: str = None) -> None:
        """Asynchronously upload file to TOS bucket
        
        Args:
            file_path: Local file path
            bucket_name: TOS bucket name
            object_key: Object key, auto-generated if None
        """
        bucket_name = self._check_bucket_name(bucket_name)
        if not object_key:
            object_key = self._build_object_key_for_file(file_path)
        # Use common function to check client and bucket
        if not self._ensure_client_and_bucket(bucket_name):
            return
        try:
            # Use asyncio.to_thread to execute blocking TOS operations in thread
            await asyncio.to_thread(
                self._client.put_object_from_file,
                bucket=bucket_name, 
                key=object_key, 
                file_path=file_path
            )
            logger.debug(f"Async upload success, object_key: {object_key}")
            return
        except Exception as e:
            logger.error(f"Async upload failed: {e}")
            return
        
    def upload_files(self, file_paths: List[str], bucket_name: str=None, object_keys: Optional[List[str]] = None) -> None:
        """Upload multiple files to TOS bucket
        
        Args:
            file_paths: List of local file paths
            bucket_name: TOS bucket name
            object_keys: List of object keys, auto-generated if empty or length mismatch
        """
        bucket_name = self._check_bucket_name(bucket_name)
        
        # If object_keys is None, create empty list
        if object_keys is None:
            object_keys = []
            
        # If object_keys length doesn't match file_paths, generate object key for each file
        if len(object_keys) != len(file_paths):
            object_keys = []
            for file_path in file_paths:
                object_key = self._build_object_key_for_file(file_path)
                object_keys.append(object_key)
            logger.debug(f"Generated object keys: {object_keys}")
        
        # Upload each file
        try:
            for file_path, object_key in zip(file_paths, object_keys):
                # Note: upload_file method doesn't return value, we use exceptions to determine success
                self.upload_file(file_path, bucket_name, object_key)
            return
        except Exception as e:
            logger.error(f"Upload files failed: {str(e)}")
            return

    async def async_upload_files(self, file_paths: List[str], bucket_name: str=None, object_keys: Optional[List[str]] = None) -> None:
        """Asynchronously upload multiple files to TOS bucket
        
        Args:
            file_paths: List of local file paths
            bucket_name: TOS bucket name
            object_keys: List of object keys, auto-generated if empty or length mismatch
        """
        bucket_name = self._check_bucket_name(bucket_name)
        
        # If object_keys is None, create empty list
        if object_keys is None:
            object_keys = []
            
        # If object_keys length doesn't match file_paths, generate object key for each file
        if len(object_keys) != len(file_paths):
            object_keys = []
            for file_path in file_paths:
                object_key = self._build_object_key_for_file(file_path)
                object_keys.append(object_key)
            logger.debug(f"Generated object keys: {object_keys}")
        
        # Upload each file
        try:
            for file_path, object_key in zip(file_paths, object_keys):
                # Use asyncio.to_thread to execute blocking TOS operations in thread
                await asyncio.to_thread(
                    self._client.put_object_from_file,
                    bucket=bucket_name, 
                    key=object_key, 
                    file_path=file_path
                )
                logger.debug(f"Async upload success, object_key: {object_key}")
            return
        except Exception as e:
            logger.error(f"Async upload files failed: {str(e)}")
            return

    def upload_directory(self, directory_path: str, bucket_name: str=None) -> None:
        """Upload entire directory to TOS bucket
        
        Args:
            directory_path: Local directory path
            bucket_name: TOS bucket name
        """
        bucket_name = self._check_bucket_name(bucket_name)

        def _upload_dir(root_dir):
            items = os.listdir(root_dir)
            for item in items:
                path = os.path.join(root_dir, item)
                if os.path.isdir(path):
                    _upload_dir(path)
                if os.path.isfile(path):
                    # Use relative path of file as object key
                    object_key = os.path.relpath(path, directory_path)
                    # upload_file method doesn't return value, use exceptions to determine success
                    self.upload_file(path, bucket_name, object_key)

        try:
            _upload_dir(directory_path)
            logger.debug(f"Upload directory success: {directory_path}")
            return
        except Exception as e:
            logger.error(f"Upload directory failed: {str(e)}")
            raise
         
    async def async_upload_directory(self, directory_path: str, bucket_name: str=None) -> None:
        """Asynchronously upload entire directory to TOS bucket
        
        Args:
            directory_path: Local directory path
            bucket_name: TOS bucket name
        """
        bucket_name = self._check_bucket_name(bucket_name)

        async def _aupload_dir(root_dir):
            items = os.listdir(root_dir)
            for item in items:
                path = os.path.join(root_dir, item)
                if os.path.isdir(path):
                    await _aupload_dir(path)
                if os.path.isfile(path):
                    # Use relative path of file as object key
                    object_key = os.path.relpath(path, directory_path)
                    # Asynchronously upload single file
                    await self.async_upload_file(path, bucket_name, object_key)

        try:
            await _aupload_dir(directory_path)
            logger.debug(f"Async upload directory success: {directory_path}")
            return
        except Exception as e:
            logger.error(f"Async upload directory failed: {str(e)}")
            raise

    def download(self, bucket_name: str, object_key: str, save_path: str) -> bool:
        """download object from TOS"""
        bucket_name = self._check_bucket_name(bucket_name)
            
        if not self._client:
            logger.error("TOS client is not initialized")
            return False
        try:
            object_stream = self._client.get_object(bucket_name, object_key)

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

    def close(self):
        if self._client:
            self._client.close()
