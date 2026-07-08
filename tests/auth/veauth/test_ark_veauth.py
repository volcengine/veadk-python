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
from unittest.mock import patch

from veadk.auth.veauth.ark_veauth import get_ark_token


def _list_page(items, total, page):
    return {"Result": {"TotalCount": total, "PageNumber": page, "Items": items}}


def _raw(api_key):
    return {"Result": {"ApiKey": api_key}}


def _key(id_, name):
    return {"Id": id_, "Name": name}


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.delenv("CLOUD_PROVIDER", raising=False)


def test_no_name_uses_first_key():
    """Legacy behavior: without a name, the first key on page 1 is used."""
    with patch("veadk.auth.veauth.ark_veauth.ve_request") as m:
        m.side_effect = [
            _list_page(
                [_key("id-1", "first"), _key("id-2", "second")], total=2, page=1
            ),
            _raw("sk-FIRST"),
        ]
        assert get_ark_token() == "sk-FIRST"
        # Only one ListApiKeys page + one GetRawApiKey; no pagination.
        assert m.call_count == 2
        assert m.call_args_list[-1].kwargs["request_body"] == {"Id": "id-1"}


def test_name_found_on_later_page_paginates_and_stops():
    """A named key on page 3 is found by paging; paging stops once matched."""
    with patch("veadk.auth.veauth.ark_veauth.ve_request") as m:
        m.side_effect = [
            _list_page([_key("a", "n1"), _key("b", "n2")], total=6, page=1),
            _list_page([_key("c", "n3"), _key("d", "n4")], total=6, page=2),
            _list_page([_key("e", "wanted"), _key("f", "n6")], total=6, page=3),
            _raw("sk-WANTED"),
        ]
        assert get_ark_token(api_key_name="wanted") == "sk-WANTED"
        # 3 ListApiKeys pages + 1 GetRawApiKey; did not fetch a 4th page.
        assert m.call_count == 4
        # Pagination is sent as query params, not in the body.
        list_call = m.call_args_list[0]
        assert list_call.kwargs["query"] == {"PageNumber": "1", "PageSize": "10"}
        assert m.call_args_list[-1].kwargs["request_body"] == {"Id": "e"}


def test_name_not_found_raises_after_full_scan():
    """A wrong/absent name scans the whole list and then errors clearly."""
    with patch("veadk.auth.veauth.ark_veauth.ve_request") as m:
        m.side_effect = [
            _list_page([_key("a", "n1")], total=2, page=1),
            _list_page([_key("b", "n2")], total=2, page=2),
        ]
        with pytest.raises(ValueError, match="my-api-key.*not found"):
            get_ark_token(api_key_name="my-api-key")
        # Both pages scanned; GetRawApiKey never called.
        assert m.call_count == 2


def test_name_found_on_first_page_no_extra_pages():
    with patch("veadk.auth.veauth.ark_veauth.ve_request") as m:
        m.side_effect = [
            _list_page([_key("x", "wanted"), _key("y", "other")], total=50, page=1),
            _raw("sk-X"),
        ]
        assert get_ark_token(api_key_name="wanted") == "sk-X"
        assert m.call_count == 2  # matched on page 1, no further paging
