from __future__ import annotations

import argparse
import csv
import json
import os
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

import dspy


class GoalFrame(BaseModel):
    primary_intent: str = Field(..., description="用户意图的主类目")
    industry: List[str] = Field(default_factory=list, description="行业或主题范围")
    time_window: Optional[str] = Field(default=None, description="时间窗口或周期")
    indicator: List[str] = Field(default_factory=list, description="指标或因子名集合")
    governance: Dict[str, Any] = Field(default_factory=dict, description="合规或治理字段")
    missing_critical_slots: List[str] = Field(default_factory=list, description="缺失的关键槽位")
    extra: Dict[str, Any] = Field(default_factory=dict, description="扩展字段")


class IntentExtraction(dspy.Signature):
    question: str = dspy.InputField(desc="用户自然语言问题")
    reasoning: str = dspy.OutputField(desc="先分析意图与槽位，再输出 JSON")
    goal_frame_json: str = dspy.OutputField(desc="GoalFrame 的 JSON 字符串")


class LabelerSignature(dspy.Signature):
    """
    分析用户 Query 和参考的 Condition。区分语义类别：
    1. Industry (行业/范围)：板块、概念、题材。
    2. Indicator (指标/属性)：量化数据、技术形态、财务指标。
    3. 提取时间窗口放入 time_window。

    【隐式值处理原则】：
    - 如果用户未提及行业，industry 为空即可，不要标记 missing_critical_slots。
    - 如果用户未提及时间，time_window 为空即可，不要标记 missing_critical_slots。
    - 仅当 query 极其模糊（如“查一下”），无法推断任何意图时，才标记 missing。

    CRITICAL: Do NOT duplicate words. If "半导体" is in industry, do NOT put it in indicator.
    """
    question: str = dspy.InputField(desc="用户自然语言问题")
    factor_name: str = dspy.InputField(desc="标准因子名，来自 conditions 解析")
    reasoning: str = dspy.OutputField(desc="先做概念辨析，再输出 JSON")
    goal_frame_json: str = dspy.OutputField(desc="GoalFrame 的 JSON 字符串")


