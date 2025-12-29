# Copyright (c) Microsoft. All rights reserved.

import math
import re
import string
import sympy
from typing import Any, cast
from veadk.agent import Agent
from veadk.runner import Runner
from veadk.memory.short_term_memory import ShortTermMemory
from agentlightning import (
    LLM,
    LitAgent,
    NamedResources,
    Trainer,
    reward,
)


def normalize_option(option: str) -> str:
    """
    >>> normalize_option("  (A)  \n")
    'A'
    """
    return re.sub(r"(\s+|\(|\))", "", option)


def is_option_result(result: str) -> bool:
    """
    >>> is_option_result("  A)  \n")
    True
    >>> is_option_result("  23/7 ")
    False
    """
    return normalize_option(result) in list(string.ascii_letters)


def float_eval(input_str: str) -> float:
    if " = around " in input_str:
        input_str = input_str.split(" = around ")[0]
    expr = sympy.parse_expr(input_str, evaluate=True)
    return float(expr.evalf())


def scalar_are_results_same(pred_result: str, true_result: str, rel_tol: float) -> bool:
    pred_result = str(pred_result) if pred_result is not None else ""  # type: ignore
    true_result = str(true_result) if true_result is not None else ""  # type: ignore

    if pred_result.strip() == true_result.strip():
        return True

    if is_option_result(true_result):
        # The task is to select correct option
        true_result = normalize_option(true_result)
        pred_result = normalize_option(pred_result)
        return pred_result == true_result

    # The task is to calculate the result as a number
    try:
        pred_float = float_eval(pred_result)
        true_float = float_eval(true_result)
        return math.isclose(pred_float, true_float, rel_tol=rel_tol)
    except Exception:
        pass

    return False


@reward
async def eval(prediction: str, ground_truth: str) -> float:
    return float(scalar_are_results_same(prediction, ground_truth, 1e-2))


class CalcAgent(LitAgent[Any]):
    async def training_rollout_async(
        self, task: Any, rollout_id: str, resources: NamedResources
    ) -> Any:  # type: ignore
        llm: LLM = cast(LLM, resources.get("main_llm"))
        calc_agent = Agent(
            name="CalcAgent",
            description="An agent that can perform calculations to answer questions.",
            instruction="You are a helpful assistant that can perform mathematical calculations to answer questions accurately.",
            model_provider="openai",
            model=llm.model,
            api_base=llm.endpoint,
            api_key="",
        )
        runner = Runner(
            agent=calc_agent,
            short_term_memory=ShortTermMemory(),
            app_name="calc_agent",
            user_id="veadk_default_user",
        )
        try:
            output_format = "Output the answer when you are ready. The answer should be surrounded by three sharps (`###`), in the form of ### ANSWER: <answer> ###."
            prompt = task["question"] + " " + output_format
            result = await runner.run(
                session_id=rollout_id,
                messages=prompt,
            )
            # evaluate
            answer = re.search(
                r"###\s*ANSWER:\s*(.+?)(\s*###|$)", result.messages[-1].content
            )  # type: ignore
            if answer:
                answer = answer.group(1)
            else:
                answer = result.messages[-1].content  # type: ignore
        except Exception as e:
            print("Failure:", str(e))
            answer = "None"
        reward = await eval(
            answer, str(task["result"])
        )  # reward is tracked with the decorator  # type: ignore
        print(
            "answer: {} ground_truth: {} reward: {}".format(
                answer, task["result"], reward
            )
        )  # type: ignore

    async def validation_rollout_async(
        self, task: Any, rollout_id: str, resources: NamedResources
    ) -> Any:  # type: ignore
        llm: LLM = cast(LLM, resources.get("main_llm"))
        resources = {
            "main_llm": LLM(
                endpoint=llm.endpoint,
                model=llm.model,
                sampling_parameters={"temperature": 0},
            )
        }
        return await self.training_rollout_async(task, rollout_id, resources)


if __name__ == "__main__":
    Trainer(n_workers=10).fit(CalcAgent(), "http://localhost:9999/")
