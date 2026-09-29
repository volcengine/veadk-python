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

"""Refresh deployment credentials without depending on the MPA application."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, repr=False)
class Credentials:
    access_key_id: str
    secret_access_key: str
    session_token: str = ""


def load_volcengine_credentials(credential_file: str = "") -> Credentials:
    """Read each call; an explicitly configured rotating file takes priority."""
    if not credential_file and not (
        os.getenv("VOLCENGINE_ACCESS_KEY") and os.getenv("VOLCENGINE_SECRET_KEY")
    ):
        credential_file = "/var/run/secrets/iam/credential"
    if credential_file:
        try:
            payload = json.loads(Path(credential_file).read_text())
            keys = [
                payload.get(key) or payload.get(alias)
                for key, alias in (
                    ("access_key_id", "AccessKeyId"),
                    ("secret_access_key", "SecretAccessKey"),
                    ("session_token", "SessionToken"),
                )
            ]
            if not all(isinstance(value, str) and value.strip() for value in keys):
                raise ValueError()
            return Credentials(*keys)
        except (OSError, ValueError, TypeError, AttributeError):
            raise ValueError(
                "Deployment credential file is unavailable or invalid"
            ) from None
    ak = os.getenv("VOLCENGINE_ACCESS_KEY", "")
    sk = os.getenv("VOLCENGINE_SECRET_KEY", "")
    if not ak or not sk:
        raise ValueError(
            "Configure deployment credentials or a rotating credential file"
        )
    return Credentials(
        ak,
        sk,
        os.getenv("VOLCENGINE_SESSION_TOKEN") or os.getenv("VOLC_SESSIONTOKEN", ""),
    )
