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

"""Package acquisition and instruction delivery, never business execution."""

from contextlib import contextmanager, suppress

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from veadk.tracing.telemetry import portal_metrics
from veadk.utils.adk_compat import get_event_function_responses


def skill_identity(skill) -> dict[str, str] | None:
    space = skill.skill_space_id or ""
    if not skill.id or not space.startswith(("sp-", "ss-")):
        return None
    version = skill.version_id or ""
    if not version and space.startswith("ss-"):
        parts = skill.path.split("/")
        if len(parts) >= 3 and parts[0] == "skills":
            version = parts[2]
    return {
        "skill_source": "skillhub_skill_space"
        if space.startswith("sp-")
        else "agentkit_skill_space",
        "skill_id": skill.id,
        "skill_name": skill.name,
        "skill_version": version,
        "skill_space_id": space,
    }


def _span_attributes(identity, consumer):
    return {
        **{
            key.replace("skill_", "skill.", 1): value for key, value in identity.items()
        },
        "skill.consumer": consumer,
    }


@contextmanager
def download(identity, *, consumer="runtime"):
    observation = {"cache_hit": False}
    if identity is None:
        yield observation
        return
    span = trace.INVALID_SPAN
    with suppress(Exception):
        span = trace.get_tracer("veadk.skills").start_span(
            f"download_skill {identity['skill_name']}",
            attributes=_span_attributes(identity, consumer),
        )
    outcome = "error"
    try:
        yield observation
        outcome = "success"
    except BaseException as error:
        with suppress(Exception):
            span.set_attributes(
                {
                    "error.type": type(error).__name__,
                    "error.description": "Skill package acquisition failed",
                }
            )
            span.set_status(
                Status(StatusCode.ERROR, "Skill package acquisition failed")
            )
        raise
    finally:
        portal_metrics.portal_metric_recorder.record_skill_download(identity)
        with suppress(Exception):
            span.set_attributes(
                {
                    "skill.download.outcome": outcome,
                    "skill.download.cache_hit": observation["cache_hit"],
                }
            )
            span.end()


def record_adk_load(tool, event):
    """Observe the final ADK response, including invocation-cache hits."""
    from google.adk.tools.skill_toolset import LoadSkillTool

    from veadk.skills.registry import VeSkillRegistry

    with suppress(Exception):
        if not isinstance(tool, LoadSkillTool) or not isinstance(
            tool._toolset._registry, VeSkillRegistry
        ):
            return
        for response in get_event_function_responses(event):
            if response.name != tool.name:
                continue
            result = response.response
            if result.get("error") or not isinstance(result.get("instructions"), str):
                continue
            identity = (
                result.get("frontmatter", {})
                .get("metadata", {})
                .get("veadk_skill_identity")
            )
            if not isinstance(identity, dict) or set(identity) != {
                "skill_source",
                "skill_id",
                "skill_name",
                "skill_version",
                "skill_space_id",
            }:
                continue
            if not identity["skill_id"] or not all(
                isinstance(value, str) for value in identity.values()
            ):
                continue
            portal_metrics.portal_metric_recorder.record_skill_load(identity)
            span = trace.get_current_span()
            span.update_name(f"load_skill {identity['skill_name']}")
            span.set_attributes(_span_attributes(identity, "runtime"))
