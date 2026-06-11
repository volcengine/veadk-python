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

"""Contract tests for ``veadk.runner.Runner``.

``Runner.__init__`` and ``Runner.run`` are the primary entry points callers and
examples use. These tests pin their parameter names and defaults so a silent
signature change (e.g. a renamed/removed kwarg) is caught here.
"""

import inspect

from veadk.runner import Runner


class TestRunnerInit:
    def test_parameter_order(self):
        sig = inspect.signature(Runner.__init__)
        # Leading, explicitly-named parameters before *args/**kwargs pass-through.
        ordered = [
            name
            for name, param in sig.parameters.items()
            if param.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        ]
        assert ordered == [
            "self",
            "agent",
            "short_term_memory",
            "app_name",
            "user_id",
            "upload_inline_data_to_tos",
            "run_processor",
        ]

    def test_defaults(self):
        params = inspect.signature(Runner.__init__).parameters
        assert params["agent"].default is None
        assert params["short_term_memory"].default is None
        assert params["app_name"].default is None
        assert params["user_id"].default == "veadk_default_user"
        assert params["upload_inline_data_to_tos"].default is False
        assert params["run_processor"].default is None

    def test_accepts_var_args_and_kwargs(self):
        # *args/**kwargs are part of the contract: they pass through to ADKRunner
        # (e.g. session_service / memory_service overrides).
        kinds = {p.kind for p in inspect.signature(Runner.__init__).parameters.values()}
        assert inspect.Parameter.VAR_POSITIONAL in kinds
        assert inspect.Parameter.VAR_KEYWORD in kinds


class TestRunnerRun:
    def test_is_coroutine(self):
        assert inspect.iscoroutinefunction(Runner.run)

    def test_parameters(self):
        sig = inspect.signature(Runner.run)
        assert list(sig.parameters) == [
            "self",
            "messages",
            "user_id",
            "session_id",
            "run_config",
            "save_tracing_data",
            "upload_inline_data_to_tos",
            "run_processor",
        ]

    def test_defaults(self):
        params = inspect.signature(Runner.run).parameters
        assert params["user_id"].default == ""
        assert isinstance(params["session_id"].default, str)
        assert params["run_config"].default is None
        assert params["save_tracing_data"].default is False
        assert params["upload_inline_data_to_tos"].default is False
        assert params["run_processor"].default is None


def test_public_helper_methods_exist():
    for name in (
        "get_trace_id",
        "save_tracing_file",
        "save_eval_set",
        "save_session_to_long_term_memory",
    ):
        assert callable(getattr(Runner, name))
