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

import click
import json
import requests
from veadk.utils.logger import get_logger
from veadk.config import getenv
from pathlib import Path

logger = get_logger(__name__)


@click.command()
@click.option("--file", required=True, help="JSON file path containing dataset items")
@click.option("--cozeloop-workspace-id", default=None, help="CozeLoop workspace ID")
@click.option("--cozeloop-evalset-id", default=None, help="CozeLoop evaluation set ID")
@click.option(
    "--cozeloop-api-key",
    default=None,
    help="CozeLoop API key (or set COZELOOP_API_KEY env var)",
)
def uploadevalset(
    file: str,
    cozeloop_workspace_id: str,
    cozeloop_evalset_id: str,
    cozeloop_api_key: str,
) -> None:
    """Upload dataset items to CozeLoop evaluation set.

    This command uploads evaluation dataset items from a JSON file to the CozeLoop
    platform for agent evaluation and testing. It processes Google ADK formatted
    evaluation cases and converts them to CozeLoop's expected format.

    Args:
        file: Path to the JSON file containing dataset items in Google ADK format.
        cozeloop_workspace_id: CozeLoop workspace identifier for organizing evaluation sets.
            If not provided, uses OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME environment variable.
        cozeloop_evalset_id: Specific evaluation set ID where items will be uploaded.
            If not provided, uses OBSERVABILITY_OPENTELEMETRY_COZELOOP_EVALSET_ID environment variable.
        cozeloop_api_key: API key for authenticating with CozeLoop services.
            If not provided, uses OBSERVABILITY_OPENTELEMETRY_COZELOOP_API_KEY environment variable.
    """

    if not cozeloop_workspace_id:
        cozeloop_workspace_id = getenv(
            "OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME"
        )
    if not cozeloop_evalset_id:
        cozeloop_evalset_id = getenv("OBSERVABILITY_OPENTELEMETRY_COZELOOP_EVALSET_ID")
    if not cozeloop_api_key:
        cozeloop_api_key = getenv("OBSERVABILITY_OPENTELEMETRY_COZELOOP_API_KEY")

    # Read JSON file
    file_path = Path(file)
    if not file_path.exists():
        logger.error(f"File not found: {file}")
        return

    logger.info(f"Reading dataset from {file}")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Prepare items
    items = []
    for case in data.get("eval_cases", []):
        conversation = case.get("conversation", [])
        for turn in conversation:
            user_text = (
                turn.get("user_content", {}).get("parts", [{}])[0].get("text", "")
            )
            output_text = (
                turn.get("final_response", {}).get("parts", [{}])[0].get("text", "")
            )

            items.append(
                {
                    "turns": [
                        {
                            "field_datas": [
                                {
                                    "name": "input",
                                    "content": {
                                        "content_type": "Text",
                                        "text": user_text,
                                    },
                                },
                                {
                                    "name": "output",
                                    "content": {
                                        "content_type": "Text",
                                        "text": output_text,
                                    },
                                },
                            ]
                        }
                    ]
                }
            )

    # Upload to CozeLoop
    url = f"https://api.coze.cn/v1/loop/evaluation/evaluation_sets/{cozeloop_evalset_id}/items"
    logger.info(
        f"Uploading {len(items)} items to workspace_id={cozeloop_workspace_id} evalset_id={cozeloop_evalset_id}"
    )

    response = requests.post(
        url=url,
        headers={
            "Authorization": f"Bearer {cozeloop_api_key}",
            "Content-Type": "application/json",
            "X-TT-ENV": "ppe_eval_openapi",
            "x-use-ppe": "1",
        },
        json={
            "workspace_id": cozeloop_workspace_id,
            "is_allow_partial_add": True,
            "is_skip_invalid_items": True,
            "items": items,
        },
    )

    if response.status_code == 200:
        logger.info(
            f"Successfully uploaded dataset to CozeLoop evalset {cozeloop_evalset_id}"
        )
    else:
        logger.error(f"Failed to upload dataset: {response.text}")
