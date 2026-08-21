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

from frontend.service.studio_scheduler.diagnostics import sanitize_diagnostic


def test_sanitize_diagnostic_redacts_quoted_json_secrets() -> None:
    diagnostic = sanitize_diagnostic(
        '{"token":"top-secret","api_key": "another-secret","detail":"safe"}'
    )

    assert diagnostic == (
        '{"token":"[REDACTED]","api_key": "[REDACTED]","detail":"safe"}'
    )
    assert "top-secret" not in diagnostic
    assert "another-secret" not in diagnostic
