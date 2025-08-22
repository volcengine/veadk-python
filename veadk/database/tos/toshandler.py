import os
from veadk.config import getenv
from veadk.utils.logger import get_logger
import tos
from datetime import datetime
import asyncio
from typing import Literal
from urllib.parse import urlparse

logger = get_logger(__name__)


class TOSHandler:
    def __init__(self):
        """Initialize TOS configuration information"""
        self.region = getenv("VOLCENGINE_REGION")
        self.ak = getenv("VOLCENGINE_ACCESS_KEY")
        self.sk = getenv("VOLCENGINE_SECRET_KEY")
        self.bucket_name = getenv("DATABASE_TOS_BUCKET")

    def _init_tos_client(self):
        """initialize TOS client"""
        try:
            return tos.TosClientV2(
                self.ak,
                self.sk,
                endpoint=f"tos-{self.region}.volces.com",
                region=self.region,
            )
        except Exception as e:
            logger.error(f"Client initialization failed:{e}")
            return None

    def get_suffix(self, data_path: str) -> str:
        """Extract the complete file suffix with leading dot (including compound suffixes such as .tar.gz)"""
        COMPOUND_SUFFIXES = {
            "tar.gz",
            "tar.bz2",
            "tar.xz",
            "tar.Z",
            "tar.lz",
            "tar.lzma",
            "tar.lzo",
            "gz",
            "bz2",
            "xz",
            "Z",
            "lz",
            "lzma",
            "lzo",
        }
        parsed = urlparse(data_path)
        path = parsed.path if parsed.scheme in ("http", "https") else data_path

        filename = os.path.basename(path).split("?")[0].split("#")[0]

        parts = filename.split(".")
        if len(parts) < 2:
            return ""
        for i in range(2, len(parts) + 1):
            candidate = ".".join(parts[-i:])
            if candidate in COMPOUND_SUFFIXES:
                return f".{candidate.lower()}"
        return f".{parts[-1].lower()}"

    def gen_url(self, user_id, app_name, session_id, data_path):
        """generate TOS URL"""
        suffix = self.get_suffix(data_path)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
        url = (
            f"{self.bucket_name}/{app_name}/{user_id}-{session_id}-{timestamp}{suffix}"
        )
        return url

    def parse_url(self, url):
        """Parse the URL to obtain bucket_name and object_key"""
        """bucket_name/object_key"""
        parts = url.split("/", 1)
        if len(parts) < 2:
            raise ValueError("URL format error, it should be: bucket_name/object_key")
        return parts

    def create_bucket(self, client, bucket_name):
        """If the bucket does not exist, create it"""
        try:
            client.head_bucket(self.bucket_name)
            logger.debug(f"Bucket {bucket_name} already exists")
            return True
        except tos.exceptions.TosServerError as e:
            if e.status_code == 404:
                client.create_bucket(
                    bucket=bucket_name,
                    storage_class=tos.StorageClassType.Storage_Class_Standard,
                    acl=tos.ACLType.ACL_Private,
                )
                logger.debug(f"Bucket {bucket_name} created successfully")
                return True
        except Exception as e:
            logger.error(f"Bucket creation failed: {str(e)}")
            return False

    def upload_to_tos(self, url: str, data, data_type: Literal["file", "bytes"]):
        if data_type not in ("file", "bytes"):
            error_msg = f"Upload failed: data_type error. Only 'file' and 'bytes' are supported, got {data_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        if data_type == "file":
            return asyncio.to_thread(self._do_upload_file, url, data)
        elif data_type == "bytes":
            return asyncio.to_thread(self._do_upload_bytes, url, data)

    def _do_upload_bytes(self, url, bytes):
        bucket_name, object_key = self.parse_url(url)
        client = self._init_tos_client()
        try:
            if not client:
                return False
            if not self.create_bucket(client, bucket_name):
                return False

            client.put_object(bucket=bucket_name, key=object_key, content=bytes)
            return True
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False
        finally:
            if client:
                client.close()

    def _do_upload_file(self, url, file_path):
        bucket_name, object_key = self.parse_url(url)
        client = self._init_tos_client()
        try:
            if not client:
                return False
            if not self.create_bucket(client, bucket_name):
                return False

            client.put_object_from_file(
                bucket=bucket_name, key=object_key, file_path=file_path
            )
            return True
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False
        finally:
            if client:
                client.close()

    def download_from_tos(self, url, save_path):
        """download image from TOS"""
        try:
            bucket_name, object_key = self.parse_url(url)
            client = self._init_tos_client()
            if not client:
                return False

            object_stream = client.get_object(bucket_name, object_key)

            save_dir = os.path.dirname(save_path)
            if save_dir and not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)

            with open(save_path, "wb") as f:
                for chunk in object_stream:
                    f.write(chunk)

            logger.debug(f"Image download success, saved to: {save_path}")
            client.close()
            return True

        except Exception as e:
            logger.error(f"Image download failed: {str(e)}")
            if "client" in locals():
                client.close()
            return False
