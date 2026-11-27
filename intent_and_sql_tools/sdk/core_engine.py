import json
from typing import Any, Callable

from .registry import ToolRegistry


class VannaBase:
    def __init__(
        self,
        config: dict,
        llm_stub: Callable[[list[dict]], str] | None = None,
        impl: Any | None = None,
    ):
        self._config = config or {}
        self._impl = impl
        self._llm_stub = llm_stub

    def _ensure_impl(self):
        if self._impl is None:
            from vanna.chromadb import ChromaDB_VectorStore
            from vanna.vertexai import VertexAI_Chat

            class _Impl(ChromaDB_VectorStore, VertexAI_Chat):
                def __init__(self, config: dict):
                    ChromaDB_VectorStore.__init__(self, config=config)
                    VertexAI_Chat.__init__(self, config=config)

            self._impl = _Impl(self._config)
        return self._impl

    def _submit_prompt(self, messages: list[dict]) -> str:
        if self._llm_stub is not None:
            return self._llm_stub(messages)
        impl = self._ensure_impl()
        return impl.submit_prompt(messages)

    def _get_related_documentation(self, question: str):
        impl = self._ensure_impl()
        return impl.get_related_documentation(question)

    def _get_similar_question_sql(self, question: str):
        impl = self._ensure_impl()
        return impl.get_similar_question_sql(question)


class IntentVanna(VannaBase):
    def generate_envelope(self, question: str) -> dict[str, Any]:
        try:
            docs = self._get_related_documentation(question)
            examples = self._get_similar_question_sql(question)
            system_prompt = (
                "Role: Semantic Parser.\n"
                "Task: Map query to JSON based on Knowledge.\n"
                f"Knowledge: {docs}\n"
                f"Examples: {examples}\n"
                "Output: JSON (IntentEnvelope)\n"
            )
            raw_resp = self._submit_prompt(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ]
            )
            envelope = json.loads(raw_resp)
            if not isinstance(envelope, dict):
                raise ValueError("IntentEnvelope must be a dict")
            intent = envelope.get("intent")
            if not intent:
                raise ValueError("Missing intent")
            payload = envelope.get("payload") or {}
            debug_context = {
                "docs": _summarize_debug(docs),
                "examples": _summarize_debug(examples),
            }
            tool_name = ToolRegistry.get_tool_name(intent)
            if tool_name == "unknown_tool":
                m = getattr(ToolRegistry, "_intent_map", {})
                if isinstance(m, dict) and intent in m:
                    tool_name = m[intent]
            return {
                "intent": intent,
                "payload": payload,
                "next_tool": tool_name,
                "error": None,
                "confidence": envelope.get("confidence"),
                "debug_context": debug_context,
            }
        except Exception as exc:
            return {
                "intent": "unknown",
                "payload": {},
                "next_tool": "unknown_tool",
                "error": str(exc),
                "confidence": None,
                "debug_context": None,
            }


class SQLVanna(VannaBase):
    def generate_sql(self, question: str) -> str:
        impl = self._ensure_impl()
        return impl.generate_sql(question=question)

    def generate_sql_from_context(self, context: str) -> str:
        return self.generate_sql(question=context)

    def run_sql(self, sql: str):
        impl = self._ensure_impl()
        return impl.run_sql(sql)


class MockVannaImpl:
    def __init__(
        self,
        docs: str = "DOCS",
        examples: str = "EXAMPLES",
        response: str = '{"intent":"query_metric","payload":{"metric":"revenue"}}',
    ):
        self._docs = docs
        self._examples = examples
        self._response = response

    def get_related_documentation(self, question: str):
        return self._docs

    def get_similar_question_sql(self, question: str):
        return self._examples

    def submit_prompt(self, messages: list[dict]):
        return self._response

    def generate_sql(self, question: str) -> str:
        return "SELECT 1"

    def run_sql(self, sql: str):
        return [{"ok": True}]

    def train(self, **kwargs):
        return True

def _summarize_debug(value: Any, limit: int = 400):
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit]
