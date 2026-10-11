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

"""Expose CI failure locations without publishing assertion payloads or secrets."""

import importlib.metadata
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


def failure_locations(report: Path) -> list[str]:
    if not report.exists():
        return ["JUnit report unavailable; check the preceding installation/test step."]
    locations = []
    for case in ET.parse(report).getroot().iter("testcase"):
        failure = next((x for x in case if x.tag in {"failure", "error"}), None)
        if failure is None:
            continue
        # Test parameters and assertion text can contain credentials or prompts.
        # Publish only Python identifiers and repository test source locations.
        name = case.get("name", "").split("[", 1)[0]
        name = name if re.fullmatch(r"[a-zA-Z_][a-zA-Z_0-9]*", name) else "collection"
        classname = case.get("classname", "")
        classname = (
            classname
            if re.fullmatch(r"[a-zA-Z_][a-zA-Z_0-9.]*", classname)
            else "tests"
        )
        source = re.findall(
            r"^(tests/[a-zA-Z_0-9/]+\.py):(\d+):", failure.text or "", re.MULTILINE
        )
        suffix = f" at {source[-1][0]}:{source[-1][1]}" if source else ""
        locations.append(f"{classname}.{name}{suffix}")
    return locations


def main() -> None:
    packages = [
        "google-adk",
        "litellm",
        "google-genai",
        "pydantic",
        "pytest",
        "pytest-asyncio",
        "sqlalchemy",
        "aiosqlite",
        "agentkit-sdk-python",
        "opentelemetry-sdk",
    ]
    versions = []
    for name in packages:
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            version = "missing"
        if re.fullmatch(r"[a-zA-Z0-9._+!-]+", version):
            versions.append(f"{name}={version}")
    print("::notice title=Dependency versions::" + "; ".join(versions))
    for location in failure_locations(Path(sys.argv[1]))[:30]:
        print("::error title=Pytest failure location::" + location)


if __name__ == "__main__":
    main()
