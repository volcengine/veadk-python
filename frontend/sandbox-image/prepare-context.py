#!/usr/bin/env python3
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

"""Prepare an allowlisted build context; no repository or credential files are copied."""

import argparse
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
import re
from pathlib import Path


def fetch_asset(asset: dict[str, str], cache: Path) -> Path:
    path = cache / asset["file"]
    if path.exists():
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == asset["sha256"]:
                return path
    partial = path.with_suffix(path.suffix + ".part")
    subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--retry",
            "3",
            "--connect-timeout",
            "15",
            "--max-time",
            "600",
            "--output",
            str(partial),
            asset["url"],
        ],
        check=True,
    )
    with partial.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != asset["sha256"]:
        raise ValueError(f"Checksum mismatch: {asset['file']}")
    partial.replace(path)
    print(f"Verified {path.name}: {path.stat().st_size:,} bytes", flush=True)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--base-image",
        required=True,
        help="Registry image reference used only in the generated context",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new archive path")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./_:@-]+", args.base_image):
        parser.error("Invalid base image reference")
    args.cache.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parent
    assets = json.loads((source / "assets.lock.json").read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(lambda asset: fetch_asset(asset, args.cache), assets))
    with tempfile.TemporaryDirectory(prefix="studio-sandbox-context-") as temporary:
        context = Path(temporary)
        for filename in (
            "Dockerfile",
            "requirements.in",
            "requirements.lock",
            "settings.json",
            "assets.lock.json",
        ):
            shutil.copyfile(source / filename, context / filename)
        dockerfile = context / "Dockerfile"
        dockerfile.write_text(
            dockerfile.read_text().replace(
                "ARG BASE_IMAGE\n", f"ARG BASE_IMAGE={args.base_image}\n", 1
            )
        )
        shutil.copytree(
            source / "runtime",
            context / "runtime",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        (context / "assets").mkdir()
        for path in paths:
            shutil.copyfile(path, context / "assets" / path.name)
        with tarfile.open(args.output, "w:gz") as archive:
            for path in sorted(context.rglob("*")):
                if path.is_file():
                    archive.add(
                        path, arcname=str(path.relative_to(context)), recursive=False
                    )
    with args.output.open("rb") as stream:
        print(f"sha256 {hashlib.file_digest(stream, 'sha256').hexdigest()}")
    print(f"archive {args.output.resolve()} ({args.output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
