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

from abc import ABC, abstractmethod

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class BaseTracer(ABC):
    """Abstract base class for implementing tracing functionality in VeADK agents.

    BaseTracer provides the foundation for collecting, managing, and exporting
    trace data from agent execution sessions. It defines the interface that all
    concrete tracer implementations must follow, enabling pluggable tracing
    backends for different observability platforms.

    Attributes:
        name: Unique identifier for this tracer instance
        _trace_id: Internal trace identifier for current execution context
        _trace_file_path: Path to the current trace data file
    """

    def __init__(self, name: str):
        """Initialize a new BaseTracer instance.

        Args:
            name: Unique identifier for this tracer instance.
        """
        self.name = name
        self._trace_id = "<unknown_trace_id>"
        self._trace_file_path = "<unknown_trace_file_path>"

    @abstractmethod
    def dump(self, user_id: str, session_id: str, path: str = "/tmp") -> str:
        """Dump the collected trace data to a local file.

        This method must be implemented by concrete tracer classes to export
        trace data in a format suitable for analysis or storage.

        Args:
            user_id: User identifier for trace organization and file naming
            session_id: Session identifier for filtering and organizing spans
            path: Directory path for the output file. Defaults to system temp directory
        """
        ...
