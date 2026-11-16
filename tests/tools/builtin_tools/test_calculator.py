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

"""Hermetic tests for the ``calculator`` built-in tool."""

import ast
import inspect
import math

import pytest

from veadk.tools.builtin_tools import calculator as calculator_module
from veadk.tools.builtin_tools.calculator import calculator


def test_signature():
    params = inspect.signature(calculator).parameters
    assert list(params) == ["expression", "precision"]


def test_defaults():
    params = inspect.signature(calculator).parameters
    assert params["expression"].default is inspect.Parameter.empty
    assert params["precision"].default == 10


# ------------------------------------------------------------ happy paths ---
@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1+2*3", 7),
        ("(1+2)*3", 9),
        ("2**10", 1024),
        ("7//2", 3),
        ("7%4", 3),
        ("-5+3", -2),
        ("+5", 5),
        ("--5", 5),
        ("20/5", 4.0),
        ("2**3**2", 512),
        ("abs(-3)", 3),
        ("round(3.14159, 2)", 3.14),
        ("min(1,2,3)", 1),
        ("max(1,2,3)", 3),
        ("floor(3.9)", 3),
        ("ceil(3.1)", 4),
        ("log10(1000)", 3.0),
        ("exp(0)", 1.0),
        ("sin(0)", 0.0),
        ("cos(0)", 1.0),
        ("tan(0)", 0.0),
    ],
)
def test_happy_paths(expression, expected):
    result = calculator(expression)
    assert "error" not in result
    assert result["result"] == expected


def test_integer_results_stay_int():
    result = calculator("2**10")
    assert result == {"expression": "2**10", "result": 1024}
    assert type(result["result"]) is int


def test_float_results_are_rounded():
    assert calculator("1/3")["result"] == 0.3333333333
    assert calculator("1/3", precision=2)["result"] == 0.33
    assert calculator("1/3", precision=0)["result"] == 0.0


def test_named_constants():
    assert calculator("pi")["result"] == round(math.pi, 10)
    assert calculator("e")["result"] == round(math.e, 10)
    assert calculator("sqrt(16)")["result"] == 4.0
    assert calculator("log(e)")["result"] == 1.0
    assert calculator("2**0.5")["result"] == round(math.sqrt(2), 10)


@pytest.mark.parametrize("precision", [0, 1, 15])
def test_precision_bounds_accepted(precision):
    assert "error" not in calculator("1/3", precision=precision)


# ------------------------------------------------------------- rejections ---
@pytest.mark.parametrize(
    "expression",
    [
        None,
        123,
        "",
        "   ",
        "x+1",
        "(1).real",
        "[1, 2][0]",
        "[x for x in [1]]",
        "lambda: 1",
        "'abc'",
        "True",
        "1j",
        "1 & 2",
        "1 if 1 else 2",
        "unknown_function(1)",
        "not 1",
        "~5",
        "1 2",
        "1 +",
    ],
)
def test_rejects_unsupported_input(expression):
    result = calculator(expression)
    assert "error" in result
    assert "result" not in result


def test_rejects_overlong_expression():
    result = calculator("1+" * 500 + "1")
    assert "error" in result
    assert "too long" in result["error"]


@pytest.mark.parametrize("precision", [-1, 16, True, "10", 1.5, None])
def test_rejects_bad_precision(precision):
    result = calculator("1+1", precision=precision)
    assert "error" in result


@pytest.mark.parametrize("expression", ["1/0", "1//0", "1%0", "0**-1"])
def test_division_by_zero(expression):
    result = calculator(expression)
    assert result == {"error": "division by zero"}


@pytest.mark.parametrize(
    "expression",
    [
        "2**101",
        "2**(-101)",
        "2**x",
        "10**100+10**100",
        "9" * 200,
        "(-8)**0.5",
        "sqrt(-1)",
        "exp(1000)",
        "min()",
        "round(1.234, ndigits=2)",
        "max(*[1, 2])",
        "min(1)(2)",
        "1e50*1e60",
    ],
)
def test_rejects_limits_and_domains(expression):
    result = calculator(expression)
    assert "error" in result


def test_exponent_limit_accepts_boundary():
    result = calculator("1**100")
    assert result["result"] == 1


def test_non_finite_helper_is_rejected():
    with pytest.raises(calculator_module._EvalError):
        calculator_module._check_number(float("inf"))
    with pytest.raises(calculator_module._EvalError):
        calculator_module._check_number(float("nan"))
    with pytest.raises(calculator_module._EvalError):
        calculator_module._check_number(True)
    with pytest.raises(calculator_module._EvalError):
        calculator_module._check_number(1j)


def test_function_zero_division_branch(monkeypatch):
    def explode(*args):
        raise ZeroDivisionError

    monkeypatch.setitem(calculator_module._FUNCTIONS, "abs", explode)
    node = ast.parse("abs(1)", mode="eval").body
    with pytest.raises(calculator_module._EvalError):
        calculator_module._apply_call(node)


def test_binary_overflow_branch():
    result = calculator("1e100**100")
    assert result == {"error": "numeric overflow"}


def test_recursion_error_is_reported(monkeypatch):
    def explode(node):
        raise RecursionError

    monkeypatch.setattr(calculator_module, "_evaluate", explode)
    result = calculator("1+1")
    assert result == {"error": "expression is too complex"}


def test_unexpected_evaluation_error_is_reported(monkeypatch):
    def explode(node):
        raise RuntimeError("boom")

    monkeypatch.setattr(calculator_module, "_evaluate", explode)
    result = calculator("1+1")
    assert result == {"error": "invalid expression"}


def test_unsupported_expression_element():
    with pytest.raises(calculator_module._EvalError):
        calculator_module._evaluate(object())
