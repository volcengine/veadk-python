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

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

# Preserve the pinned release's pipeline/rename structure and function boundary.
ORIGINAL = """function ble/builtin/bind/read-user-settings/.collect {
  local cache=$1
  printf '%s\\n' "$2" | cat >| "$cache.part" &&
    ble/bin/mv "$cache.part" "$cache"
}
unrelated='"$cache.part"'
"""
WORKER = """source "$1"
function ble/bin/mv {
  printf 'ready\\n'
  read -r release
  command mv "$@"
}
ble/builtin/bind/read-user-settings/.collect "$2" "$3"
"""


class BleCacheTest(unittest.TestCase):
    def writers(self, script: Path) -> list[subprocess.CompletedProcess[str]]:
        workers = [
            subprocess.Popen(
                [
                    "/bin/bash",
                    "--noprofile",
                    "--norc",
                    "-c",
                    WORKER,
                    "bash",
                    str(script),
                    str(script.parent / "cache"),
                    value,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for value in ("first complete cache", "second complete cache")
        ]
        try:
            for worker in workers:
                assert worker.stdout is not None
                self.assertEqual(worker.stdout.readline(), "ready\n")
            results = []
            for worker in workers:
                stdout, stderr = worker.communicate("\n", timeout=5)
                results.append(
                    subprocess.CompletedProcess(
                        worker.args, worker.returncode, stdout, stderr
                    )
                )
            return results
        finally:
            for worker in workers:
                if worker.poll() is None:
                    worker.kill()
                worker.communicate()

    def test_original_shared_temporary_file_loses_a_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "ble.sh"
            script.write_text(ORIGINAL)
            results = self.writers(script)
            self.assertEqual(sum(result.returncode != 0 for result in results), 1)

    def test_patched_concurrent_writers_publish_complete_cache(self) -> None:
        from ble_cache import patch_blesh

        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "ble.sh"
            script.write_text(ORIGINAL)
            patch_blesh(script)
            for result in self.writers(script):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
            self.assertIn(
                (script.parent / "cache").read_text(),
                {"first complete cache\n", "second complete cache\n"},
            )
            self.assertFalse(list(script.parent.glob("*.part")))

    def test_patch_is_scoped_and_idempotent(self) -> None:
        from ble_cache import patch_blesh

        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "ble.sh"
            script.write_text(ORIGINAL)
            script.chmod(0o644)
            patch_blesh(script)
            content, modified = script.read_text(), script.stat().st_mtime_ns
            patch_blesh(script)
            self.assertEqual(script.read_text(), content)
            self.assertEqual(script.stat().st_mtime_ns, modified)
            self.assertEqual(script.stat().st_mode & 0o777, 0o644)
            self.assertTrue(content.endswith("unrelated='\"$cache.part\"'\n"))

    def test_unexpected_source_is_not_modified(self) -> None:
        from ble_cache import patch_blesh

        for content in (
            "new upstream source",
            ORIGINAL.replace('"$cache.part"', '"$other"', 1),
        ):
            with (
                self.subTest(content=content),
                tempfile.TemporaryDirectory() as temporary,
            ):
                script = Path(temporary) / "ble.sh"
                script.write_text(content)
                with self.assertRaises(ValueError):
                    patch_blesh(script)
                self.assertEqual(script.read_text(), content)


if __name__ == "__main__":
    unittest.main()
