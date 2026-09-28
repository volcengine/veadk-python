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

"""Reading the ``0..1`` threshold a decision point compares an answer against.

Every judgement asks a ``noul`` question, so every answer is the probability of
"yes" in ``[0, 1]``. The points differ in what that probability costs them, so
each keeps its own threshold; parsing lives here so the points cannot drift
apart in how they treat an unusable setting.
"""

from __future__ import annotations

import math
from typing import Any

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

#: 判定阈值默认值：对「是」的概率取中性的分界点。
DEFAULT_JUDGEMENT_THRESHOLD = 0.5


def probability_threshold(
    raw: Any,
    default: float = DEFAULT_JUDGEMENT_THRESHOLD,
    *,
    name: str = "threshold",
) -> float:
    """Return a usable judgement threshold parsed from ``raw``.

    Out-of-range values are clamped instead of rejected: clamping keeps the
    intent (``1.5`` still means "never act", ``-1`` still means "always act"),
    while falling back to the default would silently flip the behaviour. A
    value with no intent to keep — unparseable text or ``NaN`` — falls back to
    ``default``.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("%s=%r is not a number; using %s", name, raw, default)
        return default
    if math.isnan(value):
        logger.warning("%s is NaN; using %s", name, default)
        return default
    if not 0.0 <= value <= 1.0:
        clamped = min(1.0, max(0.0, value))
        logger.warning("%s=%s is outside [0, 1]; using %s", name, value, clamped)
        return clamped
    return value


__all__ = ["DEFAULT_JUDGEMENT_THRESHOLD", "probability_threshold"]
