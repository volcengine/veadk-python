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

from frontend.server.skills.repository import SkillRepositoryError
from frontend.server.skills.review_text import decode_review_text, encode_review_text


@pytest.mark.parametrize("text", ["", "内容完整，同意公开。\n保留示例！", "😀" * 256])
def test_review_text_preserves_punctuation_multiline_and_maximum_length(text):
    tags = encode_review_text("comment", text)
    assert decode_review_text(tags, "comment") == text
    assert all(len(value) <= 256 and value.isascii() for value in tags.values())
    assert all("\n" not in value for value in tags.values())


def test_read_legacy_text_and_ignore_obsolete_chunks():
    assert decode_review_text({"comment": "已有备注"}, "comment") == "已有备注"
    tags = encode_review_text("comment", "😀" * 256)
    tags.update(encode_review_text("comment", "简短的新备注"))
    assert decode_review_text(tags, "comment") == "简短的新备注"


def test_missing_chunk_fails_instead_of_showing_incomplete_comment():
    tags = encode_review_text("comment", "😀" * 256)
    del tags["comment.1"]
    with pytest.raises(SkillRepositoryError, match="完整"):
        decode_review_text(tags, "comment")
