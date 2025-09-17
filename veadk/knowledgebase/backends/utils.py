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

import json
from pathlib import Path
from typing import Literal

from llama_index.core.node_parser import (
    CodeSplitter,
    HTMLNodeParser,
    MarkdownNodeParser,
    SentenceSplitter,
)
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request
from volcengine.Credentials import Credentials


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


def build_vikingdb_knowledgebase_request(
    path: str,
    volcengine_access_key: str,
    volcengine_secret_key: str,
    method: Literal["GET", "POST", "PUT", "DELETE"] = "POST",
    region: str = "cn-beijing",
    params=None,
    data=None,
    doseq=0,
) -> Request:
    if params:
        for key in params:
            if (
                type(params[key]) is int
                or type(params[key]) is float
                or type(params[key]) is bool
            ):
                params[key] = str(params[key])
            elif type(params[key]) is list:
                if not doseq:
                    params[key] = ",".join(params[key])

    r = Request()
    r.set_shema("https")
    r.set_method(method)
    r.set_connection_timeout(10)
    r.set_socket_timeout(10)

    mheaders = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    r.set_headers(mheaders)

    if params:
        r.set_query(params)

    r.set_path(path)

    if data is not None:
        r.set_body(json.dumps(data))

    credentials = Credentials(
        volcengine_access_key, volcengine_secret_key, "air", region
    )
    SignerV4.sign(r, credentials)
    return r
