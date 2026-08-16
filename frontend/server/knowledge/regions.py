# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""Knowledge control-plane and provider data-plane region mappings."""

from __future__ import annotations


def provider_data_region(provider: str, control_region: str) -> str:
    """Resolve the Viking and TOS data-plane region for a control region."""
    if provider == "byteplus" and control_region == "ap-southeast-1":
        return "cn-hongkong"
    return control_region


__all__ = ["provider_data_region"]
