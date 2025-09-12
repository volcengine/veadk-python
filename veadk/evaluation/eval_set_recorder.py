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

import time
from pathlib import Path

from google.adk.cli.utils import evals
from google.adk.evaluation.eval_case import EvalCase, SessionInput
from google.adk.evaluation.local_eval_sets_manager import LocalEvalSetsManager
from google.adk.sessions import BaseSessionService

from veadk.utils.logger import get_logger
from veadk.utils.misc import formatted_timestamp, get_temp_dir

logger = get_logger(__name__)


class EvalSetRecorder(LocalEvalSetsManager):
    def __init__(
        self, session_service: BaseSessionService, eval_set_id: str = "default"
    ):
        super().__init__(agents_dir=get_temp_dir())
        self.eval_set_id = eval_set_id if eval_set_id != "" else "default"
        self.session_service: BaseSessionService = session_service

    # adapted from google.adk.cli.fast_api
    async def add_session_to_eval_set(
        self,
        app_name: str,
        eval_set_id: str,
        session_id: str,
        user_id: str,
    ):
        eval_id = f"veadk_eval_{formatted_timestamp()}"

        # Get the session
        session = await self.session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        assert session, "Session not found."

        # Convert the session data to eval invocations
        invocations = evals.convert_session_to_eval_invocations(session)

        # Populate the session with initial session state.
        # initial_session_state = create_empty_state(agent_loader.load_agent(app_name))

        new_eval_case = EvalCase(
            eval_id=eval_id,
            conversation=invocations,
            session_input=SessionInput(app_name=app_name, user_id=user_id),
            creation_timestamp=time.time(),
        )

        try:
            self.add_eval_case(app_name, eval_set_id, new_eval_case)
        except ValueError as ve:
            raise ValueError(f"Add eval case to eval set error: {ve}")

    async def dump(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> str:
        dump_path = self._get_eval_set_file_path(app_name, self.eval_set_id)
        Path(dump_path).parent.mkdir(parents=True, exist_ok=True)

        self.create_eval_set(app_name=app_name, eval_set_id=self.eval_set_id)

        await self.add_session_to_eval_set(
            app_name=app_name,
            eval_set_id=self.eval_set_id,
            session_id=session_id,
            user_id=user_id,
        )

        logger.info(f"Dump eval set to {dump_path}")

        return dump_path
