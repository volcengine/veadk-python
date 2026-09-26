"""History framing must preserve every chosen character without duplicates."""

import copy
import re
from itertools import pairwise

import pytest
from google.genai import types

from veadk.context.config import ContextCompressionConfig
from veadk.context.evidence import evidence_ranges
from veadk.context.history_projection import project_history


@pytest.mark.parametrize("prefix", ["Invoice approval pending. ", "订单待批准🙂。"])
def test_history_excerpts_merge_overlaps_and_preserve_selected_characters(prefix):
    text = prefix * 400 + "Exact invoice code IV-8721; approval remains pending.\n"
    text += "Other source facts. " * 600
    question = "What is the invoice code and approval status?"
    contents = [
        types.Content(role="user", parts=[types.Part(text=text)]),
        types.Content(role="user", parts=[types.Part(text=question)]),
    ]
    before = copy.deepcopy(contents)
    result = project_history(contents, 1, ContextCompressionConfig(), 16000)
    assert result is not None
    projected, _ = result
    preview = projected[0].parts[0].text
    chosen = evidence_ranges(text, question, 6400 - 512 - 256)
    expected = [(m["offset"], m["end"]) for m in chosen]
    expected += [(0, len(text.encode()[:192].decode(errors="ignore")))]
    expected += [
        (len(text) - len(text.encode()[-192:].decode(errors="ignore")), len(text))
    ]
    represented = []
    for match in re.finditer(r"(?m)^\[(\d+):(\d+)\]\n", preview):
        start, end = map(int, match.groups())
        assert preview[match.end() : match.end() + end - start] == text[start:end]
        represented.append((start, end))
    assert represented
    assert all(b < c for (_, b), (c, _) in pairwise(represented))
    assert all(any(a <= x and y <= b for a, b in represented) for x, y in expected)
    assert contents == before and projected[-1] == before[-1]
