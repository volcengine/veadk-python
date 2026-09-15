# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Lightweight contracts shared by model-catalog transport and services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

CloudCredentials = tuple[str, str, str | None]
CredentialResolver = Callable[[], CloudCredentials]
Provider = Literal["volcengine", "byteplus"]
SignedRequest = Callable[..., Any]


class ModelCatalogError(RuntimeError):
    """A sanitized, retryable failure safe to return to a Studio client."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


__all__ = [
    "CloudCredentials",
    "CredentialResolver",
    "ModelCatalogError",
    "Provider",
    "SignedRequest",
]
