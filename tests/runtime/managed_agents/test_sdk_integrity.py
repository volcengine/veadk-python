"""The image must reject a modified SDK even when imports still work."""

import base64
import hashlib
import importlib.metadata
import runpy
from pathlib import Path

import pytest


CHECKER = (
    Path(__file__).resolve().parents[3]
    / "docker/managed-agents/verify_anthropic_sdk.py"
)


def checker():
    return runpy.run_path(str(CHECKER))["verify_distribution"]


def test_installed_official_sdk_is_intact():
    assert checker()(importlib.metadata.distribution("anthropic")) > 0


@pytest.mark.parametrize("change", ["modified", "missing", "unrecorded"])
def test_record_validation_rejects_changed_python_files(tmp_path, change):
    package = tmp_path / "anthropic"
    package.mkdir()
    source = package / "__init__.py"
    source.write_bytes(b"# official fixture\n")
    digest = (
        base64.urlsafe_b64encode(hashlib.sha256(source.read_bytes()).digest())
        .decode()
        .rstrip("=")
    )
    record = f"anthropic/__init__.py,sha256={digest},{source.stat().st_size}\n"

    class Distribution:
        def read_text(self, name):
            assert name == "RECORD"
            return record

        def locate_file(self, path):
            return tmp_path / path

    assert checker()(Distribution()) == 1
    if change == "modified":
        source.write_bytes(b"# replaced fixture\n")
    elif change == "missing":
        source.unlink()
    else:
        (package / "overlay.py").write_bytes(b"# overlay fixture\n")
    with pytest.raises(RuntimeError, match="SDK integrity"):
        checker()(Distribution())
