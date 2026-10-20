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

"""Save session artifacts through Studio's existing storage"""

from frontend.server.runtime_artifacts.writer import (
    ARTIFACT_WRITE_MAX_BYTES,
    StudioArtifactWriter,
)
from frontend.server.studio_tools.registry import StudioTool, StudioToolRegistry


def register_tools(registry: StudioToolRegistry) -> None:
    writer = StudioArtifactWriter.from_env()
    registry.register(
        StudioTool(
            name="studio_write_artifact",
            display_name="保存会话产物",
            description=(
                "Save a UTF-8 text file (HTML, SVG, Markdown, JSON, CSV, or code) "
                "as an artifact of the current Studio conversation. Studio "
                "automatically selects the current user's session directory. "
                "Use a relative path such as report/index.html; sibling assets "
                "can use relative links. The file appears in the session artifact "
                "explorer and preview. Writing the same path replaces its content. "
                "Maximum file size is 1 MiB. Use this tool to deliver files instead "
                "of writing to the Runtime filesystem."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 1024,
                        "description": "Relative filename within this session",
                    },
                    "content": {
                        "type": "string",
                        "maxLength": ARTIFACT_WRITE_MAX_BYTES,
                        "description": "Complete UTF-8 text content of the file",
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            executor=writer.write,
            executor_revision="studio-artifacts-v1",
            requires_context=True,
            risk_level="low",
        )
    )
