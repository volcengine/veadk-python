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

"""Errors raised by the decision-model extension."""

from __future__ import annotations


class DecisionModelError(RuntimeError):
    """Base class for decision-model failures."""


class DecisionModelDisabledError(DecisionModelError):
    """Raised when a decision is requested but no decision model is configured."""


class DecisionModelRequestError(DecisionModelError):
    """Raised when the decision-model endpoint cannot be reached or rejects it."""


class DecisionModelUnavailableError(DecisionModelError):
    """Raised while the decision model is known to be down.

    The extension raises this instead of calling an endpoint that just failed
    repeatedly, so a hot path never pays the retry and timeout budget again.
    """


class DecisionModelResponseError(DecisionModelError):
    """Raised when the endpoint answers with an unusable payload."""
