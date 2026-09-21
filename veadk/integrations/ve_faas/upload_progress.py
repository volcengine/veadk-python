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

import math
import shutil
import sys
import time
from collections import deque
from collections.abc import Iterator
from types import TracebackType


class CodeUploadProgress:
    """A sized HTTP body that reports bytes sent without copying the archive.

    Advance after each yielded chunk has been sent by the HTTP client. Completion
    is reported only when the caller exits successfully after checking the response.
    """

    def __init__(self, data: bytes, attempt: int = 1, attempts: int = 1) -> None:
        self.data = data
        self.uploaded = 0
        self.output = sys.stderr
        self.terminal = self.output.isatty()
        self.label = "Uploading code"
        if attempts > 1:
            self.label += f" ({attempt}/{attempts})"
        self.samples: deque[tuple[float, int]] = deque()
        self.last_render = 0.0
        self.line_width = 0

    def __len__(self) -> int:
        # requests uses this to retain Content-Length instead of chunked encoding.
        return len(self.data)

    def __enter__(self) -> "CodeUploadProgress":
        self.samples.append((time.monotonic(), 0))
        self._render(force=True)
        return self

    def __iter__(self) -> Iterator[bytes]:
        # requests can replay a PUT body when following a 307/308 redirect.
        if self.uploaded:
            self.uploaded = 0
            self.samples.clear()
            self.samples.append((time.monotonic(), 0))
            self._render(force=True)
        for offset in range(0, len(self), 64 * 1024):
            chunk = self.data[offset : offset + 64 * 1024]
            yield chunk
            self.uploaded += len(chunk)
            self._render()
        self._render(status="Waiting for response", force=True)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._render(
            status="Upload failed" if exc_type else "Uploaded code",
            force=True,
            final=True,
        )

    def _render(
        self, *, status: str = "", force: bool = False, final: bool = False
    ) -> None:
        now = time.monotonic()
        interval = 0.2 if self.terminal else 5.0
        if not force and now - self.last_render < interval:
            return
        self.last_render = now
        self.samples.append((now, self.uploaded))
        while len(self.samples) > 2 and self.samples[1][0] < now - 5:
            self.samples.popleft()
        started, previous = self.samples[0]
        speed = (self.uploaded - previous) / max(now - started, 0.001)
        remaining = max(0, len(self) - self.uploaded)
        eta = "--:--"
        if speed > 0:
            minutes, seconds = divmod(math.ceil(remaining / speed), 60)
            eta = f"{minutes:02d}:{seconds:02d}"
        fraction = self.uploaded / len(self) if len(self) else 0.0
        details = (
            f" {fraction:4.0%}  {self.uploaded / 1024**2:.2f} /"
            f" {len(self) / 1024**2:.2f} MB  {speed / 1024**2:.2f} MB/s"
            f"  ETA {eta}"
        )
        label = status or self.label
        width = shutil.get_terminal_size().columns
        bar_width = max(1, min(20, width - len(label) - len(details) - 4))
        filled = int(bar_width * fraction)
        bar = "#" * filled + "-" * (bar_width - filled)
        line = f"{label} [{bar}]{details}"
        try:
            if self.terminal:
                print(
                    "\r" + line.ljust(self.line_width),
                    end="\n" if final else "",
                    file=self.output,
                    flush=True,
                )
                self.line_width = len(line)
            else:
                print(line, file=self.output, flush=True)
        except (OSError, ValueError):
            # A closed output stream must not interrupt an otherwise valid upload.
            pass
