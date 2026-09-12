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

"""Shared HTTP timeout defaults for outbound requests.

Every outbound call in VeADK should carry an explicit timeout. `requests` has
no default timeout at all, so a call without one blocks forever if the peer
accepts the connection and then goes silent -- which, for the synchronous tools
that ADK invokes inline on the event loop, stalls the whole process.

Note on semantics: for `requests`, the read half of the tuple bounds the time
between two consecutive socket reads, not the total duration of the call. It
caps silence, not transfer size. Anything that needs a hard wall-clock ceiling
(a polling loop, a paginated sweep) still needs its own deadline on top.

All values are overridable per deployment via environment variables.
"""

import os

__all__ = [
    "DEFAULT_CONNECT_TIMEOUT",
    "DEFAULT_READ_TIMEOUT",
    "DEFAULT_HTTP_TIMEOUT",
    "DEFAULT_STREAM_BUDGET_SECONDS",
]


def _env_float(name: str, default: float, minimum: float = 1.0) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return max(minimum, float(raw))
    except (TypeError, ValueError):
        return default


# Time allowed to establish a TCP/TLS connection. A peer that is unreachable
# should fail fast rather than occupy a worker.
DEFAULT_CONNECT_TIMEOUT: float = _env_float("VEADK_HTTP_CONNECT_TIMEOUT", 10.0)

# Time allowed between two consecutive reads for ordinary control-plane calls.
DEFAULT_READ_TIMEOUT: float = _env_float("VEADK_HTTP_READ_TIMEOUT", 60.0)

# (connect, read) tuple, ready to pass straight to `requests`. One value for
# every outbound call: a chunk gap anywhere near a minute already means the peer
# is unhealthy, whether the payload is a JSON reply or a hundred-megabyte object.
DEFAULT_HTTP_TIMEOUT: tuple[float, float] = (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
)

# Wall-clock ceiling for consuming a streamed response end to end. This is a
# different quantity from the read timeout above, which only bounds the gap
# between two reads: a server emitting an endless trickle of valid frames resets
# that gap forever and is only caught by a total budget.
DEFAULT_STREAM_BUDGET_SECONDS: float = _env_float("VEADK_HTTP_STREAM_BUDGET", 300.0)
