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

"""Transcribe an audio file with the Volcengine flash ASR API.

The flash endpoint returns the transcript in the same request, so no task
polling is required. Local files are sent as base64; public URLs are passed
through for the service to download.
"""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Any

import httpx

from veadk.config import getenv, settings
from veadk.tools.builtin_tools.web_fetch import assert_public_url
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_ENDPOINT = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
_RESOURCE_ID = "volc.bigasr.auc_turbo"
_MAX_AUDIO_BYTES = 100 * 1024 * 1024
_SUPPORTED_SUFFIXES = {".wav", ".mp3", ".ogg", ".opus"}
_MAX_UTTERANCES = 200

_STATUS_MESSAGES = {
    "20000003": "the audio contains no speech",
    "45000001": "invalid request parameters",
    "45000002": "the audio is empty",
    "45000151": "unsupported audio format (use wav, mp3, ogg, or opus)",
    "55000031": "the ASR service is busy; retry later",
}


def _resolve_api_key() -> str:
    """Return the speech API key, or an empty string when none is configured."""
    for env_name in ("TOOL_SPEECH_TO_TEXT_API_KEY", "TOOL_VESPEECH_API_KEY"):
        value = getenv(env_name, "", allow_false_values=True)
        if value:
            return value
    try:
        return settings.tool.vespeech.api_key or ""
    except Exception as e:  # Missing AK/SK must surface as a tool error.
        logger.debug(f"Unable to resolve the speech API key: {e}")
        return ""


def _load_audio(audio: str) -> dict[str, str]:
    """Build the ``audio`` request object for a local path or public URL."""
    if audio.startswith(("http://", "https://")):
        assert_public_url(audio)
        return {"url": audio}

    path = Path(audio).expanduser()
    if not path.is_file():
        raise ValueError(f"audio file does not exist: {audio}")
    if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise ValueError(
            "unsupported audio format; expected one of: "
            + ", ".join(sorted(_SUPPORTED_SUFFIXES))
        )
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("the audio file is empty")
    if size > _MAX_AUDIO_BYTES:
        raise ValueError("the audio file exceeds the 100 MB limit")
    return {"data": base64.b64encode(path.read_bytes()).decode("ascii")}


def _parse_response(response: httpx.Response) -> dict[str, Any]:
    status = response.headers.get("X-Api-Status-Code", "")
    log_id = response.headers.get("X-Tt-Logid", "")
    if status != "20000000":
        message = _STATUS_MESSAGES.get(status) or response.headers.get("X-Api-Message")
        return {
            "error": message
            or f"ASR request failed with status {status or response.status_code}",
            "code": status or str(response.status_code),
            "log_id": log_id,
        }

    try:
        payload = response.json()
    except ValueError as e:
        return {"error": f"invalid ASR response: {e}", "log_id": log_id}

    result = payload.get("result") if isinstance(payload, dict) else None
    result = result if isinstance(result, dict) else {}
    text = result.get("text")
    if not isinstance(text, str):
        text = ""

    utterances: list[dict[str, Any]] = []
    raw_utterances = result.get("utterances")
    if isinstance(raw_utterances, list):
        for item in raw_utterances[:_MAX_UTTERANCES]:
            if not isinstance(item, dict):
                continue
            utterances.append(
                {
                    "start_time": item.get("start_time"),
                    "end_time": item.get("end_time"),
                    "text": item.get("text", ""),
                }
            )

    audio_info = payload.get("audio_info") if isinstance(payload, dict) else None
    duration = audio_info.get("duration") if isinstance(audio_info, dict) else None
    return {
        "text": text,
        "duration_ms": duration,
        "utterances": utterances,
        "log_id": log_id,
    }


async def speech_to_text(audio: str, timeout: int = 300) -> dict:
    """Transcribe speech in an audio file into text.

    Supports local wav/mp3/ogg/opus files (up to 100 MB) and public http(s)
    audio URLs. The service auto-detects the spoken language.

    Args:
        audio: Local file path or public http(s) URL of the audio.
        timeout: Request timeout in seconds, between 1 and 600.

    Returns:
        A dict with ``text``, ``duration_ms``, ``utterances`` and ``log_id``,
        or a dict with ``error`` when transcription fails.
    """
    if not audio or not isinstance(audio, str):
        return {"error": "audio must be a non-empty path or URL"}
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 1 <= timeout <= 600
    ):
        return {"error": "timeout must be an integer between 1 and 600 seconds"}

    api_key = _resolve_api_key()
    if not api_key:
        return {
            "error": (
                "Missing speech API key: set TOOL_SPEECH_TO_TEXT_API_KEY "
                "(or TOOL_VESPEECH_API_KEY)."
            )
        }

    try:
        audio_payload = _load_audio(audio)
    except ValueError as e:
        return {"error": str(e)}

    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": _RESOURCE_ID,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Sequence": "-1",
        "Content-Type": "application/json",
    }
    body = {
        "user": {"uid": "veadk"},
        "audio": audio_payload,
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(_ENDPOINT, headers=headers, json=body)
    except httpx.HTTPError as e:
        logger.error(f"speech_to_text request failed: {e}")
        return {"error": f"ASR request failed: {e}"}

    if response.status_code >= 400 and not response.headers.get("X-Api-Status-Code"):
        return {
            "error": f"ASR request failed with HTTP {response.status_code}",
            "log_id": response.headers.get("X-Tt-Logid", ""),
        }
    return _parse_response(response)
