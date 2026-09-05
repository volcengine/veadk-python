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

"""Tests for the shared HTTP timeout defaults.

The public constants are computed at import time, so anything that exercises
the environment overrides has to reload the module. Every reload here goes
through the `reload_http_defaults` fixture, whose teardown reloads the module
one final time under the ambient environment -- otherwise a mutated module
object would leak into every later test in the same session.
"""

import importlib
import os
from unittest.mock import patch

import pytest

from veadk.utils import http_defaults


def _env_vars_read_at_import() -> tuple[str, ...]:
    """Environment variables the module reads, recorded from a live reload.

    Deriving the list beats writing one down. A hardcoded list desynchronizes
    the moment a constant is renamed: the stale name keeps getting scrubbed
    while the name actually read is left alone, so an ambient value for it
    fails this file on any machine that sets it.
    """
    seen: list[str] = []
    real_getenv = os.getenv

    def _recording_getenv(name: str, default: str | None = None) -> str | None:
        seen.append(name)
        return real_getenv(name, default)

    with patch.object(http_defaults.os, "getenv", _recording_getenv):
        importlib.reload(http_defaults)
    # Drop the module built under the patched `getenv`, exactly as the fixture
    # teardown does, so discovery leaves no trace.
    importlib.reload(http_defaults)
    return tuple(dict.fromkeys(seen))


_ENV_VARS = _env_vars_read_at_import()


@pytest.fixture
def reload_http_defaults():
    """Reload `http_defaults` under a scrubbed + overridden environment.

    Every variable the module reads is scrubbed unless the test overrides it,
    so an ambient value on the developer's machine cannot reach the assertions.

    The teardown reload is unconditional: it runs even if the test body raises,
    so the module is always restored to the state it had before the test.
    """

    def _reload(**overrides: str):
        with patch.dict(os.environ, overrides, clear=False):
            for name in _ENV_VARS:
                if name not in overrides:
                    os.environ.pop(name, None)
            return importlib.reload(http_defaults)

    try:
        yield _reload
    finally:
        # `patch.dict` has already restored the ambient environment, so this
        # rebuilds exactly the module state the session started with.
        importlib.reload(http_defaults)


def test_default_tuples_have_the_documented_values(reload_http_defaults):
    module = reload_http_defaults()

    assert module.DEFAULT_HTTP_TIMEOUT == (10.0, 60.0)
    assert module.DEFAULT_STREAM_BUDGET_SECONDS == 300.0


def test_default_tuples_are_pairs_of_floats(reload_http_defaults):
    module = reload_http_defaults()

    for timeout in (module.DEFAULT_HTTP_TIMEOUT,):
        assert isinstance(timeout, tuple)
        assert len(timeout) == 2
        connect, read = timeout
        assert isinstance(connect, float)
        assert isinstance(read, float)


def test_scalar_defaults_are_floats(reload_http_defaults):
    module = reload_http_defaults()

    assert module.DEFAULT_CONNECT_TIMEOUT == 10.0
    assert module.DEFAULT_READ_TIMEOUT == 60.0
    assert module.DEFAULT_STREAM_BUDGET_SECONDS == 300.0
    assert isinstance(module.DEFAULT_CONNECT_TIMEOUT, float)
    assert isinstance(module.DEFAULT_READ_TIMEOUT, float)
    assert isinstance(module.DEFAULT_STREAM_BUDGET_SECONDS, float)


def test_http_timeout_is_built_from_the_scalar_halves(reload_http_defaults):
    module = reload_http_defaults()

    assert module.DEFAULT_HTTP_TIMEOUT == (
        module.DEFAULT_CONNECT_TIMEOUT,
        module.DEFAULT_READ_TIMEOUT,
    )


def test_stream_budget_is_a_total_not_a_socket_gap(reload_http_defaults):
    # The stream budget bounds a whole streamed response; the read timeout only
    # bounds the gap between two reads. Conflating them is what let an endless
    # trickle of valid frames hang `tts` forever, so keep the budget a scalar
    # and keep it the larger of the two.
    module = reload_http_defaults()

    assert not isinstance(module.DEFAULT_STREAM_BUDGET_SECONDS, tuple)
    assert module.DEFAULT_STREAM_BUDGET_SECONDS > module.DEFAULT_READ_TIMEOUT


def test_env_float_reads_the_environment_variable():
    with patch.dict(os.environ, {"VEADK_TEST_TIMEOUT": "42.5"}, clear=False):
        assert http_defaults._env_float("VEADK_TEST_TIMEOUT", 10.0) == 42.5


def test_env_float_parses_integer_strings():
    with patch.dict(os.environ, {"VEADK_TEST_TIMEOUT": "7"}, clear=False):
        value = http_defaults._env_float("VEADK_TEST_TIMEOUT", 10.0)

    assert value == 7.0
    assert isinstance(value, float)


def test_env_float_falls_back_when_unset():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("VEADK_TEST_TIMEOUT", None)
        assert http_defaults._env_float("VEADK_TEST_TIMEOUT", 10.0) == 10.0


