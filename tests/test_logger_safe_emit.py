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

from veadk.utils import logger as logger_module


class _RaisingLogger:
    def info(self, message):
        raise RuntimeError("info failed")

    def warning(self, message):
        raise RuntimeError("warning failed")


def test_safe_info_swallows_logging_errors():
    logger_module.safe_info(_RaisingLogger(), "message")


def test_safe_warning_swallows_logging_errors():
    logger_module.safe_warning(_RaisingLogger(), "message")
