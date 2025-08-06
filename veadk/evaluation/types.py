from dataclasses import dataclass


@dataclass
class EvalResultCaseData:
    id: str
    input: str
    actual_output: str
    expected_output: str
    score: str
    reason: str
    status: str  # `PASSED` or `FAILURE`
    latency: str


@dataclass
class EvalResultMetadata:
    tested_model: str
    judge_model: str
