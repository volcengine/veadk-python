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

"""Shared entry point for asking a decision model for a typed judgement.

Plugins and application code call this extension instead of talking to a
provider directly, so the provider, model, and credentials are configured once
per process.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any

from veadk.extensions.decisions.client import SystemOneClient
from veadk.extensions.decisions.config import DecisionModelConfig
from veadk.extensions.decisions.errors import (
    DecisionModelDisabledError,
    DecisionModelError,
    DecisionModelResponseError,
    DecisionModelUnavailableError,
)
from veadk.extensions.decisions.questions import (
    choice_question,
    noul_question,
    score_question,
)
from veadk.extensions.decisions.types import (
    ChoiceAnswer,
    DecisionAnswer,
    DecisionResult,
    NoulAnswer,
    ScoreAnswer,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

DISABLED_HINT = (
    "decision model is not configured; set DECISION_MODEL_ENABLED=true and "
    "DECISION_MODEL_API_KEY, or inject an extension with "
    "configure_default_decision_extension()"
)


class DecisionExtension:
    """Turn natural-language state into typed judgements.

    Constructing an extension never fails: an unconfigured extension keeps
    ``enabled`` false and raises only when a decision is actually requested,
    so callers can stay opt-in.

    Failures are contained. Every failure surfaces as a
    :class:`~veadk.extensions.decisions.errors.DecisionModelError`, so a
    caller that catches that one type always falls back to its own rules.
    After ``config.failure_threshold`` failures in a row the endpoint is
    marked down for ``config.cooldown_seconds``, during which judgements fail
    immediately instead of paying the retry and timeout budget again.
    """

    def __init__(
        self,
        config: DecisionModelConfig | None = None,
        *,
        client: SystemOneClient | None = None,
    ) -> None:
        self.config = config or DecisionModelConfig.disabled()
        self._client = client
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._open_until = 0.0
        self._probing = False

    @classmethod
    def from_env(cls) -> DecisionExtension:
        """Build an extension from ``DECISION_MODEL_*`` environment variables."""
        return cls(DecisionModelConfig.from_env())

    @property
    def enabled(self) -> bool:
        """Whether a decision model is configured and ready to be called."""
        return bool(self.config.configured or self._client is not None)

    def evaluate(self, state: Any, questions: Mapping[str, Any]) -> DecisionResult:
        """Evaluate several questions about one state synchronously.

        Raises:
            DecisionModelDisabledError: If no decision model is configured.
            DecisionModelUnavailableError: While the endpoint is marked down.
            DecisionModelError: Any other decision-model failure.
        """
        client = self._require_client()
        self._check_availability()
        try:
            result = client.evaluate(state=state, questions=questions)
        except DecisionModelError:
            self._record_failure()
            raise
        self._record_success()
        return result

    async def aevaluate(
        self, state: Any, questions: Mapping[str, Any]
    ) -> DecisionResult:
        """Asynchronous counterpart of :meth:`evaluate`."""
        client = self._require_client()
        self._check_availability()
        try:
            result = await client.aevaluate(state=state, questions=questions)
        except DecisionModelError:
            self._record_failure()
            raise
        self._record_success()
        return result

    def choose(
        self, state: Any, instructions: str, options: Sequence[str]
    ) -> ChoiceAnswer:
        """Pick one option for ``instructions`` and return the choice answer."""
        result = self.evaluate(state, {"q": choice_question(instructions, options)})
        answer = _single_answer(result)
        if not isinstance(answer, ChoiceAnswer):
            raise DecisionModelResponseError("expected a choice answer")
        return answer

    async def achoose(
        self, state: Any, instructions: str, options: Sequence[str]
    ) -> ChoiceAnswer:
        """Asynchronous counterpart of :meth:`choose`."""
        result = await self.aevaluate(
            state, {"q": choice_question(instructions, options)}
        )
        answer = _single_answer(result)
        if not isinstance(answer, ChoiceAnswer):
            raise DecisionModelResponseError("expected a choice answer")
        return answer

    def score(
        self, state: Any, instructions: str, levels: Sequence[str]
    ) -> ScoreAnswer:
        """Rate ``state`` on ordered ``levels`` and return the score answer."""
        result = self.evaluate(state, {"q": score_question(instructions, levels)})
        answer = _single_answer(result)
        if not isinstance(answer, ScoreAnswer):
            raise DecisionModelResponseError("expected a score answer")
        return answer

    async def ascore(
        self, state: Any, instructions: str, levels: Sequence[str]
    ) -> ScoreAnswer:
        """Asynchronous counterpart of :meth:`score`."""
        result = await self.aevaluate(
            state, {"q": score_question(instructions, levels)}
        )
        answer = _single_answer(result)
        if not isinstance(answer, ScoreAnswer):
            raise DecisionModelResponseError("expected a score answer")
        return answer

    def noul(self, state: Any, instructions: str) -> NoulAnswer:
        """Ask a yes/no question and return the probability of "yes"."""
        result = self.evaluate(state, {"q": noul_question(instructions)})
        answer = _single_answer(result)
        if not isinstance(answer, NoulAnswer):
            raise DecisionModelResponseError("expected a noul answer")
        return answer

    async def anoul(self, state: Any, instructions: str) -> NoulAnswer:
        """Asynchronous counterpart of :meth:`noul`."""
        result = await self.aevaluate(state, {"q": noul_question(instructions)})
        answer = _single_answer(result)
        if not isinstance(answer, NoulAnswer):
            raise DecisionModelResponseError("expected a noul answer")
        return answer

    def _require_client(self) -> SystemOneClient:
        if self._client is not None:
            return self._client
        if not self.config.configured:
            raise DecisionModelDisabledError(DISABLED_HINT)
        self._client = SystemOneClient(self.config)
        return self._client

    # -- availability ------------------------------------------------------

    def _check_availability(self) -> None:
        """Fail fast while the endpoint is known to be down.

        Raises:
            DecisionModelUnavailableError: While the circuit is open. Once the
                cooldown has passed, one caller becomes the probe that decides
                whether judgements may resume.
        """
        if self.config.failure_threshold <= 0:
            return
        with self._lock:
            if not self._open_until:
                return
            remaining = self._open_until - time.monotonic()
            if remaining > 0 or self._probing:
                raise DecisionModelUnavailableError(
                    f"decision model {self.config.name} is marked down; "
                    f"skipping judgements for {max(remaining, 0.0):.0f}s"
                )
            self._probing = True
            logger.info(
                "decision model cooldown elapsed; probing %s",
                self.config.endpoint,
            )

    def _record_failure(self) -> None:
        """Count a failed judgement and mark the endpoint down when it persists."""
        if self.config.failure_threshold <= 0:
            return
        with self._lock:
            self._probing = False
            self._consecutive_failures += 1
            if self._consecutive_failures < self.config.failure_threshold:
                return
            self._open_until = time.monotonic() + self.config.cooldown_seconds
            logger.warning(
                "decision model %s failed %d time(s) in a row; skipping "
                "judgements for %.0fs",
                self.config.name,
                self._consecutive_failures,
                self.config.cooldown_seconds,
            )

    def _record_success(self) -> None:
        """Mark the endpoint as healthy again."""
        if self.config.failure_threshold <= 0:
            return
        with self._lock:
            self._probing = False
            self._consecutive_failures = 0
            if self._open_until:
                self._open_until = 0.0
                logger.info(
                    "decision model %s answered again; judgements resumed",
                    self.config.name,
                )


def _single_answer(result: DecisionResult) -> DecisionAnswer:
    if not result.answers:
        raise DecisionModelResponseError("decision model returned no answers")
    return next(iter(result.answers.values()))


_default_extension: DecisionExtension | None = None


def get_default_decision_extension() -> DecisionExtension:
    """Return the process-wide extension, building it from the environment once."""
    global _default_extension
    if _default_extension is None:
        _default_extension = DecisionExtension.from_env()
    return _default_extension


def configure_default_decision_extension(extension: DecisionExtension | None) -> None:
    """Replace the process-wide extension; pass ``None`` to reset it."""
    global _default_extension
    _default_extension = extension
