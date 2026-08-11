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

"""Provider-native model defaults used by Studio provisioning and codegen."""

from __future__ import annotations

VOLCENGINE_MODELARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
BYTEPLUS_MODELARK_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"

VOLCENGINE_STUDIO_AGENT_MODEL_NAME = "doubao-seed-2-1-pro-260628"
BYTEPLUS_STUDIO_AGENT_MODEL_NAME = "seed-2-0-lite-260228"

VOLCENGINE_GENERATED_AGENT_MODEL_NAME = "doubao-seed-1-6-250615"
BYTEPLUS_GENERATED_AGENT_MODEL_NAME = BYTEPLUS_STUDIO_AGENT_MODEL_NAME

VOLCENGINE_EMBEDDING_MODEL_NAME = "doubao-embedding-vision-250615"
BYTEPLUS_EMBEDDING_MODEL_NAME = "skylark-embedding-vision-250615"

VOLCENGINE_IMAGE_GENERATE_MODEL_NAME = "doubao-seedream-5-0-260128"
BYTEPLUS_IMAGE_GENERATE_MODEL_NAME = "dola-seedream-5-0-pro-260628"

VOLCENGINE_IMAGE_EDIT_MODEL_NAME = "doubao-seededit-3-0-i2i-250628"
BYTEPLUS_IMAGE_EDIT_MODEL_NAME = "seededit-3-0-i2i-250628"

VOLCENGINE_VIDEO_MODEL_NAME = "doubao-seedance-2-0-260128"
BYTEPLUS_VIDEO_MODEL_NAME = "dreamina-seedance-2-0-260128"

BYTEPLUS_MODELARK_MODEL_IDS = frozenset(
    {
        "dola-seed-2-1-turbo-260628",
        "seed-2-0-lite-260428",
        "seed-2-0-mini-260428",
        "seed-2-0-pro-260328",
        "seed-2-0-lite-260228",
        "seed-2-0-lite-260215",
        "seed-2-0-mini-260215",
        "seed-2-0-code-preview-260328",
        "seed-1-8-251228",
        "glm-5-2-260617",
        "glm-4-7-251222",
        "deepseek-v4-flash-ga-260731",
        "deepseek-v4-pro-260425",
        "deepseek-v4-flash-260425",
        "deepseek-v3-2-251201",
        "gpt-oss-120b-250805",
        "seed-1-6-250915",
        "seed-1-6-250615",
        "seed-1-6-flash-250715",
        "seed-1-6-flash-250615",
        "dreamina-seedance-2-5-260628",
        "dreamina-seedance-2-0-260128",
        "dreamina-seedance-2-0-fast-260128",
        "dreamina-seedance-2-0-mini-260615",
        "seedance-1-5-pro-251215",
        "seedance-1-0-pro-250528",
        "seedance-1-0-pro-fast-251015",
        "dola-seedream-5-0-pro-260628",
        "seedream-5-0-260128",
        "seedream-5-0-lite-260128",
        "seedream-4-5-251128",
        "seedream-4-0-250828",
        "Hyper3d-Rodin-Gen2",
        "Hitem3d-2.0",
        "skylark-embedding-vision-251215",
        "skylark-embedding-vision-250615",
        BYTEPLUS_IMAGE_EDIT_MODEL_NAME,
    }
)

BYTEPLUS_SKILL_CREATOR_MODELS = (
    ("a", BYTEPLUS_STUDIO_AGENT_MODEL_NAME, "Seed 2.0 Lite"),
    ("b", "deepseek-v4-flash-260425", "DeepSeek V4 Flash"),
)


def _provider_id(provider: str) -> str:
    return provider.strip().lower()


def studio_agent_model_name(provider: str) -> str:
    return (
        BYTEPLUS_STUDIO_AGENT_MODEL_NAME
        if _provider_id(provider) == "byteplus"
        else VOLCENGINE_STUDIO_AGENT_MODEL_NAME
    )


def modelark_base_url(provider: str) -> str:
    return (
        BYTEPLUS_MODELARK_BASE_URL
        if _provider_id(provider) == "byteplus"
        else VOLCENGINE_MODELARK_BASE_URL
    )


def generated_agent_model_name(provider: str) -> str:
    return (
        BYTEPLUS_GENERATED_AGENT_MODEL_NAME
        if _provider_id(provider) == "byteplus"
        else VOLCENGINE_GENERATED_AGENT_MODEL_NAME
    )


def embedding_model_name(provider: str) -> str:
    return (
        BYTEPLUS_EMBEDDING_MODEL_NAME
        if _provider_id(provider) == "byteplus"
        else VOLCENGINE_EMBEDDING_MODEL_NAME
    )


def image_generate_model_name(provider: str) -> str:
    return (
        BYTEPLUS_IMAGE_GENERATE_MODEL_NAME
        if _provider_id(provider) == "byteplus"
        else VOLCENGINE_IMAGE_GENERATE_MODEL_NAME
    )


def image_edit_model_name(provider: str) -> str:
    return (
        BYTEPLUS_IMAGE_EDIT_MODEL_NAME
        if _provider_id(provider) == "byteplus"
        else VOLCENGINE_IMAGE_EDIT_MODEL_NAME
    )


def video_model_name(provider: str) -> str:
    return (
        BYTEPLUS_VIDEO_MODEL_NAME
        if _provider_id(provider) == "byteplus"
        else VOLCENGINE_VIDEO_MODEL_NAME
    )


def is_byteplus_model(model_id: str) -> bool:
    return model_id.strip() in BYTEPLUS_MODELARK_MODEL_IDS


def provider_allows_model(provider: str, model_id: str) -> bool:
    normalized = model_id.strip()
    if not normalized:
        return False
    if _provider_id(provider) == "byteplus":
        return is_byteplus_model(normalized)
    return True


def provider_env_placeholders(provider: str) -> dict[str, str]:
    return {
        "MODEL_AGENT_NAME": generated_agent_model_name(provider),
        "MODEL_AGENT_API_BASE": modelark_base_url(provider),
        "MODEL_EMBEDDING_NAME": embedding_model_name(provider),
        "MODEL_EMBEDDING_API_BASE": modelark_base_url(provider),
        "MODEL_IMAGE_NAME": image_generate_model_name(provider),
        "MODEL_IMAGE_API_BASE": modelark_base_url(provider),
        "MODEL_EDIT_NAME": image_edit_model_name(provider),
        "MODEL_EDIT_API_BASE": modelark_base_url(provider),
        "MODEL_VIDEO_NAME": video_model_name(provider),
        "MODEL_VIDEO_API_BASE": modelark_base_url(provider),
    }
