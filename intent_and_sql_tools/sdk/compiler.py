from typing import Any


class ContextCompiler:
    def compile(self, envelope: dict) -> str:
        intent = self._get_str(envelope, "intent") or "unknown"
        payload = envelope.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {"value": payload}
        if intent == "query_metric":
            return self._compile_query_metric(payload)
        if intent == "screening":
            return self._compile_screening(payload)
        if intent == "plot_chart":
            return self._compile_plot_chart(payload)
        return self._compile_unknown(intent, payload)

    def _compile_query_metric(self, payload: dict) -> str:
        metrics = self._listify(payload.get("metrics") or payload.get("metric"))
        time_range = payload.get("time_range") or payload.get("timeRange")
        filters = self._listify(payload.get("filters"))
        dimensions = self._listify(payload.get("dimensions") or payload.get("dims"))
        parts = [
            "Task: Query metrics with strict schema adherence.",
            f"Metrics: {self._fmt_list(metrics)}",
            f"TimeRange: {self._fmt_value(time_range)}",
            f"Filters: {self._fmt_list(filters)}",
            f"Dimensions: {self._fmt_list(dimensions)}",
            "Constraints: Use documentation definitions; do not hallucinate columns.",
        ]
        return "\n".join(parts)

    def _compile_screening(self, payload: dict) -> str:
        universe = payload.get("universe")
        factors = self._listify(payload.get("factors") or payload.get("rules"))
        sort_by = payload.get("sort_by") or payload.get("sortBy")
        limit = payload.get("limit")
        parts = [
            "Task: Screen entities using structured factors.",
            f"Universe: {self._fmt_value(universe)}",
            f"Factors: {self._fmt_list(factors)}",
            f"SortBy: {self._fmt_value(sort_by)}",
            f"Limit: {self._fmt_value(limit)}",
            "Constraints: Use documentation definitions; do not hallucinate columns.",
        ]
        return "\n".join(parts)

    def _compile_plot_chart(self, payload: dict) -> str:
        metric = payload.get("metric") or payload.get("metrics")
        time_range = payload.get("time_range") or payload.get("timeRange")
        dimension = payload.get("dimension") or payload.get("dimensions")
        chart_type = payload.get("chart_type") or payload.get("chartType")
        parts = [
            "Task: Generate visualization request.",
            f"Metric: {self._fmt_value(metric)}",
            f"TimeRange: {self._fmt_value(time_range)}",
            f"Dimension: {self._fmt_value(dimension)}",
            f"ChartType: {self._fmt_value(chart_type)}",
            "Constraints: Use documentation definitions; do not hallucinate columns.",
        ]
        return "\n".join(parts)

    def _compile_unknown(self, intent: str, payload: dict) -> str:
        parts = [
            "Task: Unknown intent, provide best-effort structured summary.",
            f"Intent: {intent}",
            f"RawPayload: {self._fmt_value(payload)}",
            "Constraints: Use documentation definitions; do not hallucinate columns.",
        ]
        return "\n".join(parts)

    def _listify(self, value: Any) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return [v for v in value if v not in (None, "")]
        return [value]

    def _fmt_list(self, value: list) -> str:
        return ", ".join([str(v) for v in value]) if value else "None"

    def _fmt_value(self, value: Any) -> str:
        if value in (None, "", []):
            return "None"
        return str(value)

    def _get_str(self, payload: dict, key: str) -> str | None:
        value = payload.get(key)
        if value in (None, ""):
            return None
        return str(value)
