"""Matched fixed-model controls and multi-arm accounting for live calibration.

These controls bypass classification explicitly; they never fabricate SystemOne
answers. The routing adapter, tool guards and history replay stay identical.
"""

import copy
from types import MethodType

from veadk.routing.context import RouteSelection


def install_fixed_control(agent, route):
    if route not in {"strong", "simple"}:
        raise ValueError("fixed control must select strong or simple")
    classifier = agent.model.classifier

    async def classify(self, llm_request, *, invocation_id, session_id=""):
        return RouteSelection(
            route=route,
            reason="fixed_model_control",
            invocation_id=invocation_id,
            session_id=session_id,
            model_name=self.registry.runtimes[0].config.name
            if route == "simple"
            else None,
        )

    classifier.classify = MethodType(classify, classifier)


def summarize_comparisons(rows, attempts):
    from query_routing_economics import summarize

    reports = {}
    for arm in sorted({row["arm"] for row in rows} - {"strong"}):
        selected = copy.deepcopy([r for r in rows if r["arm"] in {"strong", arm}])
        transport = copy.deepcopy(
            [r for r in attempts if r.get("arm") in {"strong", arm}]
        )
        for record in selected + transport:
            if record.get("arm") == arm:
                record["arm"] = "routed"
        reports[arm] = summarize(selected, transport)
        enriched = {(r["cohort"], r["id"], r["arm"]): r for r in selected}
        for row in rows:
            if row["arm"] not in {"strong", arm}:
                continue
            key = (
                row["cohort"],
                row["id"],
                "strong" if row["arm"] == "strong" else "routed",
            )
            original_arm = row["arm"]
            row.update(enriched[key])
            row["arm"] = original_arm
    return {"cohorts": {arm: report["cohorts"] for arm, report in reports.items()}}
