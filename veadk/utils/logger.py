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

import logging
import sys

from opentelemetry import trace

from veadk.utils.misc import getenv

_LOGGER_NAME = "veadk"

# ANSI escape codes, matching the colors loguru used by default.
_RESET = "\033[0m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_LEVEL_COLORS = {
    "DEBUG": "\033[34m",  # blue
    "INFO": "\033[1m",  # bold
    "WARNING": "\033[33m",  # yellow
    "ERROR": "\033[31m",  # red
    "CRITICAL": "\033[1m\033[31m",  # bold red
}


class _VeADKFormatter(logging.Formatter):
    def __init__(self, colorize: bool) -> None:
        super().__init__(datefmt="%Y-%m-%d %H:%M:%S")
        self._colorize = colorize

    def format(self, record: logging.LogRecord) -> str:
        time_str = self.formatTime(record, self.datefmt)
        level = record.levelname
        location = f"{record.filename}:{record.lineno}"
        message = record.getMessage()

        span = trace.get_current_span()
        trace_id_part = ""
        if span.is_recording():
            trace_id_part = (
                f" | trace_id={format(span.get_span_context().trace_id, '016x')}"
            )

        if self._colorize:
            time_str = f"{_GREEN}{time_str}{_RESET}"
            level = f"{_LEVEL_COLORS.get(level, '')}{level}{_RESET}"
            location = f"{_CYAN}{location}{_RESET}"

        line = f"{time_str} | {level} | {location}{trace_id_part} - {message}"

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def filter_log():
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
    root = logging.getLogger(_LOGGER_NAME)

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_VeADKFormatter(colorize=sys.stdout.isatty()))
    root.addHandler(handler)
    root.setLevel(getenv("LOGGING_LEVEL", "DEBUG"))

    # keep veadk logs on their own handler, do not bubble up to the root logger
    root.propagate = False
    return root


filter_log()
setup_logger()


def get_logger(name: str) -> logging.Logger:
    # anchor every logger under the veadk namespace so it inherits the handler
    # and level configured above, regardless of the caller's module name
    if name == _LOGGER_NAME or name.startswith(f"{_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
