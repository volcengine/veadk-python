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

import os

import pytest

from tests.cli.provider_environment import (
    CLI_PROVIDER_ENV_KEYS,
    preserve_cli_provider_environment,
)


@pytest.mark.parametrize("original", [None, "volcengine"])
def test_direct_cli_provider_mutations_are_restored(
    monkeypatch: pytest.MonkeyPatch,
    original: str | None,
) -> None:
    for name in CLI_PROVIDER_ENV_KEYS:
        if original is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, original)

    with preserve_cli_provider_environment():
        for name in CLI_PROVIDER_ENV_KEYS:
            os.environ[name] = "byteplus"

    assert {name: os.environ.get(name) for name in CLI_PROVIDER_ENV_KEYS} == {
        name: original for name in CLI_PROVIDER_ENV_KEYS
    }
