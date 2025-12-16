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

import contextlib
import uuid
import gzip
import json
from . import protocol
from typing import Any, AsyncIterator, Optional
from google.genai.live import AsyncLive, AsyncSession
from google.genai import _common
import google.genai.types as types
from veadk.types import RealtimeVoiceConnectConfig
from veadk.config import getenv, settings

try:
    from websockets.asyncio.client import connect as ws_connect
except ModuleNotFoundError:
    # This try/except is for TAP, mypy complains about it which is why we have the type: ignore
    from websockets.client import connect as ws_connect  # type: ignore

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class ProtocolEvents:
    ASR_INFO = 450
    ASR_RESPONSE = 451
    ASR_ENDED = 459
    TTS_SENTENCE_START = 350
    TTS_RESPONSE = 352
    TTS_SENTENCE_END = 351
    TTS_ENDED = 359
    USAGE_RESPONSE = 154
    CHAT_RESPONSE = 550
    CHAT_ENDED = 559


class ProtocolConstants:
    RESOURCE_ID = "volc.speech.dialog"
    APP_KEY = "PlgvMymc7f3tQnJ6"
    DEFAULT_SPEAKER = "zh_male_yunzhou_jupiter_bigtts"
    DEFAULT_SYSTEM_ROLE = (
        "You use a lively female voice, have an outgoing personality, and love life."
    )


class RequestConstants:
    REQ_ASR_END_SMOOTH_WINDOW_MS = 1500
    REQ_TTS_CHANNEL = 1
    REQ_TTS_SAMPLE_RATE = 24000
    REQ_DIALOG_BOT_NAME = "doubao"
    REQ_DIALOG_SPEAKING_STYLE = "Your speaking style is concise and clear, with a moderate pace and natural intonation."
    REQ_DIALOG_AUDIT_RESPONSE = "Support customize security audit response scripts。"
    REQ_DIALOG_RECV_TIMEOUT = 10


