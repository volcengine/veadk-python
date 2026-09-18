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

from io import StringIO

import pytest

from veadk.integrations.ve_faas.upload_progress import CodeUploadProgress


@pytest.mark.parametrize("terminal", [True, False])
def test_upload_progress_displays_rate_size_eta_and_waits_for_response(
    monkeypatch: pytest.MonkeyPatch, terminal: bool
) -> None:
    output = StringIO()
    monkeypatch.setattr(output, "isatty", lambda: terminal)
    monkeypatch.setattr("sys.stderr", output)
    clock = [100.0]
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.upload_progress.time.monotonic", lambda: clock[0]
    )

    with CodeUploadProgress(b"x" * 1024**2) as body:
        chunks = iter(body)
        assert len(next(chunks)) == 64 * 1024
        assert body.uploaded == 0  # A yielded chunk has not been sent yet
        clock[0] += 5
        next(chunks)
        assert body.uploaded == 64 * 1024
        line = output.getvalue().split("\r" if terminal else "\n")[
            -1 if terminal else -2
        ]
        assert "6%" in line
        assert "0.06 / 1.00 MB" in line
        assert "0.01 MB/s" in line
        assert "ETA 01:15" in line
        for _chunk in chunks:
            clock[0] += 0.1
        assert body.uploaded == len(body)
        assert "Waiting for response" in output.getvalue()
        assert "Uploaded code" not in output.getvalue()
    assert "Uploaded code" in output.getvalue()
    assert "100%" in output.getvalue()
    assert output.getvalue().endswith("\n")
    assert ("\r" in output.getvalue()) == terminal


def test_upload_progress_throttles_redirected_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = StringIO()
    monkeypatch.setattr("sys.stderr", output)
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.upload_progress.time.monotonic", lambda: 100.0
    )
    with CodeUploadProgress(b"x" * 1024**2) as body:
        assert b"".join(body) == body.data
    lines = output.getvalue().splitlines()
    assert len(lines) == 3
    assert "Uploading code" in lines[0]
    assert "Waiting for response" in lines[1]
    assert "Uploaded code" in lines[2]


def test_upload_progress_can_replay_body_after_http_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = StringIO()
    monkeypatch.setattr("sys.stderr", output)
    with CodeUploadProgress(b"x" * 150_000) as body:
        assert b"".join(body) == body.data
        assert b"".join(body) == body.data
        assert body.uploaded == len(body)
    assert "200%" not in output.getvalue()


def test_upload_progress_output_failure_does_not_interrupt_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = StringIO()
    monkeypatch.setattr("sys.stderr", output)
    body = CodeUploadProgress(b"archive")
    output.close()
    with body:
        assert b"".join(body) == b"archive"


@pytest.mark.parametrize(
    "error", [RuntimeError("connection lost"), KeyboardInterrupt()]
)
def test_upload_progress_finishes_failed_line_and_preserves_error(
    monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    output = StringIO()
    monkeypatch.setattr(output, "isatty", lambda: True)
    monkeypatch.setattr("sys.stderr", output)
    with pytest.raises(type(error)):
        with CodeUploadProgress(b"archive", 2, 2):
            raise error
    assert "(2/2)" in output.getvalue()
    assert "Upload failed" in output.getvalue()
    assert "Uploaded code" not in output.getvalue()
    assert output.getvalue().endswith("\n")
