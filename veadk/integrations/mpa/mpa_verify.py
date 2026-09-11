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

"""Post-deploy verification for a provisioned mpa-agent instance (FR-6).

Probes the runtime's ``/health`` and ``/readiness`` endpoints and the A2A
agent-card that Studio needs to connect. Reports which probes failed without
including any secret material.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

# Path suffix -> human label. Order defines probe order and report order.
_PROBES: tuple[tuple[str, str], ...] = (
    ("/health", "health"),
    ("/readiness", "readiness"),
    ("/.well-known/agent-card.json", "agent-card"),
)

_DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass
class VerificationResult:
    """Outcome of probing a provisioned instance."""

    endpoint: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    statuses: dict[str, int | str] = field(default_factory=dict)

    def summary(self) -> str:
        """Return a secret-free, human-readable summary of the probe results."""
        parts = [f"endpoint={self.endpoint}", f"passed={self.passed}"]
        for _, label in _PROBES:
            if label in self.statuses:
                parts.append(f"{label}={self.statuses[label]}")
        if self.failures:
            parts.append("failures=" + ",".join(self.failures))
        return " ".join(parts)


def verify_instance(
    public_endpoint: str,
    *,
    client: httpx.Client | None = None,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> VerificationResult:
    """Probe ``/health``, ``/readiness``, and the A2A agent-card.

    Args:
        public_endpoint: The released public base URL.
        client: Optional injected ``httpx.Client`` (used by tests). When omitted
            a short-timeout client is created and closed here.
        timeout: Per-request timeout in seconds when creating the client.

    Returns:
        A :class:`VerificationResult`. ``passed`` is True only when every probe
        returns a 2xx status.
    """
    base = public_endpoint.rstrip("/")
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    failures: list[str] = []
    statuses: dict[str, int | str] = {}
    try:
        for suffix, label in _PROBES:
            url = f"{base}{suffix}"
            try:
                response = http.get(url)
                statuses[label] = response.status_code
                if not 200 <= response.status_code < 300:
                    failures.append(f"{label}(status={response.status_code})")
            except httpx.HTTPError as exc:
                statuses[label] = "error"
                # Only the exception type is recorded to avoid leaking URLs/creds.
                failures.append(f"{label}({type(exc).__name__})")
    finally:
        if owns_client:
            http.close()

    return VerificationResult(
        endpoint=base,
        passed=not failures,
        failures=failures,
        statuses=statuses,
    )
