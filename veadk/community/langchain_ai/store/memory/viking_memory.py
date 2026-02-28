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

from __future__ import annotations

import json
from collections.abc import Iterable

from langgraph.store.base import (
    BaseStore,
    GetOp,
    ListNamespacesOp,
    Op,
    PutOp,
    Result,
    SearchOp,
)

from veadk.memory.long_term_memory_backends.vikingdb_memory_backend import (
    VikingDBLTMBackend,
)


# mem0
# viking db
class VikingMemoryStore(BaseStore):
    def __init__(self, index: str):
        # index = (index, user_id)
        # key = session_id
        self.index = index
        self._backend = VikingDBLTMBackend(index=index)

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        # The batch/abatch methods are treated as internal.
        # Users should access via put/search/get/list_namespaces/etc.
        results = []
        for op in ops:
            if isinstance(op, PutOp):
                self._apply_put_op(op)
                results.append(None)
            elif isinstance(op, GetOp):
                results.append(self._apply_get_op(op))
            elif isinstance(op, SearchOp):
                results.append(self._apply_search_op(op))
            # elif isinstance(op, ListNamespacesOp):
            #     self._apply_list_namespaces_op(op)
            else:
                raise ValueError(f"Unknown op type: {type(op)}")

        return results

    def abatch(
        self, ops: Iterable[GetOp | SearchOp | PutOp | ListNamespacesOp]
    ) -> list[Result]: ...

    def _apply_put_op(self, op: PutOp) -> None:
        index, user_id = op.namespace
        session_id = op.key

        assert index == self._backend.index, (
            "index must be the same as the backend index"
        )

        value = op.value

        event_strings = []

        for _, event in value.items():
            event_strings.append(json.dumps(event))

        if self._backend.save_memory(
            user_id=user_id,
            session_id=session_id,
            event_strings=event_strings,
        ):
            return None

    def _apply_get_op(self, op: GetOp):
        return ["Not implemented"]

    def _apply_search_op(self, op: SearchOp):
        index, user_id = op.namespace_prefix
        assert index == self._backend.index, (
            "index must be the same as the backend index"
        )

        query = op.query
        if not query:
            return []

        value = self._backend.search_memory(
            user_id=user_id, query=query, top_k=op.limit or 1
        )
        return value
