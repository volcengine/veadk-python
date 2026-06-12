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

"""Contract tests for the ``veadk agentkit harness`` CLI commands.

These pin the click command tree, option names, required flags, defaults, and
the ``HARNESS_URL`` / ``HARNESS_KEY`` env-var bindings, so a rename or a changed
default that would break documented usage is caught here.
"""

import click

from veadk.cli.cli_agentkit import harness


def _options(command: click.Command) -> dict[str | None, click.Parameter]:
    """Map of parameter name -> click Parameter for ``command``."""
    return {param.name: param for param in command.params}


def test_harness_is_a_group_with_invoke():
    assert isinstance(harness, click.Group)
    assert set(harness.commands) == {"invoke"}


class TestHarnessInvoke:
    def setup_method(self):
        self.cmd = harness.commands["invoke"]
        self.opts = _options(self.cmd)

    def test_parameters(self):
        # One positional MESSAGE argument plus the named options.
        assert set(self.opts) == {
            "message",
            "harness_name",
            "model_name",
            "system_prompt",
            "tools",
            "skills",
            "runtime",
            "user_id",
            "session_id",
            "url",
            "key",
        }

    def test_message_is_positional_argument(self):
        assert isinstance(self.opts["message"], click.Argument)
        assert self.opts["message"].required is True

    def test_required_flags(self):
        assert self.opts["harness_name"].required is True
        assert self.opts["url"].required is True

    def test_session_defaults(self):
        assert self.opts["user_id"].default == "cli-user"
        assert self.opts["session_id"].default == "cli-session"

    def test_env_var_bindings(self):
        assert self.opts["url"].envvar == "HARNESS_URL"
        assert self.opts["key"].envvar == "HARNESS_KEY"
