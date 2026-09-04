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

import os
import requests
import json
import base64
import time
import queue
import threading
import tempfile
from typing import Dict, Any
from google.adk.tools import ToolContext
from veadk.config import getenv, settings
from veadk.utils.http_defaults import (
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_STREAM_BUDGET_SECONDS,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# bound on how long the audio player thread may take to exit once it has been
# told to stop; a thread that is still marking queued chunks done is granted a
# further window of the same length, so only a stalled one is given up on
_PLAYER_JOIN_TIMEOUT = 5.0

# how long the player thread waits for the next chunk before re-checking the
# stop event, and so the worst case delay between the queue running dry and the
# thread exiting
_PLAYER_QUEUE_POLL_TIMEOUT = 0.1


def text_to_speech(text: str, tool_context: ToolContext) -> Dict[str, Any]:
    """TTS provides users with the ability to convert text to speech, turning the text content of LLM into audio.
    Use this tool when you need to convert text content into audible speech.
    It transforms plain text into natural-sounding speech, as well as exporting the generated audio in pcm format.

    Args:
        text: The text to convert.

    Returns:
        A dict with the saved audio path.
    """
    url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    temp_dir = getenv("TOOL_VESPEECH_AUDIO_OUTPUT_PATH", tempfile.gettempdir())

    app_id = getenv("TOOL_VESPEECH_APP_ID")
    speaker = getenv(
        "TOOL_VESPEECH_SPEAKER", "zh_female_vv_uranus_bigtts"
    )  # e.g. zh_female_vv_mars_bigtts
    api_key = settings.tool.vespeech.api_key
    if not all([app_id, api_key, speaker]):
        return {
            "error": (
                "Tool text_to_speech execution failed. Missing required env vars: "
                "TOOL_VESPEECH_APP_ID, TOOL_VESPEECH_API_KEY, TOOL_VESPEECH_SPEAKER"
            )
        }

    headers = {
        "X-Api-App-Id": app_id,
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": "seed-tts-2.0",  # seed-tts-1.0 or seed-tts-2.0
        "Content-Type": "application/json",
        "Connection": "keep-alive",
    }
    additions = {
        "explicit_language": "zh",
        "disable_markdown_filter": True,
        "enable_timestamp": True,
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
            "additions": json.dumps(additions),
        },
    }

    session = requests.Session()
    response = None

    try:
        logger.debug(f"Request TTS server with payload: {payload}.")
        response = session.post(
            url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=DEFAULT_HTTP_TIMEOUT,
        )

        os.makedirs(temp_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            suffix=".pcm", delete=False, dir=temp_dir
        ) as tmp:
            audio_save_path = tmp.name  # e.g. /tmp/tts_12345.pcm
            logger.debug(f"Created temporary file: {audio_save_path}")

        handle_server_response(response, audio_save_path)

    except Exception as e:
        logger.error(
            f"Failed to convert text to speech: {e}Response content: {response}"
        )
        return {
            "error": f"Tool text_to_speech execution failed. "
            f"Response content: {response}"
            f"Execution Error: {e}"
        }
    finally:
        if response:
            response.close()
        session.close()
    logger.debug("Finish convert text to speech")
    return {"saved_audio_path": audio_save_path}


def handle_server_response(
    response: requests.models.Response, audio_save_path: str
) -> None:
    """
    Handle the server response for TTS.

    Args:
        response: The server response as a requests.models.Response object.

    Returns:
        None
    """

    # audio data buffer
    audio_data = bytearray()
    # audio data queue for player thread
    audio_queue = queue.Queue()
    total_audio_size = 0

    output_stream, player_thread = None, None
    stop_event = threading.Event()
    try:
        from veadk.utils.audio_manager import (
            AudioDeviceManager,
            AudioConfig,
            input_audio_config,
            output_audio_config,
        )

        audio_device = AudioDeviceManager(
            AudioConfig(**input_audio_config), AudioConfig(**output_audio_config)
        )

        # init output stream
        output_stream = audio_device.open_output_stream()
        player_thread = threading.Thread(
            target=_audio_player_thread, args=(audio_queue, output_stream, stop_event)
        )
        player_thread.daemon = True
        player_thread.start()
    except Exception as e:
        logger.error(f"Failed to initialize audio device: {e}")

    deadline = time.monotonic() + DEFAULT_STREAM_BUDGET_SECONDS
    try:
        for chunk in response.iter_lines(decode_unicode=True):
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"tts response not finished within {DEFAULT_STREAM_BUDGET_SECONDS}s"
                )
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
                logger.debug(f"tts response error:{data}")
                break

        # save audio data to file
        save_output_to_file(audio_data, audio_save_path)
    except Exception as e:
        logger.error(f"handle tts failed: {e}, response: {response}")
        raise
    finally:
        if output_stream:
            # Ask the player to play out what it already holds and then exit.
            # Signalling before waiting is what makes the wait bounded: a
            # thread wedged inside a blocking output_stream.write can only
            # observe the event once that write returns, and one that never
            # returns must be abandoned rather than waited on.
            stop_event.set()
            if player_thread:
                _join_audio_player_thread(player_thread, audio_queue)
            output_stream.close()


def _join_audio_player_thread(player_thread, audio_queue) -> None:
    """Wait for a stopping player thread to drain and exit, but never forever.

    The caller has already set the stop event, so the thread plays whatever is
    still queued and then leaves. Each wait is bounded by _PLAYER_JOIN_TIMEOUT
    and is only renewed while the thread keeps marking chunks done, so healthy
    playback of any length still drains in full while a thread stalled inside
    output_stream.write is given up on after a single window. audio_queue.join()
    cannot do this job: it takes no timeout, and a stalled thread never reaches
    task_done(). Nothing feeds the queue any more, so unfinished_tasks only
    falls and the loop runs at most once per queued chunk.

    Args:
        player_thread: The already signalled audio player thread.
        audio_queue: The queue that thread is draining.

    Returns:
        None
    """
    pending = audio_queue.unfinished_tasks
    while True:
        player_thread.join(timeout=_PLAYER_JOIN_TIMEOUT)
        if not player_thread.is_alive():
            return
        remaining = audio_queue.unfinished_tasks
        if remaining >= pending:
            logger.error("audio player thread did not exit in time")
            return
        pending = remaining


def _audio_player_thread(audio_queue, output_stream, stop_event):
    """
    Play audio data from queue.
    Args:
        audio_queue: The queue to store audio data.
        output_stream: The output stream to play audio.
        stop_event: The event asking the thread to play out the queue and exit.

    Returns:

    """
    # stop_event means "finish what is already queued, then exit", so the thread
    # only leaves once the queue has actually run dry as well.
    while not stop_event.is_set() or not audio_queue.empty():
        try:
            audio_data = audio_queue.get(timeout=_PLAYER_QUEUE_POLL_TIMEOUT)
        except queue.Empty:
            continue
        try:
            # write audio data to output stream
            if audio_data:
                output_stream.write(audio_data)
        except Exception as e:
            logger.error(f"Failed to play audio data: {e}")
            time.sleep(0.1)
        finally:
            audio_queue.task_done()
    logger.debug("audio player thread exited")


def save_output_to_file(audio_data: bytearray, filename: str) -> None:
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
        logger.error(f"Failed to save pcm file: {e}")
