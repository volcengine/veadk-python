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

"""DeepSeek Harness skill materialization and patch generation."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from veadk.runtime.piagent.skills import PiSkillBundle, materialize_skills_for_pi
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from veadk.agent import Agent

logger = get_logger(__name__)

_EMPTY_SKILL_DIGEST = hashlib.sha256(b"[]").hexdigest()


@dataclass
class DeepSeekHarnessSkillRegistration:
    """Materialized DSH skill root plus stable content digest."""

    bundle: PiSkillBundle
    digest: str

    @property
    def has_skills(self) -> bool:
        return bool(self.bundle.root and self.bundle.count)

    @property
    def root(self) -> Path | None:
        return self.bundle.root

    @classmethod
    def from_agent(cls, agent: Agent) -> DeepSeekHarnessSkillRegistration:
        bundle = materialize_skills_for_pi(agent)
        digest = _skill_bundle_digest(bundle)
        if bundle.count:
            logger.info(
                "deepseek_harness: materialized %s skill(s) for DSH into %s",
                bundle.count,
                bundle.root,
            )
        return cls(bundle=bundle, digest=digest)

    def close(self) -> None:
        self.bundle.close()


class DeepSeekHarnessSkillPatch:
    """Manager-owned DSH patch enabling the native filesystem skill provider."""

    def __init__(
        self,
        registration: DeepSeekHarnessSkillRegistration,
        tmpdir: tempfile.TemporaryDirectory[str],
        patch_path: str,
    ) -> None:
        self.registration = registration
        self._tmpdir = tmpdir
        self.patch_path = patch_path

    @classmethod
    def create(
        cls,
        registration: DeepSeekHarnessSkillRegistration,
        *,
        profile: str,
    ) -> DeepSeekHarnessSkillPatch | None:
        if not registration.has_skills or registration.root is None:
            return None

        tmpdir = tempfile.TemporaryDirectory(prefix="veadk-deepseek-harness-skills-")
        patch = Path(tmpdir.name) / "veadk-dsh-skills.patch.yml"
        root = str(registration.root)
        if profile == "sdk":
            patch_text = (
                "- id: skill-filesystem\n"
                "  config:\n"
                "    includeDefaultRoots: false\n"
                "    watch: false\n"
                "    customSkillDirs:\n"
                f"      - {json.dumps(root, ensure_ascii=False)}\n"
            )
        else:
            patch_text = (
                "- insert:\n"
                "    - id: veadk-skill-registry\n"
                "      name: '@deepseek-ai/dsh-skill'\n"
                "    - id: veadk-skill-filesystem\n"
                "      name: '@deepseek-ai/dsh-skill-filesystem'\n"
                "      config:\n"
                "        includeDefaultRoots: false\n"
                "        watch: false\n"
                "        customSkillDirs:\n"
                f"          - {json.dumps(root, ensure_ascii=False)}\n"
                "    - id: veadk-tool-skill\n"
                "      name: '@deepseek-ai/dsh-tool-skill'\n"
            )
        patch.write_text(patch_text, encoding="utf-8")
        return cls(registration=registration, tmpdir=tmpdir, patch_path=str(patch))

    def close(self) -> None:
        self.registration.close()
        self._tmpdir.cleanup()


def _skill_bundle_digest(bundle: PiSkillBundle) -> str:
    if not bundle.root or not bundle.paths:
        return _EMPTY_SKILL_DIGEST

    records: list[tuple[str, str]] = []
    root = bundle.root
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        records.append(
            (
                rel,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    data = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