def test_env_float_falls_back_when_empty():
    with patch.dict(os.environ, {"VEADK_TEST_TIMEOUT": ""}, clear=False):
        assert http_defaults._env_float("VEADK_TEST_TIMEOUT", 10.0) == 10.0


@pytest.mark.parametrize("raw", ["abc", "10s", "1,5", "nan-ish", " "])
def test_env_float_falls_back_on_unparseable_input(raw):
    with patch.dict(os.environ, {"VEADK_TEST_TIMEOUT": raw}, clear=False):
        assert http_defaults._env_float("VEADK_TEST_TIMEOUT", 10.0) == 10.0


def test_env_float_falls_back_on_non_string_value():
    # `float(object())` raises TypeError rather than ValueError; the helper
    # must swallow that too instead of exploding at import time.
    with patch.object(http_defaults.os, "getenv", return_value=object()):
        assert http_defaults._env_float("VEADK_TEST_TIMEOUT", 10.0) == 10.0


def test_env_float_clamps_to_the_minimum():
    with patch.dict(os.environ, {"VEADK_TEST_TIMEOUT": "0.001"}, clear=False):
        assert http_defaults._env_float("VEADK_TEST_TIMEOUT", 10.0) == 1.0
        assert http_defaults._env_float("VEADK_TEST_TIMEOUT", 10.0, minimum=5.0) == 5.0


def test_env_float_clamps_negative_values():
    with patch.dict(os.environ, {"VEADK_TEST_TIMEOUT": "-30"}, clear=False):
        assert http_defaults._env_float("VEADK_TEST_TIMEOUT", 10.0) == 1.0


def test_env_float_does_not_clamp_values_above_the_minimum():
    with patch.dict(os.environ, {"VEADK_TEST_TIMEOUT": "120"}, clear=False):
        assert (
            http_defaults._env_float("VEADK_TEST_TIMEOUT", 10.0, minimum=5.0) == 120.0
        )


def test_env_overrides_apply_at_import_time(reload_http_defaults):
    module = reload_http_defaults(
        VEADK_HTTP_CONNECT_TIMEOUT="3",
        VEADK_HTTP_READ_TIMEOUT="17.5",
        VEADK_HTTP_STREAM_BUDGET="900",
    )

    assert module.DEFAULT_CONNECT_TIMEOUT == 3.0
    assert module.DEFAULT_READ_TIMEOUT == 17.5
    assert module.DEFAULT_STREAM_BUDGET_SECONDS == 900.0
    assert module.DEFAULT_HTTP_TIMEOUT == (3.0, 17.5)


def test_env_overrides_are_clamped_at_import_time(reload_http_defaults):
    module = reload_http_defaults(
        VEADK_HTTP_CONNECT_TIMEOUT="0",
        VEADK_HTTP_READ_TIMEOUT="0.25",
    )

    assert module.DEFAULT_HTTP_TIMEOUT == (1.0, 1.0)


def test_bad_env_overrides_keep_the_defaults(reload_http_defaults):
    module = reload_http_defaults(
        VEADK_HTTP_CONNECT_TIMEOUT="abc",
        VEADK_HTTP_READ_TIMEOUT="",
        VEADK_HTTP_STREAM_BUDGET="not-a-number",
    )

    assert module.DEFAULT_HTTP_TIMEOUT == (10.0, 60.0)
    assert module.DEFAULT_STREAM_BUDGET_SECONDS == 300.0


def test_module_restored_after_reload_fixture(reload_http_defaults):
    # Guards the fixture itself: a mutated module must not survive a test.
    module = reload_http_defaults(VEADK_HTTP_READ_TIMEOUT="999")

    assert module.DEFAULT_READ_TIMEOUT == 999.0
    assert importlib.reload(http_defaults).DEFAULT_HTTP_TIMEOUT[1] != 999.0


def test_ambient_env_overrides_do_not_reach_the_assertions(reload_http_defaults):
    # Guards the fixture's scrub list: a deployment that sets any of these --
    # which is exactly what the docs tell users to do -- must not turn this
    # file red. Setting all of them at once covers whichever the module reads.
    ambient = {name: "42" for name in _ENV_VARS}

    with patch.dict(os.environ, ambient, clear=False):
        module = reload_http_defaults()

        assert module.DEFAULT_HTTP_TIMEOUT == (10.0, 60.0)
        assert module.DEFAULT_STREAM_BUDGET_SECONDS == 300.0


def test_every_discovered_env_var_moves_a_public_constant(reload_http_defaults):
    # Tripwire on the discovery itself: an empty or stale list would scrub
    # nothing useful and quietly restore the ambient-environment bug. Each name
    # discovered has to actually change one of the exported constants.
    assert _ENV_VARS

    defaults = {
        name: getattr(reload_http_defaults(), name) for name in http_defaults.__all__
    }

    for env_var in _ENV_VARS:
        module = reload_http_defaults(**{env_var: "123"})
        overridden = {name: getattr(module, name) for name in module.__all__}

        assert overridden != defaults, env_var


def test_all_exports_are_present():
    for name in http_defaults.__all__:
        assert hasattr(http_defaults, name)
