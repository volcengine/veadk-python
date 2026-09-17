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

"""Exercise the public tool interface and filesystem permission boundaries"""

import asyncio
import json
import os
import threading

import pytest

from veadk.tools.builtin_tools.bash_toolset import BashToolset

pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="BashToolset requires Linux or macOS",
)

_CONTENT = "hello world\nsecond line\nlast"
_CALLS = {
    "cat": {"path": "notes.txt"},
    "find": {"pattern": "*.txt"},
    "grep": {"pattern": "hello", "ignore_case": True},
    "ls": {},
    "pwd": {},
    "head": {"path": "notes.txt", "lines": 1},
    "tail": {"path": "notes.txt", "lines": 1},
    "wc": {"path": "notes.txt"},
    "stat": {"path": "notes.txt"},
    "diff": {"path_a": "notes.txt", "path_b": "changed.txt"},
}


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path.resolve() / "workspace"
    root.mkdir()
    (root / "notes.txt").write_text(_CONTENT, encoding="utf-8")
    (root / "changed.txt").write_text("hello world\nupdated\nlast", encoding="utf-8")
    (root / ".env").write_text("private fixture", encoding="utf-8")
    (root / "nested").mkdir()
    (root / "nested" / "notes.txt").write_text("HELLO nested\n", encoding="utf-8")
    (root.parent / "outside.txt").write_text("outside fixture", encoding="utf-8")
    (root / "escape").symlink_to(root.parent / "outside.txt")
    (root / "env-alias").symlink_to(root / ".env")
    (root / "safe-alias").symlink_to(root / "notes.txt")
    return root


@pytest.mark.asyncio
async def test_all_tools_through_adk(workspace):
    toolset = BashToolset(workspace)
    tools = await toolset.get_tools()
    assert {tool.name for tool in tools} == set(_CALLS)
    results = {}
    for tool in tools:
        declaration = tool._get_declaration()
        assert declaration.name == tool.name
        result = await tool.run_async(args=_CALLS[tool.name], tool_context=None)
        assert result["error"] is None, (tool.name, result)
        assert result["truncated"] is False
        results[tool.name] = result["output"]
    assert results["cat"] == _CONTENT
    assert results["pwd"] == f"{workspace}\n"
    assert results["head"] == "hello world\n"
    assert results["tail"] == "last"
    assert json.loads(results["wc"]) == {"lines": 2, "words": 5, "bytes": 28}
    assert json.loads(results["stat"])["size_bytes"] == 28
    assert f"{workspace / 'nested' / 'notes.txt'}:1:HELLO nested" in results["grep"]
    assert str(workspace / "nested" / "notes.txt") in results["find"]
    assert str(workspace / "nested" / "notes.txt") not in results["ls"]
    assert "-second line\n+updated\n" in results["diff"]
    await toolset.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", _CALLS)
async def test_disabled_tools_cannot_be_called_directly(workspace, name):
    toolset = BashToolset(workspace, allowed_tools=[])
    assert await toolset.get_tools() == []
    result = await getattr(toolset, name)(**_CALLS[name])
    assert "disabled" in result["error"]
    assert result["output"] == ""


@pytest.mark.asyncio
async def test_constructor_copies_permissions_and_supports_multiple_roots(workspace):
    extra = workspace.parent / "extra"
    extra.mkdir()
    (extra / "notes.txt").write_text("second root", encoding="utf-8")
    names, roots, patterns = ["cat"], [workspace, extra], [".env"]
    toolset = BashToolset(
        workspace,
        allowed_tools=names,
        allowed_directories=roots,
        exclude_patterns=patterns,
    )
    names.clear()
    roots.clear()
    patterns.clear()
    assert [tool.name for tool in await toolset.get_tools()] == ["cat"]
    assert (await toolset.cat(str(extra / "notes.txt")))["output"] == "second root"
    assert (await toolset.cat(".env"))["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [".env", "../outside.txt", "escape", "env-alias"])
@pytest.mark.parametrize("name", ["cat", "grep", "head", "tail", "wc", "stat", "diff"])
async def test_content_and_metadata_tools_enforce_permissions(workspace, path, name):
    toolset = BashToolset(workspace)
    args = {"path": path}
    if name == "grep":
        args["pattern"] = "fixture"
    if name == "diff":
        args = {"path_a": "notes.txt", "path_b": path}
    result = await getattr(toolset, name)(**args)
    assert result["error"] and result["output"] == ""


@pytest.mark.asyncio
async def test_excluded_directories_and_symlinks_are_pruned(workspace):
    private = workspace / "private"
    private.mkdir()
    (private / "notes.txt").write_text("private fixture", encoding="utf-8")
    (workspace / "directory-alias").symlink_to(private, target_is_directory=True)
    toolset = BashToolset(workspace, exclude_patterns=[".env", "private"])
    for result in (
        await toolset.find(),
        await toolset.ls(show_hidden=True),
        await toolset.grep("fixture"),
    ):
        assert result["error"] is None
        assert str(private) not in result["output"]
        assert "directory-alias" not in result["output"]
        assert ".env" not in result["output"]
    assert (await toolset.cat("private/../notes.txt"))["error"]
    assert (await toolset.cat("safe-alias"))["output"] == _CONTENT
    assert (await BashToolset(workspace, exclude_patterns=[]).cat(".env"))[
        "output"
    ] == "private fixture"


@pytest.mark.asyncio
@pytest.mark.parametrize("replace_directory", [False, True])
async def test_symlink_replacement_between_validation_and_open_is_rejected(
    workspace, monkeypatch, replace_directory
):
    victim = workspace / "nested" if replace_directory else workspace / "notes.txt"
    target = workspace.parent if replace_directory else workspace.parent / "outside.txt"
    original_open = os.open
    replaced = False

    def replace_then_open(path, flags, *args, **kwargs):
        nonlocal replaced
        if path == victim.name and not replaced:
            replaced = True
            victim.rename(workspace / "original")
            victim.symlink_to(target, target_is_directory=replace_directory)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace_then_open)
    path = "nested/notes.txt" if replace_directory else "notes.txt"
    result = await BashToolset(workspace).cat(path)
    assert replaced and result["error"] and result["output"] == ""


