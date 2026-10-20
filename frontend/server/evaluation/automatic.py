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

"""Adapt automatic evaluation output to the shared Runtime sample store"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from frontend.server.evaluation_automation.models import AutoEvaluationCase

from .models import Sample
from .repository import TosEvaluationRepository, sample_id


class TosAutomaticCases:
    def __init__(self, repository: TosEvaluationRepository) -> None:
        self.repository = repository

    async def upsert(self, case: AutoEvaluationCase) -> AutoEvaluationCase:
        identifier = sample_id(
            "auto",
            case.user_id,
            case.session_id,
            case.message_id,
            case.evaluator_version,
        )
        saved = await self.repository.save_automatic(
            Sample(
                id=identifier,
                evaluationSetId=case.kind,
                source="auto",
                kind=case.kind,
                input=case.input,
                output=case.output,
                referenceOutput=case.reference_output,
                comment=case.comment,
                userId=case.user_id,
                sessionId=case.session_id,
                messageId=case.message_id,
                invocationId=case.invocation_id,
                score=case.score,
                reason=case.reason,
                evaluatorVersion=case.evaluator_version,
            )
        )
        return case.model_copy(
            update={
                "id": identifier,
                "item_key": identifier,
                "evaluation_set_id": saved.evaluation_set_id if saved else case.kind,
            }
        )

    async def list_cases(
        self, *, agent_name: str, page_size: int = 100
    ) -> list[AutoEvaluationCase]:
        from frontend.server.evaluation_automation.models import AutoEvaluationCase

        rows = await self.repository.list_samples()
        return [
            AutoEvaluationCase(
                id=row.id,
                itemKey=row.id,
                kind=row.kind,
                input=row.input,
                output=row.output,
                referenceOutput=row.reference_output,
                comment=row.comment,
                agentName=agent_name,
                sessionId=row.session_id,
                messageId=row.message_id,
                runtimeId=self.repository.runtime_id,
                invocationId=row.invocation_id,
                userId=row.user_id,
                createdAt=row.created_at,
                evaluationSetId=row.evaluation_set_id,
                score=row.score,
                reason=row.reason,
                evaluatorVersion=row.evaluator_version,
            )
            for row in rows
            if row.source == "auto" and row.kind is not None and row.score is not None
        ][:page_size]
