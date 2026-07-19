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

from veadk.cli.cli_frontend import _extract_build_error_excerpt


def test_extract_build_error_excerpt_keeps_dependency_resolution_cause() -> None:
    lines = [
        "#10 0.1 Using Python 3.12",
        "\x1b[31m× No solution found when resolving dependencies:\x1b[0m",
        "╰─▶ Because only veadk-python<=1.0.4 is available",
        "    and you require veadk-python>=1.0.5,",
        "    your requirements are unsatisfiable.",
        "#10 ERROR: process did not complete successfully",
    ]

    excerpt = _extract_build_error_excerpt(lines)

    assert "\x1b" not in excerpt
    assert "veadk-python<=1.0.4" in excerpt
    assert "veadk-python>=1.0.5" in excerpt
    assert "requirements are unsatisfiable" in excerpt


def test_extract_build_error_excerpt_removes_credentials() -> None:
    lines = [
        "VOLCENGINE_ACCESS_KEY=temporary-access-key",
        "VOLCENGINE_SECRET_KEY=temporary-secret-key",
        "Authorization: Bearer temporary.jwt.token",
        "X-Tos-Security-Token=temporary-session-token",
        "CR_TOKEN=temporary-registry-token",
        "API_KEY=temporary-api-key",
        "No solution found when resolving dependencies:",
        "Because only veadk-python<=1.0.4 is available",
        "and you require veadk-python>=1.0.5",
        "docker login --password temporary-registry-token registry.example.com",
    ]

    excerpt = _extract_build_error_excerpt(lines)

    assert "temporary" not in excerpt
    assert "veadk-python>=1.0.5" in excerpt


def test_extract_build_error_excerpt_ignores_successful_logs() -> None:
    lines = [
        "Step 1/2: Building image",
        "Successfully built image",
        "Step 2/2: Deploying service",
        "Runtime status: Ready",
    ]

    assert _extract_build_error_excerpt(lines) == ""
