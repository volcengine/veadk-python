# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""TOS ContextBucket implementation of VeADK long-term memory."""

import json
import os
import threading
from typing import Any

from pydantic import Field, PrivateAttr

import veadk.config  # noqa: F401  # Load .env and config.yaml before settings.
from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.configs.database_configs import TOSContextBucketConfig
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from tos import TosClientV2
    from tos.exceptions import TosServerError
except ImportError as exc:
    raise ImportError(
        "TOS ContextBucket long-term memory requires the pre-release "
        "`tos>=2.9.4b1`, which is not installed. Install it with:\n"
        '    pip install --upgrade "tos>=2.9.4b1" --pre'
    ) from exc


# ContextBucket support was added to `TosClientV2` as new methods on an existing
# class, so importing `tos` succeeds even on older releases (e.g. 2.8.4) that lack
# the feature. Probe for the required methods explicitly to fail closed with a
# clear message instead of surfacing a swallowed AttributeError at call time.
_REQUIRED_CONTEXT_BUCKET_METHODS = (
    "create_context_bucket_memory",
    "search_context_bucket_memory",
)


def _resolve_tos_version() -> str:
    try:
        import tos

        version = getattr(tos, "__version__", None)
        # `tos.__version__` may itself be a module exposing `__version__`.
        return getattr(version, "__version__", None) or str(version) or "unknown"
    except Exception:  # pragma: no cover - best-effort version reporting
        return "unknown"


def _assert_context_bucket_supported() -> None:
    missing = [
        method
        for method in _REQUIRED_CONTEXT_BUCKET_METHODS
        if not hasattr(TosClientV2, method)
    ]
    if missing:
        raise RuntimeError(
            f"The installed `tos` SDK ({_resolve_tos_version()}) does not support "
            "TOS ContextBucket long-term memory "
            f"(missing methods: {', '.join(missing)}). "
            "This feature requires the pre-release `tos>=2.9.4b1`. Upgrade with:\n"
            '    pip install --upgrade "tos>=2.9.4b1" --pre'
        )


