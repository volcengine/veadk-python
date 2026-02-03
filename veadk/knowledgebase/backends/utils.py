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

from pathlib import Path

from llama_index.core.node_parser import (
    CodeSplitter,
    HTMLNodeParser,
    MarkdownNodeParser,
    SentenceSplitter,
)


def get_llama_index_splitter(
    file_path: str,
) -> CodeSplitter | MarkdownNodeParser | HTMLNodeParser | SentenceSplitter:
    suffix = Path(file_path).suffix.lower()

    if suffix in [".py", ".js", ".java", ".cpp"]:
        return CodeSplitter(language=suffix.strip("."))
    elif suffix in [".md"]:
        return MarkdownNodeParser()
    elif suffix in [".html", ".htm"]:
        return HTMLNodeParser()
    else:
        return SentenceSplitter(chunk_size=512, chunk_overlap=50)
