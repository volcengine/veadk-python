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

import requests
import json
import base64
import time
import queue
import pyaudio
import threading
import tempfile
from google.adk.tools import ToolContext
from veadk.config import getenv
from veadk.utils.logger import get_logger
from veadk.utils.audio_manager import AudioDeviceManager, AudioConfig

logger = get_logger(__name__)

input_audio_config = {
    "chunk": 3200,
    "format": "pcm",
    "channels": 1,
    "sample_rate": 16000,
    "bit_size": pyaudio.paInt16,
}

output_audio_config = {
    "chunk": 3200,
    "format": "pcm",
    "channels": 1,
    "sample_rate": 24000,
    "bit_size": pyaudio.paInt16,
}


def tts(text: str, tool_context: ToolContext) -> bool:
    """TTS provides users with the ability to convert text to speech, turning the text content of LLM into audio.
    Use this tool when you need to convert text content into audible speech.
    It transforms plain text into natural-sounding speech, and supports customizations including voice timbre
    selection (e.g., male/female/neutral), speech speed and volume adjustment, as well as exporting the generated
    audio in common formats (e.g., MP3, WAV).

    Args:
        text: The text to convert.

    Returns:
        True if the TTS conversion is successful, False otherwise.
    """
    url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    audio_save_path = ""
    success = True

    app_id = getenv("TOOL_TTS_APP_ID")
    api_key = getenv("TOOL_TTS_API_KEY")
    speaker = getenv("TOOL_TTS_SPEAKER")  # e.g. zh_female_vv_mars_bigtts
    headers = {
        "X-Api-App-Id": app_id,
        "X-Api-Access-Key": api_key,
        "X-Api-Resource-Id": "seed-tts-1.0",  # seed-tts-1.0 or seed-tts-2.0
        "Content-Type": "application/json",
        "Connection": "keep-alive",
    }
    payload = {
        "user": {"uid": tool_context._invocation_context.user_id},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": "pcm",
                "bit_rate": 16000,
                "sample_rate": 24000,
                "enable_timestamp": True,
            },
            "additions": '{"explicit_language":"zh","disable_markdown_filter":true, "enable_timestamp":true}"}',
        },
    }

    session = requests.Session()
    response = None

    try:
        logger.debug(f"Request TTS server with payload: {payload}.")
        response = session.post(url, headers=headers, json=payload, stream=True)
        log_id = response.headers.get("X-Tt-Logid")
        logger.debug(
            f"Response from TTS server with logid: {log_id}, and response body {response}"
        )

        with tempfile.NamedTemporaryFile(
            suffix=".pcm", delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            audio_save_path = tmp.name  # e.g. /tmp/tts_12345.pcm
        handle_server_response(response, audio_save_path)

    except Exception as e:
        logger.debug(f"Failed to convert text to speech: {e}")
        success = False
    finally:
        if response:
            response.close()
        session.close()
    return success


def handle_server_response(
    response: requests.models.Response, audio_save_path: str
) -> None:
    """
    Handle the server response for TTS.

    Args:
        response: The server response as a dictionary.

    Returns:
        None
    """

    # audio data buffer
    audio_data = bytearray()
    # audio data queue for player thread
    audio_queue = queue.Queue()
    total_audio_size = 0

    audio_device = AudioDeviceManager(
        AudioConfig(**input_audio_config), AudioConfig(**output_audio_config)
    )

    # init output stream
    output_stream = audio_device.open_output_stream()
    stop_event = threading.Event()
    player_thread = threading.Thread(
        target=_audio_player_thread, args=(audio_queue, output_stream, stop_event)
    )
    player_thread.daemon = True
    player_thread.start()

    try:
        for chunk in response.iter_lines(decode_unicode=True):
            if not chunk:
                continue
            data = json.loads(chunk)

            if data.get("code", 0) == 0 and "data" in data and data["data"]:
                chunk_audio = base64.b64decode(data["data"])
                audio_size = len(chunk_audio)
                total_audio_size += audio_size
                audio_queue.put(chunk_audio)
                audio_data.extend(chunk_audio)
                continue
            if data.get("code", 0) == 0 and "sentence" in data and data["sentence"]:
                logger.debug(f"sentence_data: {data}")
                continue
            if data.get("code", 0) == 20000000:
                logger.debug(
                    f"successfully get audio data, total size: {total_audio_size / 1024:.2f} KB"
                )
                break
            if data.get("code", 0) > 0:
                logger.debug(f"error response:{data}")
                break

        # save audio data to file
        save_output_to_file(audio_data, audio_save_path)
    except Exception as e:
        logger.error(f"handle tts failed: {e}, response: {response}")
    finally:
        audio_queue.join()
        stop_event.set()
        player_thread.join()
        output_stream.close()


def _audio_player_thread(audio_queue, output_stream, stop_event):
    """
    Play audio data from queue.
    Args:
        audio_queue: The queue to store audio data.
        output_stream: The output stream to play audio.
        stop_event: The event to stop the thread.

    Returns:

    """
    while not stop_event.is_set():
        try:
            # write audio data to output stream
            audio_data = audio_queue.get(timeout=1.0)
            if audio_data:
                output_stream.write(audio_data)
            audio_queue.task_done()
        except queue.Empty:
            # if queue is empty, sleep for a while
            time.sleep(0.1)
        except Exception as e:
            logger.debug(f"Failed to play audio data: {e}")
            time.sleep(0.1)
    logger.debug("audio player thread exited")


def save_output_to_file(audio_data: bytearray, filename: str):
    """
    Save audio data to file.

    Args:
        audio_data: The audio data as bytes.
        filename: The filename to save the audio data.

    Returns:
        None
    """

    if not audio_data:
        logger.debug("No audio data to save.")
        return
    if not filename:
        logger.debug("No filename to save audio data.")
        return

    try:
        with open(filename, "wb") as f:
            f.write(audio_data)
            logger.debug(
                f"Successfully save audio file to {filename},file size: {len(audio_data) / 1024:.2f} KB"
            )
    except IOError as e:
        logger.debug(f"Failed to save pcm file: {e}")
