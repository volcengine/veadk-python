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
import veadk.integrations.ve_tos.ve_tos as tos_mod

# 使用 pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def mock_client(monkeypatch):
    fake_client = mock.Mock()

    monkeypatch.setattr(tos_mod.tos, "TosClientV2", lambda *a, **k: fake_client)

    class FakeExceptions:
        class TosServerError(Exception):
            def __init__(self, msg):
                super().__init__(msg)
                self.status_code = None

    monkeypatch.setattr(tos_mod.tos, "exceptions", FakeExceptions)
    monkeypatch.setattr(
        tos_mod.tos,
        "StorageClassType",
        type("S", (), {"Storage_Class_Standard": "STANDARD"}),
    )
    monkeypatch.setattr(
        tos_mod.tos, "ACLType", type("A", (), {"ACL_Private": "private"})
    )

    return fake_client


@pytest.fixture
def tos_client(mock_client):
    return tos_mod.VeTOS()


def test_create_bucket_exists(tos_client, mock_client):
    mock_client.head_bucket.return_value = None  # head_bucket 正常返回表示存在
    result = tos_client.create_bucket()
    assert result is True
    mock_client.create_bucket.assert_not_called()


def test_create_bucket_not_exists(tos_client, mock_client):
    exc = tos_mod.tos.exceptions.TosServerError("not found")
    exc.status_code = 404
    mock_client.head_bucket.side_effect = exc

    result = tos_client.create_bucket()
    assert result is True
    mock_client.create_bucket.assert_called_once()


@pytest.mark.asyncio
async def test_upload_bytes_success(tos_client, mock_client):
    mock_client.head_bucket.return_value = True
    data = b"hello world"

    result = await tos_client.upload("obj-key", data)
    assert result is True
    mock_client.put_object.assert_called_once()
    mock_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_upload_file_success(tmp_path, tos_client, mock_client):
    mock_client.head_bucket.return_value = True
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello file")

    result = await tos_client.upload("obj-key", str(file_path))
    assert result is True
    mock_client.put_object_from_file.assert_called_once()
    mock_client.close.assert_called_once()


def test_download_success(tmp_path, tos_client, mock_client):
    save_path = tmp_path / "out.txt"
    mock_client.get_object.return_value = [b"abc", b"def"]

    result = tos_client.download("obj-key", str(save_path))
    assert result is True
    assert save_path.read_bytes() == b"abcdef"


def test_download_fail(tos_client, mock_client):
    mock_client.get_object.side_effect = Exception("boom")
    result = tos_client.download("obj-key", "somewhere.txt")
    assert result is False
