"""Keep loopback integration traffic local, even on proxy-configured hosts."""

import os

import pytest


@pytest.fixture(autouse=True)
def local_http_bypass(monkeypatch):
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(name, os.getenv(name, "") + ",127.0.0.1,localhost,::1")
