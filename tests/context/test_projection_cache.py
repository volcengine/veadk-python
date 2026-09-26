# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

"""Validate archived projections without trusting cache order or stale ranges."""

import copy

import pytest
from google.adk.events import Event, EventActions
from google.adk.sessions import Session
from google.genai import types

from veadk.context import manager
from veadk.context.history import fingerprint
from veadk.context.runtime import ContextScope

KEY = "veadk:context:synthetic-policy-branch"


def contents():
    return [
        types.Content(role="user", parts=[types.Part(text=f"Original fact {i}")])
        for i in range(40)
    ]


def record(source, count):
    return {
        "version": 1,
        "source_count": count,
        "source_hash": fingerprint(source[:count]),
        "summary": f"Synthetic summary covering {count} contents",
    }


def scope_for(state=None, records=()):
    session = Session(
        id="session",
        app_name="offline",
        user_id="synthetic",
        state=state or {},
        events=[
            Event(author="agent", actions=EventActions(state_delta=delta))
            for delta in records
        ],
    )
    return ContextScope(session=session, agent_name="agent", branch="")


@pytest.mark.parametrize("newest_location", ["pending", "state", "events"])
def test_projection_recency_is_source_coverage_not_completion_order(newest_location):
    source = contents()
    older, newer = record(source, 4), record(source, 8)
    scope = scope_for({KEY: older}, [{KEY: newer}, {KEY: older}])
    if newest_location == "pending":
        scope.pending_state[KEY] = record(source, 12)
        expected = scope.pending_state[KEY]
    elif newest_location == "state":
        scope.session.state[KEY] = record(source, 12)
        expected = scope.session.state[KEY]
    else:
        expected = newer
    before = copy.deepcopy((scope.pending_state, scope.session.model_dump(), source))
    assert manager._cached_summary(scope, KEY, source) == expected
    assert (scope.pending_state, scope.session.model_dump(), source) == before


@pytest.mark.parametrize(
    "update",
    [
        {"source_count": True},
        {"source_count": "12"},
        {"source_count": 0},
        {"source_count": 40},
        {"version": 999},
        {"summary": None},
        {"source_hash": "wrong-source-fingerprint"},
    ],
)
def test_invalid_newer_projection_does_not_displace_verified_original_range(update):
    source = contents()
    valid = record(source, 4)
    invalid = {**record(source, 12), **update}
    scope = scope_for({KEY: invalid}, [{KEY: valid}])
    assert manager._cached_summary(scope, KEY, source) == valid


def test_unrelated_policy_or_branch_records_cannot_be_reused():
    source = contents()
    scope = scope_for(records=[{"veadk:context:other-branch": record(source, 12)}])
    assert manager._cached_summary(scope, KEY, source) is None
    assert manager._cached_summary(None, KEY, source) is None


def test_changed_history_invalidates_state_and_archived_projections():
    source = contents()
    cached = record(source, 12)
    scope = scope_for({KEY: cached}, [{KEY: cached}])
    source[0].parts[0].text = "Changed original fact"
    assert manager._cached_summary(scope, KEY, source) is None


def test_untrusted_cache_ranges_have_bounded_fingerprint_work(monkeypatch):
    source = contents()
    scope = scope_for(
        records=[
            {KEY: {**record(source, count), "source_hash": f"invalid-{count}"}}
            for count in range(1, 40)
        ]
    )
    checked = []

    def observe(values):
        checked.append(len(values))
        return fingerprint(values)

    monkeypatch.setattr(manager, "fingerprint", observe)
    assert manager._cached_summary(scope, KEY, source) is None
    assert checked == list(range(39, 31, -1))


def test_multiple_candidates_for_one_range_count_the_original_only_once(monkeypatch):
    source = contents()
    cached = record(source, 12)
    scope = scope_for(
        records=[
            {KEY: cached},
            *[{KEY: {**cached, "source_hash": f"invalid-{i}"}} for i in range(6)],
        ]
    )
    checked = []

    def observe(values):
        checked.append(len(values))
        return fingerprint(values)

    monkeypatch.setattr(manager, "fingerprint", observe)
    assert manager._cached_summary(scope, KEY, source) == cached
    assert checked == [12]
