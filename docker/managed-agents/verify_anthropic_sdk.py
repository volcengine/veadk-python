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

"""Check the installed SDK is unchanged from its hash-locked wheel RECORD.

The installer verifies the official artifact hash from uv.lock. This separate
check rejects changed, missing or overlaid Python files after installation; it
is not an independent trust root if RECORD itself has been replaced.
"""

import base64
import csv
import hashlib
import importlib.metadata
import io
from pathlib import PurePosixPath


def verify_distribution(distribution: importlib.metadata.Distribution) -> int:
    record = distribution.read_text("RECORD")
    if not record:
        raise RuntimeError("Anthropic SDK integrity: missing wheel RECORD")
    expected = set()
    for name, digest, _size in csv.reader(io.StringIO(record)):
        path = PurePosixPath(name)
        if not name.startswith("anthropic/") or path.suffix != ".py":
            continue
        if path.is_absolute() or ".." in path.parts or not digest.startswith("sha256="):
            raise RuntimeError("Anthropic SDK integrity: invalid Python file record")
        installed = distribution.locate_file(name)
        if not installed.is_file() or installed.is_symlink():
            raise RuntimeError(f"Anthropic SDK integrity: missing or linked {name}")
        actual = (
            base64.urlsafe_b64encode(hashlib.sha256(installed.read_bytes()).digest())
            .decode()
            .rstrip("=")
        )
        if actual != digest.removeprefix("sha256="):
            raise RuntimeError(f"Anthropic SDK integrity: modified {name}")
        expected.add(installed)
    if not expected:
        raise RuntimeError("Anthropic SDK integrity: no recorded Python files")
    actual_files = set(distribution.locate_file("anthropic").rglob("*.py"))
    if actual_files != expected:
        raise RuntimeError("Anthropic SDK integrity: unrecorded Python files")
    return len(expected)


if __name__ == "__main__":
    sdk = importlib.metadata.distribution("anthropic")
    count = verify_distribution(sdk)
    print(
        f"Official Anthropic SDK {sdk.version}: {count} Python files match wheel RECORD"
    )
