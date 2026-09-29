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

import pytest

from frontend.server.mpa_a2a import mpa_a2a_rpc_url


@pytest.mark.parametrize("suffix", ["", "/"])
def test_shared_runtime_prefix_is_restored(suffix):
    assert (
        mpa_a2a_rpc_url(
            "https://runtime.example/runtime/r-one" + suffix,
            "https://runtime.example:443/a2a/jsonrpc",
        )
        == "https://runtime.example/runtime/r-one/a2a/jsonrpc"
    )


@pytest.mark.parametrize(
    "endpoint,card",
    [
        (
            "https://runtime.example/runtime/r-one",
            "https://@runtime.example/a2a/jsonrpc",
        ),
        ("https://runtime.example", "https://runtime.example/a2a/jsonrpc"),
        ("https://runtime.example/runtime/r-one", "https://other.example/a2a/jsonrpc"),
        ("https://runtime.example/runtime/r-one", "http://runtime.example/a2a/jsonrpc"),
        (
            "https://runtime.example/runtime/r-one",
            "https://runtime.example:8443/a2a/jsonrpc",
        ),
        (
            "https://runtime.example/runtime/r-one",
            "https://runtime.example/runtime/r-one/a2a/jsonrpc",
        ),
        ("https://runtime.example/runtime/r-one", "https://runtime.example/custom"),
        (
            "https://runtime.example/runtime/r-one",
            "https://runtime.example/a2a/jsonrpc?q=1",
        ),
        (
            "https://runtime.example/runtime/r-one",
            "https://runtime.example/a2a/jsonrpc#x",
        ),
        (
            "https://runtime.example/runtime/r-one",
            "https://user@runtime.example/a2a/jsonrpc",
        ),
        ("https://runtime.example/unrelated", "https://runtime.example/a2a/jsonrpc"),
        (
            "https://runtime.example/runtime/%2e%2e",
            "https://runtime.example/a2a/jsonrpc",
        ),
        (
            "https://runtime.example/runtime/r-one",
            "https://runtime.example:bad/a2a/jsonrpc",
        ),
    ],
)
def test_other_card_addresses_are_preserved(endpoint, card):
    assert mpa_a2a_rpc_url(endpoint, card) == card
