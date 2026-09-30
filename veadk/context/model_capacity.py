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

"""Reviewed capacities in tokens, not bytes. No runtime network access.

Match only the listed provider/model IDs and transport aliases. Updating a
family does not update its other revisions. Source URLs and verification dates
belong to each row so changes can be reviewed with their evidence.

``context_window`` is a conservative shared input/output ceiling. If a source
publishes only an input cap (Gemini), reuse that cap as the shared ceiling;
never add the output cap to invent a larger window. For k/K/M abbreviations we
use decimal units conservatively. Exact integer limits retain their units.

Output reserves are SDK planning defaults, NOT API generation parameters or a
promise that arbitrary reasoning fits. Native output settings are preserved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date
from importlib.resources import files
import json
import re
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ModelCapacity:
    provider: str
    model_id: str
    context_window: int
    max_input_tokens: int
    max_output_tokens: int
    source: str
    verified_on: str
    default_output_reserve: int
    aliases: tuple[str, ...]
    default_answer_tokens: int | None
    reasoning_token_reserve: int
    answer_only_max_tokens: bool
    ark_thinking_controls: bool


def _invalid(field):
    return ValueError(
        f"invalid_model_capacity_config: {field}. "
        "Check veadk/context/model_capacities.json."
    )


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _invalid("duplicate JSON keys")
        result[key] = value
    return result


def _row_from_config(row):
    if not isinstance(row, dict) or set(row) != {f.name for f in fields(ModelCapacity)}:
        raise _invalid("model fields")
    for field in ("provider", "model_id"):
        if not isinstance(row[field], str) or not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9._:-]*", row[field]
        ):
            raise _invalid(field)
    aliases = row["aliases"]
    if not isinstance(aliases, list) or any(
        not isinstance(alias, str)
        or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:-]*", alias)
        for alias in aliases
    ):
        raise _invalid("aliases")
    if len(set([row["model_id"], *aliases])) != len(aliases) + 1:
        raise _invalid("duplicate aliases")
    for field in (
        "context_window",
        "max_input_tokens",
        "max_output_tokens",
        "default_output_reserve",
    ):
        if type(row[field]) is not int or row[field] <= 0:
            raise _invalid(field)
    window = row["context_window"]
    if (
        row["max_input_tokens"] > window
        or row["max_output_tokens"] > window
        or row["default_output_reserve"] >= window
        or row["default_output_reserve"] > row["max_output_tokens"]
    ):
        raise _invalid("capacity bounds")
    answer = row["default_answer_tokens"]
    if answer is not None and (
        type(answer) is not int or not 0 < answer <= row["max_output_tokens"]
    ):
        raise _invalid("default_answer_tokens")
    reasoning = row["reasoning_token_reserve"]
    if type(reasoning) is not int or not 0 <= reasoning < window:
        raise _invalid("reasoning_token_reserve")
    if (answer or 0) + reasoning > row["default_output_reserve"]:
        raise _invalid("output planning reserves")
    for field in ("answer_only_max_tokens", "ark_thinking_controls"):
        if type(row[field]) is not bool:
            raise _invalid(field)
    if row["answer_only_max_tokens"] and answer is None:
        raise _invalid("answer-only output requires default_answer_tokens")
    try:
        if not isinstance(row["source"], str):
            raise ValueError
        source = urlsplit(row["source"])
        if (
            source.scheme != "https"
            or not source.hostname
            or source.username
            or source.password
        ):
            raise ValueError
        if date.fromisoformat(row["verified_on"]).isoformat() != row["verified_on"]:
            raise ValueError
    except (TypeError, ValueError):
        raise _invalid("source or verified_on") from None
    return ModelCapacity(**{**row, "aliases": tuple(aliases)})


def _capacity_lookup(rows):
    # Bare IDs identify only their reviewed provider. openai/ is also an Ark
    # transport spelling; it never grants cross-provider capacity borrowing.
    result = {}
    for row in rows:
        for model_id in (row.model_id, *row.aliases):
            names = [model_id, f"{row.provider}/{model_id}"]
            if row.provider == "volcengine":
                names.append(f"openai/{model_id}")
            for name in names:
                if name in result:
                    raise _invalid("duplicate model or alias lookup")
                result[name] = row
    return result


def _parse_capacities(text):
    try:
        data = json.loads(text, object_pairs_hook=_unique_fields)
    except (ValueError, RecursionError):
        raise _invalid("JSON syntax or duplicate keys") from None
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "models"}
        or type(data["schema_version"]) is not int
        or data["schema_version"] != 1
        or not isinstance(data["models"], list)
        or not data["models"]
    ):
        raise _invalid("schema_version or models")
    rows = tuple(_row_from_config(row) for row in data["models"])
    _capacity_lookup(rows)  # Reject collisions before accepting any row.
    return rows


def _load_capacities():
    try:
        text = (
            files(__package__)
            .joinpath("model_capacities.json")
            .read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError):
        raise ValueError(
            "model_capacity_config_unavailable: restore "
            "veadk/context/model_capacities.json or reinstall the SDK."
        ) from None
    return _parse_capacities(text)


# Package resources work in installed wheels and do not depend on cwd. Load
# once, without network access; malformed/missing configuration fails closed.
MODEL_CAPACITIES: tuple[ModelCapacity, ...] = _load_capacities()
_CAPACITY_BY_NAME = _capacity_lookup(MODEL_CAPACITIES)


def get_model_capacity(model: str) -> dict:
    """Return a fresh copy so request code cannot mutate the shared table."""
    row = _CAPACITY_BY_NAME.get(model)
    return asdict(row) if row is not None else {}
