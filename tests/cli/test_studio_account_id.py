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

from types import SimpleNamespace
from typing import Any

import pytest

from veadk.cli.studio_account_id import (
    resolve_studio_account_id_metadata,
    studio_account_id_from_tos_bucket,
)


def test_resolves_account_id_from_function_role() -> None:
    result = resolve_studio_account_id_metadata(
        remote_function=SimpleNamespace(
            role="trn:iam::2100123456:role/VeADKFrontendServiceRole"
        )
    )

    assert result.account_id == "2100123456"
    assert result.error == ""


def test_resolves_account_id_from_studio_tos_bucket_after_sts_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail(**_: Any) -> str:
        raise RuntimeError("sts failed with secret-ak")

    monkeypatch.setattr(
        "frontend.server.storage.provisioning.resolve_studio_account_id_for_deploy",
        _fail,
    )

    result = resolve_studio_account_id_metadata(
        environment={"VEADK_STUDIO_TOS_BUCKET": "veadk-studio-2100123456"},
        access_key="secret-ak",
        secret_key="secret-sk",
        region="cn-beijing",
    )

    assert result.account_id == "2100123456"
    assert result.error == ""


def test_reports_sanitized_account_id_resolution_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail(**_: Any) -> str:
        raise RuntimeError("sts failed with secret-ak")

    monkeypatch.setattr(
        "frontend.server.storage.provisioning.resolve_studio_account_id_for_deploy",
        _fail,
    )

    result = resolve_studio_account_id_metadata(
        environment={"VEADK_STUDIO_TOS_BUCKET": "custom-studio-bucket"},
        access_key="secret-ak",
        secret_key="secret-sk",
        region="cn-beijing",
    )

    assert result.account_id == ""
    assert result.error == "sts failed with ***"


def test_parses_account_id_from_studio_tos_bucket_path() -> None:
    assert (
        studio_account_id_from_tos_bucket("tos://veadk-studio-2100123456/data")
        == "2100123456"
    )
