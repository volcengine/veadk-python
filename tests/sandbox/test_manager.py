"""Offline lifecycle contract checks; no cloud credentials or network required."""

import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as Obj

from veadk.sandbox import (
    SandboxError,
    SandboxManager,
    SessionKey,
)
from veadk.sandbox.manager import _api_error_code as api_error_code
from veadk.sandbox.manager import _mcp_endpoint as mcp_endpoint


class FakeClient:
    def __init__(self):
        self.calls = []
        self.sessions = {}
        self.lose_create_response = False
        self.reject_create = False
        self.fail_get = False

    def create_session(self, req):
        self.calls.append("create")
        if self.reject_create:
            raise TimeoutError("submission unknown")
        sid = f"sandbox-{len(self.sessions) + 1}"
        self.sessions[sid] = Obj(
            session_id=sid,
            user_session_id=req.user_session_id,
            status="Ready",
            endpoint="https://example.com/?Authorization=secret&route=1",
        )
        if self.lose_create_response:
            raise TimeoutError("response lost")
        return self.sessions[sid]

    def list_sessions(self, req):
        return Obj(session_infos=list(self.sessions.values()), next_token=None)

    def get_session(self, req):
        if self.fail_get:
            raise TimeoutError("temporary outage")
        return self.sessions[req.session_id]

    def pause_session(self, req):
        self.calls.append("pause")
        self.sessions[req.session_id].status = "Paused"
        return Obj(session_id=req.session_id)

    def resume_session(self, req):
        self.calls.append("resume")
        value = self.sessions[req.session_id]
        value.status = "Ready"
        value.endpoint = "https://example.com/?Authorization=refreshed&route=2"
        return Obj(session_id=req.session_id)

    def delete_session(self, req):
        self.calls.append("delete")
        self.sessions[req.session_id].status = "Terminated"
        return Obj(session_id=req.session_id)


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = FakeClient()
        self.key = SessionKey("app", "user", "chat")
        self.manager = self.new_manager()

    def new_manager(self):
        return SandboxManager(
            tool_id="test-tool",
            state_dir=Path(self.tmp.name),
            client=self.client,
            poll_interval=0.01,
            ready_timeout=0.15,
        )

    async def test_create_pause_restart_resume_delete(self):
        async with self.manager.acquire(self.key) as first:
            sid = first.session_id
            self.assertIn("Authorization=secret", first.mcp_url)
            self.assertNotIn("secret", repr(first))
        await self.manager.pause(self.key)
        async with self.new_manager().acquire(self.key) as resumed:
            self.assertEqual(resumed.session_id, sid)
            self.assertIn("Authorization=refreshed", resumed.mcp_url)
        await self.manager.delete(self.key)
        await self.manager.delete(self.key)
        with self.assertRaises(SandboxError):
            async with self.manager.acquire(self.key):
                pass
        self.assertEqual(self.client.calls, ["create", "pause", "resume", "delete"])
        saved = "".join(p.read_text() for p in Path(self.tmp.name).glob("*.json"))
        self.assertNotIn("Authorization", saved)
        self.assertNotIn("secret", saved)

    async def test_lost_create_response_recovers_same_session(self):
        self.client.lose_create_response = True
        async with self.manager.acquire(self.key) as lease:
            self.assertEqual(lease.session_id, "sandbox-1")
        self.assertEqual(self.client.calls, ["create"])

    async def test_unknown_create_never_automatically_retries(self):
        self.client.reject_create = True
        for _ in range(2):
            with self.assertRaises(SandboxError):
                async with self.new_manager().acquire(self.key):
                    pass
        self.assertEqual(self.client.calls, ["create"])

    async def test_lookup_error_does_not_replace_sandbox(self):
        async with self.manager.acquire(self.key):
            pass
        self.client.fail_get = True
        with self.assertRaises(SandboxError):
            async with self.manager.acquire(self.key):
                pass
        self.assertEqual(self.client.calls, ["create"])

    async def test_terminal_session_is_not_replaced(self):
        async with self.manager.acquire(self.key) as lease:
            sid = lease.session_id
        self.client.sessions[sid].status = "Terminated"
        with self.assertRaises(SandboxError):
            async with self.new_manager().acquire(self.key):
                pass
        self.assertEqual(self.client.calls, ["create"])

    async def test_ambiguous_create_recovery_never_picks_an_instance(self):
        self.client.lose_create_response = True

        def ambiguous(req):
            value = next(iter(self.client.sessions.values()))
            other = Obj(**vars(value))
            other.session_id = "sandbox-2"
            return Obj(session_infos=[value, other], next_token=None)

        self.client.list_sessions = ambiguous
        for _ in range(2):
            with self.assertRaisesRegex(SandboxError, "ambiguous"):
                async with self.new_manager().acquire(self.key):
                    pass
        self.assertEqual(self.client.calls, ["create"])

    async def test_create_recovery_paginates(self):
        self.client.lose_create_response = True
        cursors = []

        def pages(req):
            cursors.append(req.next_token)
            if req.next_token is None:
                return Obj(session_infos=[], next_token="page-2")
            return Obj(
                session_infos=list(self.client.sessions.values()), next_token=None
            )

        self.client.list_sessions = pages
        async with self.manager.acquire(self.key) as lease:
            self.assertEqual(lease.session_id, "sandbox-1")
        self.assertEqual(cursors, [None, "page-2"])

    async def test_poll_timeout_preserves_existing_binding(self):
        original = self.client.create_session

        def starting(req):
            value = original(req)
            value.status = "Starting"
            return value

        self.client.create_session = starting
        with self.assertRaisesRegex(SandboxError, "Timed out"):
            async with self.manager.acquire(self.key):
                pass
        self.client.sessions["sandbox-1"].status = "Ready"
        async with self.new_manager().acquire(self.key) as lease:
            self.assertEqual(lease.session_id, "sandbox-1")
        self.assertEqual(self.client.calls, ["create"])

    async def test_pause_waits_for_active_turn_across_managers(self):
        async with self.manager.acquire(self.key):
            pause = asyncio.create_task(self.new_manager().pause(self.key))
            await asyncio.sleep(0.03)
            self.assertNotIn("pause", self.client.calls)
        await pause
        self.assertEqual(self.client.calls, ["create", "pause"])

    async def test_cancelled_turn_releases_lock(self):
        entered = asyncio.Event()

        async def turn():
            async with self.manager.acquire(self.key):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(turn())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await self.manager.pause(self.key)
        self.assertEqual(self.client.calls, ["create", "pause"])

    async def test_cancelled_control_request_waits_for_worker(self):
        started, release = threading.Event(), threading.Event()
        original = self.client.create_session

        def slow_create(req):
            started.set()
            release.wait(2)
            return original(req)

        self.client.create_session = slow_create

        async def turn():
            async with self.manager.acquire(self.key):
                pass

        task = asyncio.create_task(turn())
        while not started.is_set():
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.02)
        self.assertFalse(task.done())
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        async with self.new_manager().acquire(self.key) as lease:
            self.assertEqual(lease.session_id, "sandbox-1")
        self.assertEqual(self.client.calls, ["create"])

    async def test_delete_accepts_structured_not_found_after_success(self):
        async with self.manager.acquire(self.key):
            pass

        def gone(req):
            cause = Exception(
                json.dumps(
                    {
                        "ResponseMetadata": {
                            "Error": {"Code": "InvalidResource.NotFound"}
                        }
                    }
                ).encode()
            )
            error = RuntimeError("SDK wrapper")
            error.__cause__ = cause
            raise error

        self.client.get_session = gone
        await self.manager.delete(self.key)
        self.assertEqual((await self.manager.status(self.key))["phase"], "deleted")

    async def test_delete_outage_retains_tombstone_and_blocks_acquire(self):
        async with self.manager.acquire(self.key):
            pass
        self.client.fail_get = True
        with self.assertRaises(SandboxError):
            await self.manager.delete(self.key)
        self.client.fail_get = False
        with self.assertRaises(SandboxError):
            async with self.manager.acquire(self.key):
                pass
        self.assertEqual(self.client.calls.count("create"), 1)

    def test_error_message_alone_does_not_prove_deletion(self):
        self.assertIsNone(api_error_code(RuntimeError("InvalidResource.NotFound")))

    def test_endpoint_preserves_query_and_rejects_invalid_paths(self):
        self.assertEqual(
            mcp_endpoint("https://example.com/?route=x&Authorization=y"),
            "https://example.com/mcp?route=x&Authorization=y",
        )
        self.assertEqual(
            mcp_endpoint("https://example.com/mcp?a=b"), "https://example.com/mcp?a=b"
        )
        with self.assertRaises(SandboxError):
            mcp_endpoint("https://example.com/unexpected/path")


if __name__ == "__main__":
    unittest.main()
