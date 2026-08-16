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

"""Knowledge control-plane and provider data-plane region mappings."""

from __future__ import annotations


def provider_data_region(provider: str, control_region: str) -> str:
    """Resolve the Viking and TOS data-plane region for a control region."""
    if provider == "byteplus" and control_region == "ap-southeast-1":
        return "cn-hongkong"
    return control_region


__all__ = ["provider_data_region"]