@pytest.mark.asyncio
async def test_special_files_and_shell_syntax(workspace):
    os.mkfifo(workspace / "pipe")
    toolset = BashToolset(workspace)
    result = await toolset.cat("pipe")
    assert result["error"] and result["output"] == ""
    assert "pipe" not in (await toolset.find())["output"]
    name = "$(touch marker);notes.txt"
    (workspace / name).write_text("literal filename", encoding="utf-8")
    assert (await toolset.cat(name))["output"] == "literal filename"
    assert not (workspace / "marker").exists()


@pytest.mark.asyncio
async def test_search_filters_and_literal_matching(workspace):
    toolset = BashToolset(workspace)
    result = await toolset.find(pattern="*.txt", max_depth=1)
    assert result["error"] is None and "nested/notes.txt" not in result["output"]
    result = await toolset.find(file_type="directory")
    assert result["output"] == f"{workspace / 'nested'}/\n"
    assert (await toolset.grep("h.*o"))["output"] == ""
    assert (await toolset.grep("hello", file_pattern="*.csv"))["output"] == ""
    result = await toolset.grep("hello", recursive=False, ignore_case=True)
    assert "HELLO nested" not in result["output"]


@pytest.mark.asyncio
async def test_resource_limits_and_unicode_truncation(workspace):
    (workspace / "unicode.txt").write_text("你好\n", encoding="utf-8")
    result = await BashToolset(workspace, max_output_bytes=4).cat("unicode.txt")
    assert result == {"output": "你", "error": None, "truncated": True}
    result = await BashToolset(workspace, max_read_bytes=4).wc("notes.txt")
    assert "max_read_bytes" in result["error"] and result["output"] == ""
    result = await BashToolset(workspace, max_entries=1).find()
    assert "max_entries" in result["error"]
    (workspace / "long.txt").write_text("line\n" * 2001, encoding="utf-8")
    result = await BashToolset(workspace).diff("long.txt", "notes.txt")
    assert "2000 lines" in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_caller", [False, True])
async def test_timeout_and_cancellation_release_worker(
    workspace, monkeypatch, cancel_caller
):
    toolset = BashToolset(workspace, timeout=0.1 if not cancel_caller else 2)
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def delayed_text(path, execution):
        started.set()
        try:
            release.wait(timeout=2)
            execution.check()
            yield "must not be returned"
        finally:
            finished.set()

    monkeypatch.setattr(toolset, "_text", delayed_text)
    task = asyncio.create_task(toolset.cat("notes.txt"))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        if cancel_caller:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            result = await task
            assert (
                result["error"] == "Tool execution timed out" and result["output"] == ""
            )
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 2)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"allowed_tools": ["bash"]},
        {"allowed_tools": "cat"},
        {"allowed_directories": []},
        {"exclude_patterns": [""]},
        {"timeout": 0},
        {"timeout": float("nan")},
        {"timeout": float("inf")},
        {"max_output_bytes": 0},
        {"max_read_bytes": True},
        {"max_entries": -1},
    ],
)
def test_invalid_configuration_fails_closed(workspace, kwargs):
    with pytest.raises((TypeError, ValueError)):
        BashToolset(workspace, **kwargs)


def test_unsupported_platform_is_rejected(workspace, monkeypatch):
    monkeypatch.delattr(os, "O_NOFOLLOW")
    with pytest.raises(NotImplementedError, match="Linux or macOS"):
        BashToolset(workspace)
