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

from ark_sdk.resources.pipeline_plugin.test_instance import (
    get_or_create_pipeline_plugin_test_instance,
)
from ark_sdk.types.pipeline_plugin.rollout import (
    ChatCompletionSample,
)
from plugins.async_weather_rollout import demo_rollout
from ark_sdk.core.plugin.rollout.proxy import InferenceProxy, Mode

if __name__ == "__main__":
    instance = get_or_create_pipeline_plugin_test_instance(demo_rollout)
    base_url = ""
    api_key = ""

    sample = ChatCompletionSample(
        **{
            "model": "doubao-seed-1-6-flash-250615",
            "messages": [
                {
                    "role": "user",
                    "content": "北京天气",
                }
            ],
        }
    )
    proxy = InferenceProxy(sample, url=base_url, jwt_token=api_key, mode=Mode.Inference)
    proxy.headers = {"test-header-zql": "test-value-zql"}
    resp = instance.request(
        {
            "context": {},
            "proxy": proxy,
            "sample": sample,
        },
        # sync 为false时不会创建新的faas函数（不会更新代码）
        sync=True,
    )
    print(resp)
