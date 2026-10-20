#!/usr/bin/env python3
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

"""Configure only the base Ubuntu archive URLs, without changing suites or signing."""

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

mirror = sys.argv[1].rstrip("/")
parsed = urlsplit(mirror)
if (
    parsed.scheme != "https"
    or not parsed.hostname
    or parsed.username
    or parsed.password
    or parsed.query
    or parsed.fragment
):
    raise ValueError(
        "APT mirror must be an HTTPS URL without credentials or query parameters"
    )
source = Path("/etc/apt/sources.list")
content = source.read_text()
updated, count = re.subn(
    r"https?://(?:archive|security)\.ubuntu\.com/ubuntu/?", mirror, content
)
if count == 0:
    raise ValueError(
        "Base APT sources changed; review mirror configuration before building"
    )
source.write_text(updated)
