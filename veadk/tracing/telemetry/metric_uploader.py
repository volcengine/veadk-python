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

from __future__ import annotations

from collections.abc import Callable, Hashable
from threading import RLock
from typing import Any, Protocol

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class MetricUploader(Protocol):
    """Interface implemented by exporter-specific metric uploaders."""

    @property
    def registration_key(self) -> Hashable:
        """Return a stable, non-logged key for one metric destination."""

    def record_call_llm(self, *args: Any) -> None: ...

    def record_tool_call(self, *args: Any) -> None: ...

    def record_skill_call(self, *args: Any) -> None: ...

    def force_flush(self) -> bool: ...

    def shutdown(self) -> None: ...


class MetricUploaderRegistry:
    """Process-level registry for active metric destinations.

    Uploaders are deduplicated by their registration key. Different keys remain
    active together, so one process can intentionally publish metrics to more
    than one destination without repeatedly scanning tracers and exporters.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._uploaders: dict[Hashable, MetricUploader] = {}

    @property
    def uploaders(self) -> tuple[MetricUploader, ...]:
        with self._lock:
            return tuple(self._uploaders.values())

    def get(self, registration_key: Hashable) -> MetricUploader | None:
        with self._lock:
            return self._uploaders.get(registration_key)

    def get_or_create(
        self,
        registration_key: Hashable,
        factory: Callable[[], MetricUploader],
    ) -> MetricUploader:
        """Return the registered uploader, constructing it only when absent."""
        with self._lock:
            uploader = self._uploaders.get(registration_key)
            if uploader is None:
                uploader = factory()
                self._uploaders[registration_key] = uploader
                logger.debug(
                    "Registered metric uploader `%s`.",
                    uploader.__class__.__name__,
                )
            return uploader

    def register(self, uploader: MetricUploader) -> MetricUploader:
        """Register an uploader, closing a duplicate instance if necessary."""
        with self._lock:
            existing = self._uploaders.get(uploader.registration_key)
            if existing is None:
                self._uploaders[uploader.registration_key] = uploader
                logger.debug(
                    "Registered metric uploader `%s`.",
                    uploader.__class__.__name__,
                )
                return uploader

        if existing is not uploader:
            uploader.shutdown()
        return existing

    def record_call_llm(self, *args: Any) -> None:
        self._fan_out("record_call_llm", *args)

    def record_tool_call(self, *args: Any) -> None:
        self._fan_out("record_tool_call", *args)

    def record_skill_call(self, *args: Any) -> None:
        self._fan_out("record_skill_call", *args)

    def force_flush(self) -> bool:
        flushed = True
        for uploader in self.uploaders:
            try:
                flushed = bool(uploader.force_flush()) and flushed
            except Exception as e:
                flushed = False
                logger.warning(
                    "Failed to flush metric uploader `%s`: %s",
                    uploader.__class__.__name__,
                    e,
                )
        return flushed

    def clear(self, *, shutdown: bool = True) -> None:
        """Remove all uploaders, optionally shutting down their SDK providers."""
        with self._lock:
            uploaders = tuple(self._uploaders.values())
            self._uploaders.clear()

        if shutdown:
            for uploader in uploaders:
                try:
                    uploader.shutdown()
                except Exception as e:
                    logger.warning(
                        "Failed to shut down metric uploader `%s`: %s",
                        uploader.__class__.__name__,
                        e,
                    )

    def _fan_out(self, method_name: str, *args: Any) -> None:
        for uploader in self.uploaders:
            try:
                getattr(uploader, method_name)(*args)
            except Exception as e:
                logger.warning(
                    "Metric uploader `%s` failed in %s: %s",
                    uploader.__class__.__name__,
                    method_name,
                    e,
                )


metric_uploader_registry = MetricUploaderRegistry()
