"""Exact Prometheus vector operations under an explicitly registered schema."""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, localcontext

NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\Z")


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def vector_values(text):
    if len(text.encode()) > 2_000_000:
        raise ValueError("document_limit")
    obj = json.loads(text, object_pairs_hook=no_duplicates)
    if (
        not isinstance(obj, dict)
        or set(obj) != {"status", "data"}
        or obj["status"] != "success"
    ):
        raise ValueError("unsupported_vector")
    data = obj["data"]
    if (
        not isinstance(data, dict)
        or set(data) != {"resultType", "result"}
        or data["resultType"] != "vector"
    ):
        raise ValueError("unsupported_vector")
    rows = data["result"]
    if not isinstance(rows, list) or len(rows) > 4000:
        raise ValueError("record_limit")
    values = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"metric", "value"}:
            raise ValueError("unsupported_record")
        if (
            not isinstance(row["metric"], dict)
            or len(row["metric"]) > 64
            or not all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in row["metric"].items()
            )
        ):
            raise ValueError("unsupported_labels")
        pair = row["value"]
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or type(pair[0]) not in (int, float)
            or not 0 <= pair[0] <= 3_000_000_000
        ):
            raise ValueError("unsupported_pair")
        raw = pair[1]
        if (
            not isinstance(raw, str)
            or not 1 <= len(raw) <= 40
            or not NUMBER.fullmatch(raw)
        ):
            raise ValueError("unsupported_number")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            raise ValueError("number_limit") from None
        if not value.is_finite() or value and not -20 <= value.adjusted() <= 20:
            raise ValueError("number_limit")
        # Zero can carry an arbitrarily large exponent despite adjusted-value
        # bounds; canonicalize before fixed-point formatting allocates memory.
        values.append(value if value else Decimal(0))
    return values


def statistic(text, operation):
    values = vector_values(text)
    if operation == "count":
        value = Decimal(len(values))
    elif operation in ("tail", "max") and not values:
        return {"error": "empty_vector", "complete": False}
    elif operation == "tail":
        value = values[-1]
    elif operation == "max":
        value = max(values)
    elif operation == "sum":
        with localcontext() as context:
            context.prec = 100
            value = sum(values, Decimal(0))
    else:
        return {"error": "unsupported_operation", "complete": False}
    formatted = format(value, "f")
    formatted = formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
    return {
        "operation": operation,
        "value": formatted,
        "record_count": len(values),
        "complete": True,
        "meaning": "Exact operation on this vector's data.result/value[1], without unit conversion or business interpretation.",
    }


def overview(text):
    values = vector_values(text)
    with localcontext() as context:
        context.prec = 100
        total = sum(values, Decimal(0))

    def number(value):
        if value is None:
            return None
        formatted = format(value, "f")
        return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted

    return {
        "complete": True,
        "scope": "data.result[*].value[1]",
        "record_count": len(values),
        "tail_value": number(values[-1]) if values else None,
        "max_value": number(max(values)) if values else None,
        "sum_values": number(total),
        "business_units_inferred": False,
        "meaning": "Exact arithmetic over every original sample, not a business total or unit conversion. Use sums only when arithmetic across all these values is requested.",
    }
