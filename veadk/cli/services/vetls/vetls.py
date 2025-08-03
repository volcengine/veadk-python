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

from __future__ import absolute_import, division, print_function

import ast
import json
from collections import defaultdict
from datetime import datetime, timedelta

from volcengine.tls.tls_requests import SearchLogsRequest
from volcengine.tls.TLSService import TLSService

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class VeTLS:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        dump_path: str,
        endpoint: str = "https://tls-cn-beijing.volces.com",
        region: str = "cn-beijing",
    ):
        self.client = TLSService(endpoint, access_key, secret_key, region)
        self.dump_path: str = dump_path

    def query(self, topic_id: str, query: str):
        logger.warning("Currently, we only search the logs in the last 24 hours.")
        now = datetime.now()
        one_day_ago = now - timedelta(days=1)
        one_day_ago = int(one_day_ago.timestamp() * 1000)
        now = int(now.timestamp() * 1000)

        search_logs_request = SearchLogsRequest(
            topic_id=topic_id,
            query=query,
            limit=100,
            start_time=one_day_ago,
            end_time=now,
        )

        search_logs_response = self.client.search_logs_v2(search_logs_request)
        log_str_list = search_logs_response.get_search_result().get_logs()
        log_dict_list = []
        for log in log_str_list:
            # message: str -> dict
            message = ast.literal_eval(log["message"])
            trace_id = log.get("trace_id")
            log_dict_list.append(
                {
                    "trace_id": trace_id,
                    "message": message,
                }
            )
        log_dict_list = log_dict_list[::-1]

        # 创建一个默认为 list 的字典来聚合
        grouped = defaultdict(list)

        # 遍历原始数据，按 key 分组
        for item in log_dict_list:
            grouped[item["trace_id"]].append(item["message"])
        result = [{"trace_id": k, "data": v} for k, v in grouped.items()]

        self.dump_to_file(result)

    def dump_to_file(self, logs: list[dict]):
        with open(f"{self.dump_path}/logs.json", "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=4)
        logger.info(f"VeTLS dumps log list to {self.dump_path}/logs.json")
        logger.info(f"VeTLS dumps log list to {self.dump_path}/logs.json")
        logger.info(f"VeTLS dumps log list to {self.dump_path}/logs.json")