class DataLabeler(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(LabelerSignature)

    def forward(self, question: str, factor_name: str) -> dspy.Prediction:
        return self.predict(question=question, factor_name=factor_name)


class IntentProgram(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(IntentExtraction)

    def forward(self, question: str) -> dspy.Prediction:
        return self.predict(question=question)


def _find_repo_root() -> str:
    start = os.path.abspath(os.getcwd())
    candidates = [start, os.path.abspath(os.path.dirname(__file__))]
    for base in candidates:
        cur = os.path.abspath(base)
        for _ in range(8):
            if os.path.exists(os.path.join(cur, "select_stocks_qa.csv")):
                return cur
            nxt = os.path.dirname(cur)
            if nxt == cur:
                break
            cur = nxt
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _configure_dspy() -> None:
    api_key = os.environ.get("ARK_API_KEY") or os.environ.get("MODEL_AGENT_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 ARK_API_KEY 或 MODEL_AGENT_API_KEY 以访问方舟模型")
    base_url = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    model = os.environ.get("ARK_MODEL", "doubao-seed-1-6-flash-250828")
    if "/" not in model:
        model = f"openai/{model}"
    timeout = int(os.environ.get("ARK_TIMEOUT", "60"))
    if hasattr(dspy, "OpenAI"):
        lm = dspy.OpenAI(model=model, api_base=base_url, api_key=api_key, timeout=timeout)
    else:
        lm = dspy.LM(model=model, api_base=base_url, api_key=api_key, timeout=timeout)
    dspy.settings.configure(lm=lm)


def _safe_json_loads(text: str) -> Optional[Any]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None


def extract_json_content(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "")
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1].strip()
    return cleaned.strip()


def _normalize_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def _build_missing_slots(frame: Dict[str, Any]) -> List[str]:
    missing = []
    has_industry = bool(_normalize_str_list(frame.get("industry")))
    has_indicator = bool(_normalize_str_list(frame.get("indicator")))
    if not has_industry and not has_indicator:
        missing.append("intent_subject")
    return missing


def _is_time_window_like(value: str) -> bool:
    return bool(re.match(r"^(前|近)?[0-9一二三四五六七八九十]+(日|天|周|月|年)$", value))


def _dedupe_list(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _coerce_goal_frame(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    frame = dict(raw)
    primary_intent = str(frame.get("primary_intent") or "").strip()
    frame["primary_intent"] = primary_intent if primary_intent else "stock_factor_query"
    frame["indicator"] = _normalize_str_list(frame.get("indicator"))
    industry = _normalize_str_list(frame.get("industry"))
    expanded_industry = []
    for item in industry:
        if "," in item:
            expanded_industry.extend([part.strip() for part in item.split(",") if part.strip()])
        else:
            expanded_industry.append(item)
    frame["industry"] = expanded_industry
    time_window = frame.get("time_window")
    if isinstance(time_window, list) and time_window:
        frame["time_window"] = str(time_window[0]).strip()
    elif isinstance(time_window, str):
        tw = time_window.strip()
        frame["time_window"] = tw if tw else None
    else:
        frame["time_window"] = None
    frame["missing_critical_slots"] = _build_missing_slots(frame)
    governance = frame.get("governance")
    frame["governance"] = governance if isinstance(governance, dict) else {}
    try:
        validated = GoalFrame(**frame)
        return validated.model_dump()
    except ValidationError as e:
        print(f"ValidationError in _coerce_goal_frame: {e}")
        print(f"  > Raw Frame: {frame}")
        return None


def load_csv_rows(csv_path: str, max_rows: Optional[int] = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            question = str(row.get("question") or "").strip()
            conditions_raw = row.get("conditions")
            conditions = []
            if conditions_raw:
                try:
                    conditions = json.loads(conditions_raw)
                except Exception:
                    conditions = []
            factor_names = []
            for item in conditions or []:
                if not isinstance(item, dict):
                    continue
                factor = str(item.get("factor") or "").strip()
                if factor:
                    factor_names.append(factor)
            if not question:
                continue
            rows.append(
                {
                    "question": question,
                    "conditions": conditions,
                    "factor_names": factor_names,
                }
            )
            if max_rows and len(rows) >= max_rows:
                break
    return rows


def augment_dataset(
    rows: List[Dict[str, Any]],
    labeler: DataLabeler,
) -> List[Dict[str, Any]]:
    augmented: List[Dict[str, Any]] = []
    total = len(rows)
    for idx, row in enumerate(rows, start=1):
        question = row["question"]
        factor_names = row.get("factor_names") or []
        factor_hint = "、".join(_normalize_str_list(factor_names)) if factor_names else ""
        if total:
            print(f"Labeling {idx}/{total}")
        prediction = labeler(question=question, factor_name=factor_hint)
        reasoning = str(getattr(prediction, "reasoning", "") or "")
        raw_output = getattr(prediction, "goal_frame_json", "")
        cleaned_json = extract_json_content(str(raw_output))
        try:
            goal_frame_raw = json.loads(cleaned_json)
        except Exception:
            print(f"Warning: invalid goal_frame_json at row {idx}, skipped.")
            print(f"FAILED RAW JSON: {raw_output}")
            continue
        goal_frame = _coerce_goal_frame(goal_frame_raw)
        if not goal_frame:
            print(f"Warning: invalid goal_frame_json at row {idx}, skipped")
            print(f"FAILED PARSED JSON: {goal_frame_raw}")
            continue
        goal_frame_json = json.dumps(goal_frame, ensure_ascii=False)
        augmented.append(
            {
                "question": question,
                "factor_names": factor_names,
                "reasoning": reasoning,
                "goal_frame": goal_frame,
                "goal_frame_json": goal_frame_json,
            }
        )
    return augmented


def save_json(data: Any, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_augmented_dataset(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_logic(example: dspy.Example, pred: dspy.Prediction, trace: Any = None) -> bool:
    expected_raw = _safe_json_loads(getattr(example, "goal_frame_json", ""))
    predicted_raw = _safe_json_loads(getattr(pred, "goal_frame_json", ""))
    reasoning = getattr(pred, "reasoning", "")
    if not reasoning or len(str(reasoning).strip()) <= 10:
        return False
    if not isinstance(expected_raw, dict) or not isinstance(predicted_raw, dict):
        return False
    expected_indicator = _normalize_str_list(expected_raw.get("indicator"))
    predicted_indicator = _normalize_str_list(predicted_raw.get("indicator"))
    if expected_indicator and not set(expected_indicator).intersection(predicted_indicator):
        return False
    expected_industry = _normalize_str_list(expected_raw.get("industry"))
    predicted_industry = _normalize_str_list(predicted_raw.get("industry"))
    if expected_industry and not set(expected_industry).intersection(predicted_industry):
        return False
    return True


def compile_intent_prompt(
    augmented_path: str,
    compiled_path: str,
    max_bootstrapped_demos: int = 6,
    max_labeled_demos: int = 12,
) -> None:
    data = load_augmented_dataset(augmented_path)
    if not data:
        raise ValueError("增强数据为空，无法编译")
    trainset: List[dspy.Example] = []
    for item in data:
        reasoning = str(item.get("reasoning") or "")
        if len(reasoning.strip()) <= 10:
            continue
        example = dspy.Example(
            question=item.get("question", ""),
            goal_frame_json=item.get("goal_frame_json", ""),
            reasoning=reasoning,
        ).with_inputs("question")
        trainset.append(example)
    if not trainset:
        raise ValueError("清洗后训练数据为空，请检查增强数据的 reasoning 字段")
    teleprompter = dspy.teleprompt.BootstrapFewShot(
        metric=validate_logic,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_labeled_demos,
    )
    compiled_program = teleprompter.compile(IntentProgram(), trainset=trainset)
    if hasattr(compiled_program, "save"):
        compiled_program.save(compiled_path)
        return
    if hasattr(dspy, "save"):
        dspy.save(compiled_program, compiled_path)
        return
    payload = None
    if hasattr(compiled_program, "dump"):
        payload = compiled_program.dump()
    elif hasattr(compiled_program, "to_dict"):
        payload = compiled_program.to_dict()
    if payload is None:
        raise RuntimeError("无法序列化编译结果，请检查 DSPy 版本")
    save_json(payload, compiled_path)


def run_pipeline(
    repo_root: str,
    csv_path: str,
    augmented_path: str,
    compiled_path: str,
    max_rows: Optional[int] = None,
) -> None:
    _configure_dspy()
    rows = load_csv_rows(csv_path, max_rows=max_rows)
    labeler = DataLabeler()
    augmented = augment_dataset(rows, labeler)
    save_json(augmented, augmented_path)
    compile_intent_prompt(augmented_path, compiled_path)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DSPy 意图结构化引擎构建脚本")
    parser.add_argument(
        "--repo-root",
        default=_find_repo_root(),
        help="仓库根目录",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="select_stocks_qa.csv 路径",
    )
    parser.add_argument(
        "--augmented",
        default=None,
        help="增强数据输出路径",
    )
    parser.add_argument(
        "--compiled",
        default=None,
        help="编译后的 Prompt 输出路径",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="限制处理的行数，便于快速测试",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    repo_root = os.path.abspath(args.repo_root)
    csv_path = args.csv or os.path.join(repo_root, "select_stocks_qa.csv")
    augmented_path = args.augmented or os.path.join(repo_root, "data", "augmented_dataset.json")
    compiled_path = args.compiled or os.path.join(repo_root, "dspy_eval", "compiled_intent_prompt.json")
    run_pipeline(repo_root, csv_path, augmented_path, compiled_path, max_rows=args.max_rows)


if __name__ == "__main__":
    main()
