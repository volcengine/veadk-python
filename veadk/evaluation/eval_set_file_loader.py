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

from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.local_eval_sets_manager import (
    load_eval_set_from_file as adk_load_eval_set_from_file,
)


def load_eval_set_from_file(eval_set_file_path: str) -> EvalSet:
    try:
        eval_set = adk_load_eval_set_from_file(eval_set_file_path, eval_set_file_path)
    except Exception as e:
        raise Exception(
            f"Failed to load eval set from file {eval_set_file_path}"
        ) from e
    return eval_set
