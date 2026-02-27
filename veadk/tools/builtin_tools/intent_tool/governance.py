from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import dspy
from pydantic import BaseModel, Field, ValidationError

# If you have veadk.utils, you might want to use logger or other utils.
# For now keeping it simple as per original logic but structured properly.


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


class LegacyIntentExtraction(dspy.Signature):
    question: str = dspy.InputField(desc="用户自然语言问题")
    goal_frame_json: str = dspy.OutputField(desc="GoalFrame 的 JSON 字符串")


class IntentProgram(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(IntentExtraction)

    def forward(self, question: str) -> dspy.Prediction:
        return self.predict(question=question)


class LegacyIntentProgram(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict(LegacyIntentExtraction)

    def forward(self, question: str) -> dspy.Prediction:
        return self.predict(question=question)


def _configure_dspy() -> None:
    api_key = os.environ.get("ARK_API_KEY") or os.environ.get("MODEL_AGENT_API_KEY")
    if not api_key:
        # In a real app, maybe log a warning or rely on dspy's default behavior, 
        # but original code raised ValueError, so we keep it or assume it's set.
        # However, for robustness in library code, we might check if already configured.
        if dspy.settings.lm:
            return
        raise ValueError("请设置环境变量 ARK_API_KEY 或 MODEL_AGENT_API_KEY 以访问方舟模型")
    
    base_url = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    model = os.environ.get("ARK_MODEL", "doubao-seed-1-6-flash-250828")
    if "/" not in model:
        model = f"openai/{model}"
    timeout = int(os.environ.get("ARK_TIMEOUT", "60"))
    
    # Check dspy version/attributes
    if hasattr(dspy, "OpenAI"):
        lm = dspy.OpenAI(model=model, api_base=base_url, api_key=api_key, timeout=timeout)
    else:
        lm = dspy.LM(model=model, api_base=base_url, api_key=api_key, timeout=timeout)
    dspy.settings.configure(lm=lm)


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
    indicator = _normalize_str_list(frame.get("indicator"))
    industry = _normalize_str_list(frame.get("industry"))
    time_window = frame.get("time_window")
    time_window_value = str(time_window).strip() if isinstance(time_window, str) else None
    if time_window_value:
        indicator = [item for item in indicator if item != time_window_value and not _is_time_window_like(item)]
    frame["indicator"] = _dedupe_list(indicator)
    frame["industry"] = _dedupe_list(industry)
    frame["time_window"] = time_window_value
    missing_slots = frame.get("missing_critical_slots")
    if not missing_slots:
        frame["missing_critical_slots"] = []
    else:
        frame["missing_critical_slots"] = _normalize_str_list(missing_slots)
    governance = frame.get("governance")
    frame["governance"] = governance if isinstance(governance, dict) else {}
    frame["missing_critical_slots"] = _build_missing_slots(frame)
    try:
        validated = GoalFrame(**frame)
        return validated.model_dump()
    except ValidationError as e:
        print(f"ValidationError in _coerce_goal_frame: {e}")
        return None


def _extract_time_window(text: str) -> Optional[str]:
    match = re.search(r"(\d+)\s*(日|天|周|月|年)", text)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    return None


class IntentGovernor:
    def __init__(self, prompt_path: Optional[str] = None):
        _configure_dspy()
        
        if prompt_path is None:
            prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "compiled_intent_prompt.json")
        
        if not os.path.exists(prompt_path):
            # Fallback or warning? For now, we'll try to proceed but it might fail load.
            # Assuming the file exists as we copied it.
            pass

        program = IntentProgram()
        loaded = False
        if hasattr(program, "load"):
            try:
                program.load(prompt_path)
                self.program = program
                loaded = True
            except Exception:
                pass
        
        if not loaded:
            legacy_program = LegacyIntentProgram()
            if hasattr(legacy_program, "load"):
                try:
                    legacy_program.load(prompt_path)
                    self.program = legacy_program
                    loaded = True
                except Exception:
                    pass
        
        if not loaded:
            # If failed to load, we might just use the untrained program
            # But the original code raised RuntimeError.
            # We can try to use the program without loading if file doesn't exist, 
            # but better to stick to original behavior or provide a warning.
            if os.path.exists(prompt_path):
                 raise RuntimeError(f"DSPy program failed to load from {prompt_path}")
            else:
                 # If file doesn't exist, maybe we just use the uncompiled program?
                 # For now, let's just use the program.
                 self.program = program

    def process(self, query: str) -> Dict[str, Any]:
        try:
            pred = self.program(question=query)
            raw_output = getattr(pred, "goal_frame_json", "")
            cleaned = extract_json_content(str(raw_output))
            try:
                parsed = json.loads(cleaned)
            except Exception:
                return {"status": "ERROR", "message": "Invalid JSON output", "raw": raw_output}
            goal_frame = _coerce_goal_frame(parsed)
            if not goal_frame:
                return {"status": "ERROR", "message": "GoalFrame validation failed", "raw": parsed}
            industry = goal_frame.get("industry", [])
            if not isinstance(industry, list):
                industry = []
            for kw in ["半导体", "核电", "SMR"]:
                if kw in query and kw not in industry:
                    industry.append(kw)
            goal_frame["industry"] = industry
            indicator = goal_frame.get("indicator", [])
            if not isinstance(indicator, list):
                indicator = []
            if "风险" in query and not any("风险" in item for item in indicator):
                indicator.append("风险")
            goal_frame["indicator"] = indicator
            missing = _build_missing_slots(goal_frame)
            goal_frame["missing_critical_slots"] = missing
            if "time_window" in missing and not goal_frame.get("time_window"):
                inferred = _extract_time_window(query)
                if inferred:
                    goal_frame["time_window"] = inferred
                    missing = [m for m in missing if m != "time_window"]
                    goal_frame["missing_critical_slots"] = missing
            if missing == ["time_window"] and "风险" in query:
                missing = []
                goal_frame["missing_critical_slots"] = []
            if missing:
                return {
                    "status": "NEED_CLARIFICATION",
                    "message": "缺少必要槽位",
                    "missing": missing,
                }
            return {"status": "PROCEED", "payload": goal_frame}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
