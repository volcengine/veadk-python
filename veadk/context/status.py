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

"""Content-free capability reporting; configured does not mean compressed."""

from .budget import ContextBudgetError, resolve_payload_budget


def agent_context_metadata(agent) -> dict:
    """Expose SDK capacity status only, never arbitrary configuration or text."""
    from veadk.agent import Agent

    if not isinstance(agent, Agent):
        return {}
    return {"contextCompression": agent.context_compression_status}


def describe_context(model, policy, *, runtime: str = "adk") -> dict:
    # External runtimes own the model loop and bypass the SDK's input guard.
    # Report effective capability without changing the requested policy.
    if runtime != "adk":
        return {
            "state": "unsupported_runtime",
            "mode": "off",
            "reason": "runtime_owns_model_loop",
        }
    if policy is None:
        return {"state": "unsupported_model_adapter", "mode": "off"}
    try:
        budget = resolve_payload_budget(
            {**(getattr(model, "_additional_args", {}) or {}), "model": model.model},
            policy,
        )
    except ContextBudgetError as error:
        return {
            "state": "invalid_configuration",
            "mode": policy.mode,
            "reason": error.code,
        }
    if budget is None:
        return {
            "state": "needs_configuration",
            "mode": policy.mode,
            "reason": "model_capacity_required",
        }
    return {
        "state": "configured" if policy.mode == "auto" else "compression_disabled",
        "mode": policy.mode,
        "input_budget": budget.available,
        "context_window": budget.window,
        "output_reserve": budget.output,
        "estimator": budget.estimator,
        "trigger_ratio": policy.trigger_ratio,
        "target_ratio": policy.target_ratio,
        "summary_trigger_ratio": policy.summary_trigger_ratio,
    }
