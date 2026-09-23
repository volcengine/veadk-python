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

"""Optional decision-model capability for VeADK agents.

A decision model turns evidence and criteria into typed judgements (a choice,
a score, or the probability that a condition holds) that code can act on
directly. It is separate from the agent's conversational model and entirely
opt-in: without configuration, callers see ``enabled == False`` and nothing
else changes.

Usage:

```python
from veadk.extensions.decisions import DecisionExtension

extension = DecisionExtension.from_env()
if extension.enabled:
    answer = await extension.achoose(
        "My card was charged twice.",
        "Which team should handle this?",
        ["billing", "shipping", "returns"],
    )
    print(answer.choice, answer.confidence)
```
"""

from veadk.extensions.decisions.client import SystemOneClient
from veadk.extensions.decisions.config import (
    DEFAULT_API_BASE,
    DEFAULT_MODEL_NAME,
    DecisionModelConfig,
)
from veadk.extensions.decisions.errors import (
    DecisionModelDisabledError,
    DecisionModelError,
    DecisionModelRequestError,
    DecisionModelResponseError,
)
from veadk.extensions.decisions.questions import (
    choice_question,
    noul_question,
    score_question,
)
from veadk.extensions.decisions.extension import (
    DecisionExtension,
    configure_default_decision_extension,
    get_default_decision_extension,
)
from veadk.extensions.decisions.tools import decision_evaluate
from veadk.extensions.decisions.types import (
    ChoiceAnswer,
    DecisionAnswer,
    DecisionResult,
    DecisionUsage,
    NoulAnswer,
    ScoreAnswer,
)

__all__ = [
    "ChoiceAnswer",
    "DEFAULT_API_BASE",
    "DEFAULT_MODEL_NAME",
    "DecisionAnswer",
    "DecisionModelConfig",
    "DecisionModelDisabledError",
    "DecisionModelError",
    "DecisionModelRequestError",
    "DecisionModelResponseError",
    "DecisionResult",
    "DecisionExtension",
    "DecisionUsage",
    "NoulAnswer",
    "ScoreAnswer",
    "SystemOneClient",
    "choice_question",
    "configure_default_decision_extension",
    "decision_evaluate",
    "get_default_decision_extension",
    "noul_question",
    "score_question",
]
