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

import sys

from loguru import logger
from opentelemetry import trace

from veadk.utils.misc import getenv


def filter_log():
    import logging
    import warnings

    from urllib3.exceptions import InsecureRequestWarning

    # ignore all warnings
    warnings.filterwarnings("ignore")

    # ignore UserWarning
    warnings.filterwarnings(
        "ignore", category=UserWarning, module="opensearchpy.connection.http_urllib3"
    )

    # ignore InsecureRequestWarning
    warnings.filterwarnings("ignore", category=InsecureRequestWarning)

    # disable logs
    logging.basicConfig(level=logging.ERROR)


def setup_logger():
    logger.remove()

    def format_with_traceid(record):
        span = trace.get_current_span()
        trace_id_part = ""
        if span.is_recording():
            trace_id_part = (
                f" | trace_id={format(span.get_span_context().trace_id, '016x')}"
            )

        base_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{file}:{line}</cyan>"
        message_part = " - {message}\n{exception}"

        return base_format + trace_id_part + message_part

    logger.add(
        sys.stdout,
        format=format_with_traceid,
        colorize=True,
        level=getenv("LOGGING_LEVEL", "DEBUG"),
    )
    return logger


filter_log()
setup_logger()


def get_logger(name: str):
    return logger.bind(name=name)
