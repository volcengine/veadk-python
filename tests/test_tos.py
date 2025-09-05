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

import pytest
from unittest import mock

# Check if tos module is available
import importlib

TOS_AVAILABLE = False
try:
    importlib.import_module("veadk.integrations.ve_tos.ve_tos")
    TOS_AVAILABLE = True
except ImportError:
    pass

# Skip tests that require tos module if it's not available
require_tos = pytest.mark.skipif(not TOS_AVAILABLE, reason="tos module not available")

# 使用 pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
@require_tos
def mock_client(monkeypatch):
    import veadk.integrations.ve_tos.ve_tos as tos_mod

    fake_client = mock.Mock()

    monkeypatch.setenv("DATABASE_TOS_REGION", "test-region")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("DATABASE_TOS_BUCKET", "test-bucket")

    monkeypatch.setattr(tos_mod.tos, "TosClientV2", lambda *a, **k: fake_client)

    class FakeExceptions:
        class TosServerError(Exception):
            def __init__(
                self,
                msg: str,
                code: int = 0,
                host_id: str = "",
                resource: str = "",
                request_id: str = "",
                header=None,
            ):
                super().__init__(msg)
                self.status_code = code

    monkeypatch.setattr(tos_mod.tos, "exceptions", FakeExceptions)
    monkeypatch.setattr(
        tos_mod.tos,
        "StorageClassType",
        type("S", (), {"Storage_Class_Standard": "STANDARD"}),
    )
    monkeypatch.setattr(
        tos_mod.tos,
        "ACLType",
        type("A", (), {"ACL_Private": "private", "ACL_Public_Read": "public-read"}),
    )

    return fake_client


@pytest.fixture
@require_tos
def tos_client(mock_client):
    import veadk.integrations.ve_tos.ve_tos as tos_mod

    return tos_mod.VeTOS()


@require_tos
def test_create_bucket_exists(tos_client, mock_client):
    mock_client.head_bucket.return_value = None  # head_bucket 正常返回表示存在
    result = tos_client.create_bucket()
    assert result is True
    mock_client.create_bucket.assert_not_called()


@require_tos
def test_create_bucket_not_exists(tos_client, mock_client):
    import veadk.integrations.ve_tos.ve_tos as tos_mod

    exc = tos_mod.tos.exceptions.TosServerError(msg="not found", code=404)
    mock_client.head_bucket.side_effect = exc

    result = tos_client.create_bucket()
    assert result is True
    mock_client.create_bucket.assert_called_once()


@require_tos
@pytest.mark.asyncio
async def test_upload_bytes_success(tos_client, mock_client):
    mock_client.head_bucket.return_value = True
    data = b"hello world"

    result = await tos_client.upload("obj-key", data)
    assert result is None
    mock_client.put_object.assert_called_once()
    mock_client.close.assert_called_once()


@require_tos
@pytest.mark.asyncio
async def test_upload_file_success(tmp_path, tos_client, mock_client):
    mock_client.head_bucket.return_value = True
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello file")

    result = await tos_client.upload("obj-key", str(file_path))
    assert result is None
    mock_client.put_object_from_file.assert_called_once()
    mock_client.close.assert_called_once()


@require_tos
def test_download_success(tmp_path, tos_client, mock_client):
    save_path = tmp_path / "out.txt"
    mock_client.get_object.return_value = [b"abc", b"def"]

    result = tos_client.download("obj-key", str(save_path))
    assert result is True
    assert save_path.read_bytes() == b"abcdef"


@require_tos
def test_download_fail(tos_client, mock_client):
    mock_client.get_object.side_effect = Exception("boom")
    result = tos_client.download("obj-key", "somewhere.txt")
    assert result is False


@require_tos
@pytest.mark.skipif(TOS_AVAILABLE, reason="tos module is available")
def test_tos_import_error():
    """Test VeTOS behavior when tos module is not installed"""
    # Remove tos from sys.modules to simulate it's not installed
    import sys

    original_tos = sys.modules.get("tos")
    if "tos" in sys.modules:
        del sys.modules["tos"]

    try:
        # Try to import ve_tos module, which should raise ImportError
        with pytest.raises(ImportError) as exc_info:
            pass

        # Check that the error message contains installation instructions
        assert "pip install tos" in str(exc_info.value)
    finally:
        # Restore original state
        if original_tos is not None:
            sys.modules["tos"] = original_tos
