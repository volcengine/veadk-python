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

"""Bounded deterministic queries over explicitly described original data."""

import json
import re


def count_unique(text, record_format):
    if len(text.encode()) > 2_000_000:
        raise ValueError("document_limit")
    if record_format == "json_array_strings":
        records = json.loads(text)
        if not isinstance(records, list) or not all(
            isinstance(x, str) for x in records
        ):
            raise ValueError("unsupported_records")
    elif record_format == "numbered_paragraphs":
        # Explicit contract: consecutive Paragraph N: records separated by a
        # blank line. Only framing whitespace is stripped; equality is exact.
        matches = list(re.finditer(r"(?:\A|\n\n)Paragraph ([1-9][0-9]*):[ \t]*", text))
        if not matches or matches[0].start() != 0:
            raise ValueError("unsupported_records")
        if [int(m[1]) for m in matches] != list(range(1, len(matches) + 1)):
            raise ValueError("ambiguous_record_boundaries")
        records = [
            text[
                m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)
            ].strip()
            for i, m in enumerate(matches)
        ]
        if any(not item for item in records):
            raise ValueError("empty_record")
    else:
        raise ValueError("unsupported_operation")
    if len(records) > 10000:
        raise ValueError("record_limit")
    return {
        "operation": "count_unique",
        "value": len(set(records)),
        "record_count": len(records),
        "complete": True,
        "equality": "exact text after declared framing removal",
    }


def search(text, query, maximum):
    """Return bounded ranked original evidence, with unchanged character offsets."""
    from .search_evidence import search_ranges

    matches = search_ranges(text, query, maximum)
    return {
        "found": bool(matches),
        "matches": matches,
        "complete": False,
        "total_characters": len(text),
    }
