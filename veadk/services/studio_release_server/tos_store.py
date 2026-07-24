"""TOS-backed durable state and VeFaaS IAM credential resolution."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from veadk.services.studio_release_server.models import (
    ReleaseServerSettings,
    ReleaseStatus,
)

_IAM_CREDENTIAL_PATH = Path("/var/run/secrets/iam/credential")


@dataclass(frozen=True)
class VolcengineCredentials:
    """One AK/SK pair with an optional STS token."""

    access_key: str
    secret_key: str
    session_token: str


def resolve_credentials() -> VolcengineCredentials:
    """Prefer explicit credentials locally, otherwise use VeFaaS IAM."""
    access_key = os.getenv("VOLCENGINE_ACCESS_KEY", "").strip()
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY", "").strip()
    if bool(access_key) != bool(secret_key):
        raise ValueError("VOLCENGINE_ACCESS_KEY and VOLCENGINE_SECRET_KEY must match.")
    if access_key and secret_key:
        return VolcengineCredentials(
            access_key=access_key,
            secret_key=secret_key,
            session_token=os.getenv("VOLCENGINE_SESSION_TOKEN", "").strip(),
        )
    if not _IAM_CREDENTIAL_PATH.is_file():
        raise FileNotFoundError(
            "VeFaaS IAM credential file is unavailable and no AK/SK was provided."
        )
    payload = json.loads(_IAM_CREDENTIAL_PATH.read_text(encoding="utf-8"))
    return VolcengineCredentials(
        access_key=str(payload["access_key_id"]),
        secret_key=str(payload["secret_access_key"]),
        session_token=str(payload["session_token"]),
    )


class JobStore(Protocol):
    """Persistence contract used by the release orchestrator."""

    def get(self, job_id: str) -> ReleaseStatus | None:
        """Return one job, or None when it does not exist."""
        ...

    def put(self, status: ReleaseStatus) -> None:
        """Persist the complete current job state."""
        ...


class TosJobStore:
    """Persist release status independently of VeFaaS instances."""

    def __init__(
        self,
        settings: ReleaseServerSettings,
        *,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory or self._new_client

    def get(self, job_id: str) -> ReleaseStatus | None:
        """Load and validate one TOS status object."""
        import tos

        try:
            response = self._client_factory().get_object(
                bucket=self._settings.bucket,
                key=self._job_key(job_id),
            )
        except tos.exceptions.TosServerError as error:
            if error.status_code == 404:
                return None
            raise
        content = b"".join(response)
        if len(content) > 256 * 1024:
            raise ValueError("Studio release status object is too large.")
        return ReleaseStatus.model_validate_json(content)

    def put(self, status: ReleaseStatus) -> None:
        """Replace the mutable status object for one release job."""
        content = (
            json.dumps(status.public_dict(), ensure_ascii=False, indent=2) + "\n"
        ).encode()
        self._client_factory().put_object(
            bucket=self._settings.bucket,
            key=self._job_key(status.job_id),
            content=content,
            content_type="application/json",
        )

    def _job_key(self, job_id: str) -> str:
        return f"{self._settings.job_prefix.strip().strip('/')}/{job_id}.json"

    def _new_client(self) -> Any:
        import tos

        credentials = resolve_credentials()
        return tos.TosClientV2(
            credentials.access_key,
            credentials.secret_key,
            security_token=credentials.session_token or None,
            endpoint=f"tos-{self._settings.region}.volces.com",
            region=self._settings.region,
        )


__all__ = [
    "JobStore",
    "TosJobStore",
    "VolcengineCredentials",
    "resolve_credentials",
]
