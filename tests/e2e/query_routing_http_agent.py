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
"""Agents loaded by the real ADK API server for opt-in HTTP acceptance tests."""

import asyncio
import json
import os
from pathlib import Path

from google.adk.tools import AgentTool, ToolContext
from google.genai import types
from pydantic import BaseModel

from veadk import Agent
from veadk.decision import DecisionClient
from veadk.routing import factory

SIMPLE = os.getenv("VEADK_QUERY_ROUTING_SIMPLE_MODEL", "doubao-seed-2-1-lite-260915")
STRONG = os.getenv("VEADK_QUERY_ROUTING_STRONG_MODEL", "doubao-seed-2-1-pro-260915")


def audit(**record):
    # Only synthetic test data and allowlisted metadata are written here.
    with Path(os.environ["VEADK_QUERY_ROUTING_AUDIT"]).open("a") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")


class ObservedDecisionClient(DecisionClient):
    app_name = ""

    async def judge(self, **kwargs):
        audit(kind="decision_start", app=self.app_name)
        return await super().judge(**kwargs)


factory.DecisionClient = ObservedDecisionClient


async def observe_model(callback_context, llm_request):
    audit(
        kind="model",
        agent=callback_context.agent_name,
        invocation=callback_context.invocation_id,
        model=llm_request.model,
    )


def lookup_order(order_id: str, tool_context: ToolContext) -> dict:
    """Look up a synthetic order; retry once when the result is temporarily unavailable."""
    count = tool_context.state.get("lookup_count", 0) + 1
    tool_context.state["lookup_count"] = count
    if count == 1:
        return {"error": "temporarily_unavailable", "retryable": True}
    orders = {f"ORD-{41 + i:03d}": (7 + i, 19 + i) for i in range(12)}
    if order_id not in orders:
        return {"error": "unknown_order"}
    quantity, price = orders[order_id]
    return {"order_id": order_id, "quantity": quantity, "unit_price": price}


def calculate_total(quantity: int, unit_price: int) -> dict:
    """Calculate an order total from the values returned by lookup_order."""
    audit(kind="calculate_total", quantity=quantity, unit_price=unit_price)
    return {"total": quantity * unit_price}


async def wait_for_inventory(tool_context: ToolContext) -> dict:
    """Wait for an inventory lookup requested by the user."""
    tool_context.state["inventory_started"] = True
    audit(kind="inventory_started")
    cancelled = False
    try:
        await asyncio.sleep(20)
        return {"inventory": 12}
    except asyncio.CancelledError:
        cancelled = True
        raise
    finally:
        audit(kind="inventory_finished", cancelled=cancelled)


class CodeResult(BaseModel):
    code: str
    quantity: int


def build_agent(kind: str) -> Agent:
    responses = kind != "chat"
    routing = {
        "mode": "enforce",
        "simple_models": [
            {
                "name": SIMPLE,
                "api": "chat_completions" if kind in ("chat", "mixed") else "responses",
                "supports_tools": True,
                "supports_media": True,
                "supports_structured_output": True,
            }
        ],
    }
    if kind == "shadow":
        routing.pop("mode")
    elif kind == "timeout":
        routing["decision_timeout"] = 0.001

    options = {
        "name": kind,
        "model_name": STRONG,
        "model_api_base": os.environ["MODEL_AGENT_API_BASE"],
        "model_api_key": os.environ["MODEL_AGENT_API_KEY"],
        "enable_responses": responses,
        "model_extra_config": {
            "extra_body": {"thinking": {"type": "disabled"}},
        },
        "generate_content_config": types.GenerateContentConfig(
            temperature=0, max_output_tokens=1024
        ),
        "instruction": "Follow the user. Keep answers brief and remember facts across turns.",
        "before_model_callback": observe_model,
    }
    if responses:
        options["model_extra_config"]["store"] = True
        options["model_extra_config"]["extra_body"]["caching"] = {"type": "disabled"}
    if kind != "default_off":
        options["query_routing"] = False if kind == "disabled" else routing
    if kind == "tools":
        options["tools"] = [lookup_order, calculate_total]
        options["instruction"] = (
            "For order requests call lookup_order; retry once if it reports a retryable "
            "error. Then call calculate_total with the returned quantity and unit_price. "
            "Do not guess tool results. Return only the total."
        )
    if kind == "cancel":
        options["tools"] = [wait_for_inventory]
        options["instruction"] = (
            "Call wait_for_inventory only when the user asks to look up inventory. "
            "Otherwise answer directly."
        )
    if kind == "schema":
        options["output_schema"] = CodeResult
    if kind == "nested":
        leaf = Agent(
            **{
                **options,
                "name": "leaf",
                "query_routing": False,
                "instruction": "Return exactly NESTED_HTTP_OK.",
            }
        )
        child = Agent(
            **{
                **options,
                "name": "child",
                "query_routing": False,
                "tools": [AgentTool(leaf)],
                "instruction": "Pass the user's full request to leaf once and return its answer exactly.",
            }
        )
        options["tools"] = [AgentTool(child)]
        options["instruction"] = (
            "Pass the user's full request to child once and return its answer exactly."
        )
    root = Agent(**options)
    if kind not in ("disabled", "default_off"):
        root.model.classifier._judge.app_name = kind
    return root
