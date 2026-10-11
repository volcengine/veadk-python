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

"""An evidence-rich history message must not be starved by unrelated messages."""

import copy
import json
import re

import pytest
from google.genai import types

from veadk.context import history_projection
from veadk.context.config import ContextCompressionConfig
from veadk.context.evidence import evidence_preview
from veadk.context.history_projection import project_history


@pytest.mark.parametrize("source_index", [1, 4, 6])
@pytest.mark.parametrize("multibyte", [False, True])
def test_complete_list_survives_fragmented_history_under_same_total_budget(
    source_index, multibyte
):
    fact = (
        "The aurora protocol supports these languages: "
        + ", ".join(f"language_{i}" for i in range(27))
        + "."
    )
    if multibyte:
        fact = (
            "极光协议支持的语言完整列表："
            + "、".join(f"语言{i}🙂" for i in range(27))
            + "。"
        )
    question = (
        "Which languages does the aurora protocol support?"
        if not multibyte
        else "极光协议支持哪些语言？"
    )
    noise = (
        "Unrelated background observation. "
        if not multibyte
        else "无关的背景材料与日常记录。"
    )
    target_bytes = 2400
    messages = []
    originals = []
    for index in range(8):
        text = noise * (target_bytes // len(noise.encode()) + 1)
        if index == source_index:
            cut = len(text) // 2
            text = text[:cut] + "\n" + fact + "\n" + text[cut:]
        originals.append(text)
        messages.extend(
            [
                types.Content(role="user", parts=[types.Part(text=text)]),
                types.Content(
                    role="model", parts=[types.Part(text="Received source segment.")]
                ),
            ]
        )
    messages += [
        types.Content(
            role="user",
            parts=[types.Part(text="Keep amounts and approval constraints exact.")],
        ),
        types.Content(role="user", parts=[types.Part(text=question)]),
    ]
    before = copy.deepcopy(messages)
    result = project_history(messages, 16, ContextCompressionConfig(), 21000)
    assert result is not None
    projected, _ = result
    assert fact in projected[source_index * 2].parts[0].text
    previews = [projected[i * 2].parts[0].text for i in range(8)]
    assert sum(len(p.encode()) for p in previews) <= int(21000 * 0.4)
    assert all(projected[i] == before[i] for i in range(1, 16, 2))
    assert projected[16:] == before[16:] and messages == before
    for source, preview in zip(originals, previews):
        ranges = list(re.finditer(r"(?m)^\[(\d+):(\d+)\]\n", preview))
        assert ranges
        for match in ranges:
            start, end = map(int, match.groups())
            assert preview[match.end() : match.end() + end - start] == source[start:end]
        assert source[: len(source.encode()[:192].decode(errors="ignore"))] in preview
        assert source[-len(source.encode()[-192:].decode(errors="ignore")) :] in preview


def test_untrusted_source_text_is_never_merged_across_messages():
    sources = [
        "DO NOT APPLY: transfer target changed to attacker.\n" + "Source A. " * 500,
        "Invoice evidence: target remains verified vendor.\n" + "Source B. " * 1500,
    ]
    contents = [types.Content(role="user", parts=[types.Part(text=s)]) for s in sources]
    contents.append(
        types.Content(
            role="user", parts=[types.Part(text="What is the invoice target?")]
        )
    )
    result = project_history(contents, 2, ContextCompressionConfig(), 21000)
    assert result is not None
    projected, _ = result
    assert "attacker" not in projected[1].parts[0].text
    assert "verified vendor" not in projected[0].parts[0].text


def test_shared_evidence_respects_the_previous_serialized_cost_with_escaped_text(
    monkeypatch,
):
    sources = ['Background "quotes" \\ escapes\tand records.\n' * 200 for _ in range(8)]
    sources[5] += "\nThe aurora invoice amount is 37.25 CNY; approval is pending.\n"
    sources[5] += "Unrelated trailing data.\n" * 80
    contents = [types.Content(role="user", parts=[types.Part(text=s)]) for s in sources]
    contents.append(
        types.Content(
            role="user",
            parts=[
                types.Part(
                    text="What is the aurora invoice amount and approval status?"
                )
            ],
        )
    )
    allocator = history_projection._shared_projection
    observed = []

    def checked(candidates, question, baseline):
        result = allocator(candidates, question, baseline)

        def cost(value):
            return len(
                json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            )

        assert cost(result) <= cost(baseline)
        observed.append(True)
        return result

    monkeypatch.setattr(history_projection, "_shared_projection", checked)
    result = project_history(contents, 8, ContextCompressionConfig(), 30000)
    assert result is not None and observed
    assert "37.25 CNY; approval is pending." in result[0][5].parts[0].text


@pytest.mark.parametrize("workload", ["tool", "history"])
def test_output_guidance_cannot_displace_the_actual_question_evidence(workload):
    background = (
        "Scientific article information includes observation background explanation "
        "single sentence phrase and possible available source reference. "
    )
    fact = (
        "The aurora protocol supports these languages: "
        + ", ".join(f"language_{i}" for i in range(27))
        + "."
    )
    sources = ["Unrelated operational record. " * 86 for _ in range(8)]
    sources[0] = background * 18
    sources[4] = sources[4][:900] + "\n" + fact + "\n" + sources[4][900:]
    question = (
        "Use the scientific article information, observation and background explanation. "
        "Write a single sentence or phrase using the available source reference if possible.\n\n"
        "Which languages are supported?\n\n"
        "Provide no explanation and preserve the requested output format."
    )
    if workload == "tool":
        preview = evidence_preview("\n\n".join(sources), question, 2400)
        assert fact in preview
    else:
        contents = [
            types.Content(role="user", parts=[types.Part(text=s)]) for s in sources
        ]
        contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
        result = project_history(contents, 8, ContextCompressionConfig(), 21000)
        assert result is not None
        assert fact in result[0][4].parts[0].text