class DoubaoAsyncSession(AsyncSession):
    """[Preview] AsyncSession."""

    async def send_realtime_input(
        self,
        *,
        media: Optional[types.BlobImageUnionDict] = None,
        audio: Optional[types.BlobOrDict] = None,
        audio_stream_end: Optional[bool] = None,
        video: Optional[types.BlobImageUnionDict] = None,
        text: Optional[str] = None,
        activity_start: Optional[types.ActivityStartOrDict] = None,
        activity_end: Optional[types.ActivityEndOrDict] = None,
    ) -> None:
        """Send realtime input to the model, only send one argument per call.

        Use `send_realtime_input` for realtime audio chunks and video
        frames(images).

        With `send_realtime_input` the api will respond to audio automatically
        based on voice activity detection (VAD).

        `send_realtime_input` is optimized for responsivness at the expense of
        deterministic ordering. Audio and video tokens are added to the
        context when they become available.

        Args:
          media: A `Blob`-like object, the realtime media to send.

        Example:

        .. code-block:: python

          from pathlib import Path

          from google import genai
          from google.genai import types

          import PIL.Image

          import os

          if os.environ.get('GOOGLE_GENAI_USE_VERTEXAI'):
            MODEL_NAME = 'gemini-2.0-flash-live-preview-04-09'
          else:
            MODEL_NAME = 'gemini-live-2.5-flash-preview';


          client = genai.Client()

          async with client.aio.live.connect(
              model=MODEL_NAME,
              config={"response_modalities": ["TEXT"]},
          ) as session:
            await session.send_realtime_input(
                media=PIL.Image.open('image.jpg'))

            audio_bytes = Path('audio.pcm').read_bytes()
            await session.send_realtime_input(
                media=types.Blob(data=audio_bytes, mime_type='audio/pcm;rate=16000'))

            async for msg in session.receive():
              if msg.text is not None:
                print(f'{msg.text}')
        """
        kwargs: _common.StringDict = {}
        if media is not None:
            kwargs["media"] = media
        if audio is not None:
            kwargs["audio"] = audio
        if audio_stream_end is not None:
            kwargs["audio_stream_end"] = audio_stream_end
        if video is not None:
            kwargs["video"] = video
        if text is not None:
            kwargs["text"] = text
        if activity_start is not None:
            kwargs["activity_start"] = activity_start
        if activity_end is not None:
            kwargs["activity_end"] = activity_end

        if len(kwargs) != 1:
            raise ValueError(
                f"Only one argument can be set, got {len(kwargs)}:"
                f" {list(kwargs.keys())}"
            )

        task_request = bytearray(
            protocol.generate_header(
                message_type=protocol.CLIENT_AUDIO_ONLY_REQUEST,
                serial_method=protocol.NO_SERIALIZATION,
            )
        )
        task_request.extend(int(200).to_bytes(4, "big"))
        task_request.extend((len(self.session_id)).to_bytes(4, "big"))
        task_request.extend(str.encode(self.session_id))
        payload_bytes = gzip.compress(media.data)
        task_request.extend(
            (len(payload_bytes)).to_bytes(4, "big")
        )  # payload size(4 bytes)
        task_request.extend(payload_bytes)
        await self._ws.send(task_request)

    async def receive(self) -> AsyncIterator[types.LiveServerMessage]:
        """Receive model responses from the server.

        The method will yield the model responses from the server. The returned
        responses will represent a complete model turn. When the returned message
        is function call, user must call `send` with the function response to
        continue the turn.

        Yields:
          The model responses from the server.

        Example usage:

        .. code-block:: python

          client = genai.Client(api_key=API_KEY)

          async with client.aio.live.connect(model='...') as session:
            await session.send(input='Hello world!', end_of_turn=True)
            async for message in session.receive():
              print(message)
        """
        # TODO(b/365983264) Handle intermittent issues for the user.
        while result := await self._receive():
            # todo
            # if result.server_content and result.server_content.turn_complete:
            #   yield result
            #   break
            yield result

    async def _receive(self) -> types.LiveServerMessage:
        try:
            raw_response = await self._ws.recv(decode=False)
        except TypeError:
            raw_response = await self._ws.recv()  # type: ignore[assignment]
        if raw_response:
            try:
                response = protocol.parse_response(raw_response)
                logger.debug(f"receive llm response: {response}")
            except Exception:
                raise ValueError(f"Failed to parse raw response: {raw_response!r}")
        else:
            response = {}

        return self.convert_to_live_server_message(response)

    def convert_to_live_server_message(
        self, response: dict[str, Any]
    ) -> types.LiveServerMessage:
        """Converts a raw response to a LiveServerMessage.

        Args:
          response: The raw response from the server.

        Returns:
          The converted LiveServerMessage.
        """

        """
        msg = {
            "server_content": {
                "model_turn": {
                    "parts": [{
                        "inline_data": "",
                        "text": ""
                    }],
                    "role": "model"
                },
                "turn_complete": False,
                "interrupted": False,
                "input_transcription": {
                    "text": "",
                    "finished": False
                },
                "output_transcription": {
                    "text": "",
                    "finished": False
                }
            },
            "usage_metadata": {}
        }
        """
        parameter_model = types.LiveServerMessage()
        model_turn = {}
        server_content = {}
        usage_metadata = {}
        output_ranscription = {}

        if "event" in response and "payload_msg" in response:
            message = response.get("payload_msg")
            if response.get("event") == ProtocolEvents.ASR_INFO:
                # ASRInfo
                # The model recognizes the event returned by the first character in the audio stream,
                # which is used to interrupt the client's broadcast
                server_content["interrupted"] = True
            elif (
                response.get("event") == ProtocolEvents.ASR_RESPONSE
                and "results" in message
            ):
                # ASRResponse
                # The ASR Response model identifies the textual content of a user's speech
                server_content["inputTranscription"] = {
                    "text": message.get("results")[0].get("text"),
                    "finished": True,
                }
            elif response.get("event") == ProtocolEvents.ASR_ENDED:
                # ASREnded
                # The model considers the event where the user's speech ends
                logger.debug("ASREnded msg: %s", message)
            elif response.get("event") == ProtocolEvents.TTS_SENTENCE_START:
                # TTSSentenceStart
                logger.debug("TTSSentenceStart msg: %s", message)
            elif response.get("event") == ProtocolEvents.TTS_RESPONSE:
                # TTSResponse
                # Return the audio data generated by the model, and load the binary audio data into the payload
                model_turn["parts"] = [{"inlineData": {"data": message}}]
                server_content["modelTurn"] = model_turn
            elif response.get("event") == ProtocolEvents.TTS_SENTENCE_END:
                # TTSSentenceEnd
                logger.debug("TTSSentenceEnd msg: %s", message)
            elif response.get("event") == ProtocolEvents.USAGE_RESPONSE:
                # UsageResponse
                # Usage information corresponding to each round of interaction
                def sum_cached_tokens(d):
                    return sum(v for k, v in d.items() if k.startswith(("cached_")))

                usage_metadata["tool_use_prompt_token_count"] = (
                    lambda d: sum(d.values())
                )(message.get("usage"))
                usage_metadata["cached_content_token_count"] = sum_cached_tokens(
                    message.get("usage")
                )
            elif response.get("event") == ProtocolEvents.CHAT_RESPONSE:
                # ChatResponse
                # The text content replied by the model needs to be concatenated
                output_ranscription["text"] = message.get("content")
                server_content["output_transcription"] = output_ranscription
            elif response.get("event") == ProtocolEvents.CHAT_ENDED:
                # ChatEnded
                # End event of model reply text
                output_ranscription["finished"] = True
                server_content["output_transcription"] = output_ranscription
            elif response.get("event") == ProtocolEvents.TTS_ENDED:
                # TTSEnded
                # End event of synthesized audio
                server_content["turnComplete"] = True

        return types.LiveServerMessage._from_response(
            response={"serverContent": server_content, "usageMetadata": usage_metadata},
            kwargs=parameter_model.model_dump(),
        )


