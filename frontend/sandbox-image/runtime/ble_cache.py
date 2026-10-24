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

"""Backport process-specific Readline cache files to the pinned ble.sh release."""

import os
import stat
import tempfile
from pathlib import Path


def patch_blesh(path: Path) -> None:
    content = path.read_text()
    before, start, tail = content.partition(
        "function ble/builtin/bind/read-user-settings/.collect {\n"
    )
    body, end, after = tail.partition("\n}\n")
    old, new = '"$cache.part"', '"$cache.$$.part"'
    if not start or not end:
        raise ValueError("Pinned ble.sh Readline cache function changed")
    if body.count(new) == 2 and old not in body:
        return
    if body.count(old) != 2 or new in body:
        raise ValueError("Pinned ble.sh Readline cache writer changed")
    # $$ stays identical in the pipeline writer and the following mv process.
    updated = before + start + body.replace(old, new) + end + after
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(updated)
            output.flush()
            os.fchmod(output.fileno(), stat.S_IMODE(path.stat().st_mode))
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
