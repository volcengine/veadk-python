from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

# Adjust import based on where VikingDBKnowledgeBackend is located
# User said: Assume `vikingdb_knowledge_backend.py` located in `veadk/knowledgebase/backends/`
from veadk.knowledgebase.backends.vikingdb_knowledge_backend import VikingDBKnowledgeBackend

BASE_RERANK_INSTRUCTION = (
    "Whether the Document answers the Query or matches the content retrieval intent"
)

TIME_WINDOW_PATTERN = re.compile(r"(前|近)?(\d+|[一二三四五六七八九十]+)(日|天|周|月|年)")


def _extract_content(entry: Any) -> str:
    content = getattr(entry, "content", None)
    if content is None and isinstance(entry, dict):
        content = entry.get("content")
    return content or ""


def _extract_factor(content: str) -> str:
    if not content:
        return ""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for line in lines:
        if line.lower().startswith("factor"):
            parts = line.split(":", 1)
            return parts[1].strip() if len(parts) > 1 else line
        if line.startswith("因子"):
            parts = line.split(":", 1)
            return parts[1].strip() if len(parts) > 1 else line
    for line in lines:
        if line.startswith(
            (
                "id:",
                "classid:",
                "subclassid:",
                "back_test_type:",
                "描述:",
                "分类名称:",
                "子分类名称:",
                "is_gold_standard:",
                "ai_desc:",
                "synonyms:",
                "syn_questions:",
            )
        ):
            continue
        return line
    return ""


def _extract_time_windows(text: str) -> List[str]:
    if not text:
        return []
    return [match.group(0) for match in TIME_WINDOW_PATTERN.finditer(text)]


def _chinese_numeral_to_int(value: str) -> int | None:
    mapping = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if value in mapping:
        return mapping[value]
    if value.endswith("十") and value[:-1] in mapping:
        return mapping[value[:-1]] * 10
    if value.startswith("十") and value[1:] in mapping:
        return 10 + mapping[value[1:]]
    if "十" in value and len(value) == 3:
        left, right = value.split("十", 1)
        if left in mapping and right in mapping:
            return mapping[left] * 10 + mapping[right]
    return None


def _normalize_time_window(value: str | None) -> str | None:
    if not value:
        return None
    match = TIME_WINDOW_PATTERN.search(value)
    if not match:
        return value
    amount = match.group(2)
    unit = match.group(3)
    if amount.isdigit():
        normalized_amount = amount
    else:
        numeral = _chinese_numeral_to_int(amount)
        normalized_amount = str(numeral) if numeral is not None else amount
    return f"{normalized_amount}{unit}"


def _build_rerank_instruction(time_window: str | None) -> str:
    if not time_window:
        return BASE_RERANK_INSTRUCTION
    normalized = _normalize_time_window(time_window) or time_window
    return f"{BASE_RERANK_INSTRUCTION}; time_window must match: {normalized}"


class StockRetriever:
    def __init__(self, collection_name: str, backend: Optional[Any] = None):
        if backend:
            self.backend = backend
        else:
            self.backend = VikingDBKnowledgeBackend(index=collection_name)

    def _search(self, query: str, limit: int, time_window: str | None) -> List[dict]:
        # Accessing internal method _do_request is not ideal but following original logic.
        # Ideally should use backend.search() but we need custom post_processing.
        # VikingDBKnowledgeBackend.search() supports metadata filtering but maybe not custom post_processing dict directly in current version?
        # Let's check VikingDBKnowledgeBackend again. 
        # It has _search_knowledge calling self._viking_sdk_client.search_knowledge with post_processing.
        # But search() method signature is: search(self, query: str, top_k: int = 5, metadata: dict | None = None, rerank: bool = True)
        # It doesn't expose post_processing customization (rerank_instruction).
        # So we keep using _do_request as in the original script or we extend the backend.
        # For this refactor, I will stick to the original logic which uses _do_request.
        
        response = self.backend._do_request(
            body={
                "project": self.backend.volcengine_project,
                "name": self.backend.index,
                "query": query,
                "limit": limit,
                "post_processing": {
                    "rerank_switch": True,
                    "rerank_instruction": _build_rerank_instruction(time_window),
                },
            },
            path="/api/knowledge/collection/search_knowledge",
            method="POST",
        )
        results = response.get("result_list")
        if results is None:
            results = response.get("data", {}).get("result_list", [])
        return results

    def retrieve(self, goal_frame: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a dict with `context_str` and `raw_chunks`.
        """
        payload = goal_frame.get("payload", {}) if isinstance(goal_frame, dict) else {}
        # If goal_frame is already the payload (from governor), handle that.
        # The governor returns {"status": "PROCEED", "payload": goal_frame_dict}
        # But if the user passes the whole governor result, we need to extract payload.
        if "payload" in goal_frame:
             payload = goal_frame["payload"]
        elif "industry" in goal_frame or "indicator" in goal_frame:
             # assume goal_frame is the payload itself
             payload = goal_frame

        industry = payload.get("industry") or []
        indicator = payload.get("indicator") or []
        time_window = payload.get("time_window")
        normalized_time_window = _normalize_time_window(time_window)
        
        if isinstance(industry, str):
            industry = [industry]
        if isinstance(indicator, str):
            indicator = [indicator]
            
        industry_results = []
        raw_chunks = []
        
        for item in industry:
            results = self._search(query=item, limit=1, time_window=None)
            entry = results[0] if results else {}
            if entry:
                raw_chunks.append(entry)
            content = _extract_content(entry)
            industry_results.append(
                {"query": item, "content": content or "", "top1": _extract_factor(content)}
            )
            
        indicator_results = []
        for item in indicator:
            if normalized_time_window:
                search_query = f"{normalized_time_window} {item}"
            else:
                search_query = item
            results = self._search(
                query=search_query, limit=1, time_window=normalized_time_window
            )
            entry = results[0] if results else {}
            if entry:
                raw_chunks.append(entry)
            content = _extract_content(entry) or ""
            indicator_results.append(
                {"query": item, "content": content, "top1": _extract_factor(content)}
            )
            
        # Construct context_str
        context_lines = []
        if industry_results:
            context_lines.append("Industry Info:")
            for res in industry_results:
                context_lines.append(f"- {res['query']}: {res['top1']}")
        
        if indicator_results:
            context_lines.append("\nIndicator Info:")
            for res in indicator_results:
                context_lines.append(f"- {res['query']}: {res['top1']}")
                
        context_str = "\n".join(context_lines)
        
        return {
            "context_str": context_str,
            "raw_chunks": raw_chunks,
            # Keeping original details just in case
            "industry_results": industry_results,
            "indicator_results": indicator_results,
        }
