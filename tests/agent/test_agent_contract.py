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

"""Contract tests for the ``veadk.Agent`` public field surface.

``Agent`` is a pydantic model whose fields are its public configuration API
(used directly by callers and by the Harness server / web studio codegen). These
tests pin the veadk-specific fields and their defaults. They intentionally do
*not* assert the full field set — that includes inherited google-adk
``LlmAgent`` fields, which would make the test brittle against ADK upgrades.
"""

from veadk import Agent

# veadk-specific fields with simple, stable defaults. (model_* fields are
# default_factory-bound to settings and so are checked only for presence.)
_EXPECTED_DEFAULTS = {
    "enable_responses": False,
    "enable_responses_cache": True,
    "enable_authz": False,
    "auto_save_session": False,
    "enable_supervisor": False,
    "enable_ghostchar": False,
    "enable_dataset_gen": False,
    "enable_dynamic_load_skills": False,
    "enable_skills_checklist": False,
    "enable_tunnel": False,
    "runtime": "adk",
}

_EXPECTED_PRESENT = {
    "name",
    "description",
    "instruction",
    "model_name",
    "model_provider",
    "model_api_base",
    "model_api_key",
    "model_extra_config",
    "tools",
    "sub_agents",
    "knowledgebase",
    "short_term_memory",
    "long_term_memory",
    "tracers",
    "skills",
    "skills_mode",
}


def test_agent_is_pydantic_model():
    assert hasattr(Agent, "model_fields")


def test_expected_fields_present():
    missing = _EXPECTED_PRESENT - set(Agent.model_fields)
    assert not missing, f"Agent lost expected fields: {missing}"


def test_field_defaults():
    fields = dict(Agent.model_fields)
    for name, expected in _EXPECTED_DEFAULTS.items():
        assert name in fields, f"Agent lost field {name!r}"
        assert fields[name].default == expected, (
            f"Agent.{name} default changed: {fields[name].default!r} != {expected!r}"
        )


def test_skills_defaults_to_empty_list():
    # default_factory=list -> assert via an instantiation-free factory call.
    factory = Agent.model_fields["skills"].default_factory
    assert factory is not None
    assert factory() == []  # type: ignore[call-arg]  # pydantic's overloaded factory type