class TosContextBucketLTMBackend(BaseLongTermMemoryBackend):
    """Persist VeADK long-term memory through TOS ContextBucketMemory.

    The backend maps its index to one ContextBucket and each runtime user ID to
    a ContextSet. The service then performs memory inference and retrieval.
    """

    volcengine_access_key: str | None = Field(
        default_factory=lambda: os.getenv("VOLCENGINE_ACCESS_KEY")
    )
    volcengine_secret_key: str | None = Field(
        default_factory=lambda: os.getenv("VOLCENGINE_SECRET_KEY")
    )
    session_token: str = Field(
        default_factory=lambda: os.getenv("VOLCENGINE_SESSION_TOKEN", "")
    )
    context_bucket_name: str | None = Field(
        default_factory=lambda: os.getenv("DATABASE_TOS_CONTEXT_BUCKET_NAME")
    )
    account_id: str | None = Field(
        default_factory=lambda: os.getenv("DATABASE_TOS_CONTEXT_ACCOUNT_ID")
    )
    tos_context_config: TOSContextBucketConfig = Field(
        default_factory=TOSContextBucketConfig
    )

    _client: Any = PrivateAttr()
    _ensured_sets: set[str] = PrivateAttr(default_factory=set)
    _ensure_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def model_post_init(self, __context: Any) -> None:
        _assert_context_bucket_supported()

        if not self.account_id:
            raise ValueError(
                "DATABASE_TOS_CONTEXT_ACCOUNT_ID is required for the TOS "
                "ContextBucket long-term memory backend."
            )
        if not self.tos_context_config.control_endpoint:
            raise ValueError(
                "DATABASE_TOS_CONTEXT_CONTROL_ENDPOINT is required for the TOS "
                "ContextBucket long-term memory backend."
            )

        self.context_bucket_name = self.context_bucket_name or self.index
        self.precheck_index_naming()

        ak, sk, sts_token = self._get_ak_sk_sts()
        self._client = TosClientV2(
            ak,
            sk,
            self.tos_context_config.endpoint,
            self.tos_context_config.region,
            security_token=sts_token or None,
            control_endpoint=self.tos_context_config.control_endpoint,
        )
        self._ensure_context_bucket()

    def _get_ak_sk_sts(self) -> tuple[str, str, str]:
        """Resolve (access_key, secret_key, sts_token) for the TOS client.

        Mirrors the credential strategy of the VikingDB backend: use the
        explicitly provided AK/SK (with the STS token from
        ``VOLCENGINE_SESSION_TOKEN``) when both are present, otherwise fall back
        to the VeFaaS IAM credential file so cloud deployments authenticate
        with the instance role without static secrets.
        """
        if self.volcengine_access_key and self.volcengine_secret_key:
            logger.debug(
                "Using Volcengine credentials from environment for "
                "TosContextBucketLTMBackend."
            )
            return (
                self.volcengine_access_key,
                self.volcengine_secret_key,
                self.session_token,
            )

        cred = get_credential_from_vefaas_iam()
        logger.debug(
            "Using Volcengine credentials from VeFaaS IAM file for "
            "TosContextBucketLTMBackend."
        )
        return cred.access_key_id, cred.secret_access_key, cred.session_token

    def precheck_index_naming(self) -> None:
        name = self.context_bucket_name
        if not isinstance(name, str) or not 3 <= len(name) <= 63:
            raise ValueError(
                "Invalid TOS ContextBucket name: it must be 3-63 characters long. "
                "Set DATABASE_TOS_CONTEXT_BUCKET_NAME to override the app name."
            )
        if (
            name.startswith("-")
            or name.endswith("-")
            or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in name)
        ):
            raise ValueError(
                "Invalid TOS ContextBucket name: use lowercase letters, digits, "
                "and hyphens, without a leading or trailing hyphen. Set "
                "DATABASE_TOS_CONTEXT_BUCKET_NAME to override the app name."
            )

    @staticmethod
    def _status_code(error: Exception) -> int | None:
        return getattr(error, "status_code", None)

    def _ensure_context_bucket(self) -> None:
        try:
            self._client.get_context_bucket(
                account_id=self.account_id,
                context_bucket_name=self.context_bucket_name,
            )
        except TosServerError as error:
            if self._status_code(error) != 404:
                raise
            try:
                self._client.create_context_bucket(
                    account_id=self.account_id,
                    context_bucket_name=self.context_bucket_name,
                )
            except TosServerError as create_error:
                if self._status_code(create_error) != 409:
                    raise
                self._client.get_context_bucket(
                    account_id=self.account_id,
                    context_bucket_name=self.context_bucket_name,
                )

    def _context_set_name(self, user_id: str) -> str:
        """Return the ContextSet name for a user.

        Keeping this mapping in one place permits a future deterministic encoding
        if the service imposes stricter user-ID naming constraints.
        """
        return user_id

    @staticmethod
    def _validate_memory_context_set(context_set: Any, context_set_name: str) -> None:
        if not getattr(context_set, "enable", False) or "memory" not in (
            getattr(context_set, "scenes", None) or []
        ):
            raise ValueError(
                f"ContextSet {context_set_name!r} is not enabled for memory."
            )

    def _ensure_context_set(self, context_set_name: str) -> None:
        if context_set_name in self._ensured_sets:
            return

        with self._ensure_lock:
            if context_set_name in self._ensured_sets:
                return
            try:
                context_set = self._client.get_context_set(
                    account_id=self.account_id,
                    context_bucket_name=self.context_bucket_name,
                    context_set_name=context_set_name,
                )
                self._validate_memory_context_set(context_set, context_set_name)
            except TosServerError as error:
                if self._status_code(error) != 404:
                    raise
                try:
                    self._client.create_context_set(
                        account_id=self.account_id,
                        context_bucket_name=self.context_bucket_name,
                        context_set_name=context_set_name,
                        enable=True,
                        scenes=["memory"],
                    )
                except TosServerError as create_error:
                    if self._status_code(create_error) != 409:
                        raise
                    context_set = self._client.get_context_set(
                        account_id=self.account_id,
                        context_bucket_name=self.context_bucket_name,
                        context_set_name=context_set_name,
                    )
                    self._validate_memory_context_set(context_set, context_set_name)
            self._ensured_sets.add(context_set_name)

    @staticmethod
    def _to_content(event_string: str) -> str:
        try:
            payload = json.loads(event_string)
            parts = payload.get("parts") or []
            text = parts[0].get("text") if parts else None
            return text or event_string
        except (AttributeError, IndexError, TypeError, json.JSONDecodeError):
            return event_string

    def save_memory(self, user_id: str, event_strings: list[str], **kwargs) -> bool:
        if not event_strings:
            return True

        try:
            context_set_name = self._context_set_name(user_id)
            self._ensure_context_set(context_set_name)
            infer = kwargs.pop("infer", True)
            # Framework-level bookkeeping kwargs are not accepted by the TOS
            # ContextBucket SDK; drop them so they are not forwarded downstream.
            kwargs.pop("session_id", None)
            kwargs.pop("app_name", None)
            for event_string in event_strings:
                self._client.create_context_bucket_memory(
                    account_id=self.account_id,
                    context_bucket_name=self.context_bucket_name,
                    context_set_name=context_set_name,
                    content=self._to_content(event_string),
                    infer=infer,
                    **kwargs,
                )
            return True
        except Exception as error:
            logger.error(f"Failed to save memory to TOS ContextBucket: {error}")
            return False

    def search_memory(
        self, user_id: str, query: str, top_k: int, **kwargs
    ) -> list[str]:
        try:
            context_set_name = self._context_set_name(user_id)
            self._ensure_context_set(context_set_name)
            # Framework-level bookkeeping kwargs are not accepted by the TOS
            # ContextBucket SDK; drop them so they are not forwarded downstream.
            kwargs.pop("app_name", None)
            output = self._client.search_context_bucket_memory(
                account_id=self.account_id,
                context_bucket_name=self.context_bucket_name,
                context_set_name=context_set_name,
                query=query,
                limit=top_k,
                **kwargs,
            )
            return [
                result.memory
                for result in getattr(output, "results", [])
                if getattr(result, "memory", None)
            ]
        except Exception as error:
            logger.error(f"Failed to search memory from TOS ContextBucket: {error}")
            return []
