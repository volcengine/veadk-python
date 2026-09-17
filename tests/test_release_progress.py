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

import json
from io import BytesIO

import pytest

from veadk.integrations.ve_faas import release_progress
from veadk.integrations.ve_faas.release_progress import ReleaseProgress
from veadk.integrations.ve_faas.ve_faas import VeFaaS


@pytest.fixture
def progress(monkeypatch: pytest.MonkeyPatch):
    clock = [0.0]
    messages = []
    monkeypatch.setattr(release_progress.time, "monotonic", lambda: clock[0])
    reporter = ReleaseProgress(
        provider="volcengine",
        region="cn-beijing",
        app_id="app-id",
        secrets=("private-access-key", "private-secret-key"),
        emit=messages.append,
    )
    return reporter, messages, clock


def test_progress_shows_stage_and_elapsed_when_logs_are_quiet(progress) -> None:
    reporter, messages, clock = progress
    reporter.status("deploying", 9)
    reporter.logs(["[function][fn-id][install][Info] installing dependencies"])
    count = len(messages)
    clock[0] = 14
    reporter.waiting()
    assert len(messages) == count
    clock[0] = 15
    reporter.waiting()
    assert "安装依赖" in messages[-1]
    assert "00:15" in messages[-1]
    assert "暂无新日志" in messages[-1]
    reporter.status("deploying", 9)
    assert len(messages) == count + 1


def test_progress_only_prints_new_lines_in_growing_and_rolling_logs(progress) -> None:
    reporter, messages, _ = progress
    reporter.logs(["first", "second"])
    reporter.logs(["first", "second", "third"])
    reporter.logs(["first", "second"])  # Ignore a stale shorter snapshot
    reporter.logs([])  # A temporarily empty response must not erase the cursor
    reporter.logs(["second", "third", "fourth"])
    reporter.logs(["second", "third", "fourth"])
    assert [line for line in messages if line.startswith("[发布日志]")] == [
        "[发布日志] first",
        "[发布日志] second",
        "[发布日志] third",
        "[发布日志] fourth",
    ]