class DoubaoAsyncLive(AsyncLive):
    """[Preview] AsyncLive for doubao realtime voice model."""

    @contextlib.asynccontextmanager
    async def connect(
        self,
        *,
        model: str,
        config: Optional[types.LiveConnectConfigOrDict] = None,
    ) -> AsyncIterator[DoubaoAsyncSession]:
        """[Preview] Connect to the live server.

        Note: the live API is currently in preview.

        Usage:

        .. code-block:: python

          client = genai.Client(api_key=API_KEY)
          config = {}
          async with client.aio.live.connect(model='...', config=config) as session:
            await session.send_client_content(
              turns=types.Content(
                role='user',
                parts=[types.Part(text='hello!')]
              ),
              turn_complete=True
            )
            async for message in session.receive():
              print(message)

        Args:
          model: The model to use for the live session.
          config: The configuration for the live session.
          **kwargs: additional keyword arguments.

        Yields:
          An AsyncSession object.
        """
        # TODO(b/404946570): Support per request http options.
        if isinstance(config, dict):
            config = RealtimeVoiceConnectConfig(**config)

        api_key = settings.realtime_model.api_key
        api_base = settings.realtime_model.api_base
        app_id = getenv("MODEL_REALTIME_APP_ID")
        speaker = getenv("MODEL_REALTIME_TTS_SPEAKER", "zh_male_yunzhou_jupiter_bigtts")

        system_role = "You use a lively female voice, have an outgoing personality, and love life."
        if (
            config
            and hasattr(config, "system_instruction")
            and config.system_instruction
            and config.system_instruction.parts
        ):
            system_role = config.system_instruction.parts[0].text

        headers = {
            "X-Api-App-ID": app_id,
            "X-Api-Access-Key": api_key,
            "X-Api-Resource-Id": ProtocolConstants.RESOURCE_ID,  # fixed value
            "X-Api-App-Key": ProtocolConstants.APP_KEY,  # fixed value
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }

        start_session_req = {
            "asr": {
                "extra": {
                    "end_smooth_window_ms": RequestConstants.REQ_ASR_END_SMOOTH_WINDOW_MS,
                },
            },
            "tts": {
                "speaker": speaker,
                "audio_config": {
                    "channel": RequestConstants.REQ_TTS_CHANNEL,
                    "format": "pcm_s16le",  # default: pcm_f32le
                    "sample_rate": RequestConstants.REQ_TTS_SAMPLE_RATE,
                },
            },
            "dialog": {
                "bot_name": RequestConstants.REQ_DIALOG_BOT_NAME,
                "system_role": system_role,
                "speaking_style": RequestConstants.REQ_DIALOG_SPEAKING_STYLE,
                "extra": {
                    "strict_audit": False,
                    "audit_response": RequestConstants.REQ_DIALOG_AUDIT_RESPONSE,
                    "recv_timeout": RequestConstants.REQ_DIALOG_RECV_TIMEOUT,
                    "input_mod": "audio",
                },
            },
        }

        async with ws_connect(
            api_base, additional_headers=headers, **self._api_client._websocket_ssl_ctx
        ) as ws:
            logid = ws.response.headers.get("X-Tt-Logid")
            logger.info(f"dialog server response logid: {logid}")

            # StartConnection request
            start_connection_request = bytearray(protocol.generate_header())
            start_connection_request.extend(int(1).to_bytes(4, "big"))
            payload_bytes = str.encode("{}")
            payload_bytes = gzip.compress(payload_bytes)
            start_connection_request.extend((len(payload_bytes)).to_bytes(4, "big"))
            start_connection_request.extend(payload_bytes)

            await ws.send(start_connection_request)

            try:
                # websockets 14.0+
                raw_response = await ws.recv()
                logger.info(
                    f"StartConnection response: {protocol.parse_response(raw_response)}"
                )
                response_result = protocol.parse_response(raw_response)
                session_id = response_result.get("session_id")
                recv_timeout = 120
                mod = "audio"
                # Expanding this parameter can maintain silence for a period of time,
                # mainly used for text mode, with a parameter range of [10, 120]
                start_session_req["dialog"]["extra"]["recv_timeout"] = recv_timeout
                # This parameter can remain silent for a period of time in either text or audio_file mode
                start_session_req["dialog"]["extra"]["input_mod"] = mod
                # StartSession request
                request_params = start_session_req
                payload_bytes = str.encode(json.dumps(request_params))
                payload_bytes = gzip.compress(payload_bytes)
                start_session_request = bytearray(protocol.generate_header())
                start_session_request.extend(int(100).to_bytes(4, "big"))
                start_session_request.extend((len(session_id)).to_bytes(4, "big"))
                start_session_request.extend(str.encode(session_id))
                start_session_request.extend((len(payload_bytes)).to_bytes(4, "big"))
                start_session_request.extend(payload_bytes)
                await ws.send(start_session_request)
                response = await ws.recv()

                logger.info(
                    f"StartSession response: {protocol.parse_response(response)}"
                )
            except TypeError:
                raw_response = await ws.recv()  # type: ignore[assignment]
            yield DoubaoAsyncSession(
                api_client=self._api_client,
                websocket=ws,
                session_id=session_id,
            )