def test_build_logs_retry_grow_and_refresh_signed_url_without_duplicate_output(
    progress,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reporter, messages, _ = progress
    contents = iter(
        [
            OSError("not ready"),
            ("step one\npartial", False),
            ("step one\npartial line\n", False),
        ]
    )
    urls = []

    def read(url):
        urls.append(url)
        result = next(contents)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(release_progress, "_read_build_log", read)
    old_url = "https://build.example/step.log?signature=old-secret"
    new_url = "https://build.example/step.log?signature=new-secret"
    reporter.logs([old_url])
    reporter.logs([old_url])
    reporter.logs([new_url], final=True)
    assert urls == [old_url, old_url, new_url]
    assert messages.count("[构建日志] step one") == 1
    assert messages.count("[构建日志] partial line") == 1
    assert "[构建日志] partial" not in messages
    assert "new-secret" not in "\n".join(messages)
    assert "old-secret" not in "\n".join(messages)
    assert sum(message.startswith("[发布日志]") for message in messages) == 1


def test_progress_redacts_credentials_and_signed_queries(progress) -> None:
    reporter, messages, _ = progress
    reporter.logs(
        [
            "private-access-key private-secret-key token=dynamic-secret",
            '"api_key": "json-secret" Authorization: Bearer bearer-secret',
            "https://example.com/resource?X-Tos-Signature=signed-secret",
        ]
    )
    output = "\n".join(messages)
    for secret in (
        "private-access-key",
        "private-secret-key",
        "dynamic-secret",
        "json-secret",
        "bearer-secret",
        "signed-secret",
    ):
        assert secret not in output


@pytest.mark.parametrize("content_range", ["bytes 100-125/126", ""])
def test_build_log_reader_bounds_download_and_handles_partial_utf8(
    monkeypatch: pytest.MonkeyPatch,
    content_range: str,
) -> None:
    requests = []

    class Response(BytesIO):
        headers = {"Content-Range": content_range}

    def open_url(request, timeout):
        requests.append((request, timeout))
        return Response(b"\x80partial\ncomplete line\n")

    monkeypatch.setattr(release_progress.urllib.request, "urlopen", open_url)
    text, truncated = release_progress._read_build_log("https://build.example/step.log")
    if content_range:
        assert text == "complete line\n"
    assert not truncated
    assert requests[0][0].get_header("Range") == "bytes=-262144"
    assert requests[0][1] == 3


def test_build_log_reader_handles_servers_ignoring_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response(BytesIO):
        headers = {}

    monkeypatch.setattr(
        release_progress.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: Response(b"x" * 300_000),
    )
    text, truncated = release_progress._read_build_log("https://build.example/step.log")
    assert len(text) == 256 * 1024
    assert truncated


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_release_streams_current_revision_logs_and_final_lines(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    service = object.__new__(VeFaaS)
    service.provider = provider
    service.region = "cn-beijing" if provider == "volcengine" else "ap-southeast-1"
    service.ak = "private-ak"
    service.sk = "private-sk"
    service.session_token = "private-sts"
    monkeypatch.setattr(
        service,
        "_start_application_release",
        lambda _: {"Result": {"RevisionNumber": 9}},
    )
    states = iter(["deploying", "deploying", "deploy_success"])
    monkeypatch.setattr(
        service,
        "_get_application_status",
        lambda _: (
            next(states),
            {
                "Result": {
                    "CloudResource": json.dumps(
                        {"framework": {"url": {"system_url": "https://studio.example"}}}
                    )
                }
            },
        ),
    )
    snapshots = iter(
        [["building"], ["building", "starting"], ["building", "starting", "ready"]]
    )
    revisions = []

    def logs(**kwargs):
        revisions.append(kwargs["revision_number"])
        assert kwargs["timeout"] == 5
        return next(snapshots)

    monkeypatch.setattr(service, "_get_application_logs", logs)
    messages = []
    delays = []
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.ve_faas.logger.info",
        lambda message, *_: messages.append(message),
    )
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.time.sleep", delays.append)
    assert service._release_application("app-id") == "https://studio.example"
    assert revisions == [9, 9, 9]
    assert delays == [3, 3]
    for line in ("building", "starting", "ready"):
        assert sum(message.endswith("] " + line) for message in messages) == 1
    assert "https://studio.example" in messages[-1]


def test_release_keeps_waiting_when_logs_unavailable_and_never_reads_old_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = object.__new__(VeFaaS)
    monkeypatch.setattr(service, "_start_application_release", lambda _: {})
    results = iter(
        [
            ("deploying", {"StableRevisionNumber": 7}),
            ("deploying", {"NewRevisionNumber": 8}),
            ("deploying", {"NewRevisionNumber": 8}),
            (
                "deploy_success",
                {
                    "NewRevisionNumber": 8,
                    "CloudResource": json.dumps(
                        {"framework": {"url": {"system_url": "https://studio.example"}}}
                    ),
                },
            ),
        ]
    )
    monkeypatch.setattr(
        service,
        "_get_application_status",
        lambda _: (lambda state: (state[0], {"Result": state[1]}))(next(results)),
    )
    revisions = []

    def logs(**kwargs):
        revisions.append(kwargs["revision_number"])
        raise RuntimeError("permission denied")

    monkeypatch.setattr(service, "_get_application_logs", logs)
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.time.sleep", lambda _: None)
    messages = []
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.ve_faas.logger.info", messages.append
    )
    assert service._release_application("app-id") == "https://studio.example"
    assert revisions == [8, 8, 8]
    assert sum("暂时无法读取云端日志" in message for message in messages) == 1


def test_failed_release_preserves_cloud_failure_when_log_request_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = object.__new__(VeFaaS)
    monkeypatch.setattr(
        service,
        "_start_application_release",
        lambda _: {"Result": {"RevisionNumber": 9}},
    )
    monkeypatch.setattr(
        service,
        "_get_application_status",
        lambda _: ("deploy_fail", {"Result": {"Message": "runtime failed to start"}}),
    )
    monkeypatch.setattr(
        service,
        "_get_application_logs",
        lambda **_: (_ for _ in ()).throw(RuntimeError("logs unavailable")),
    )
    with pytest.raises(Exception, match="runtime failed to start") as error:
        service._release_application("app-id")
    assert "未能读取最终发布日志" in str(error.value)
