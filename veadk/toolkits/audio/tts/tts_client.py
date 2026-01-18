import json
import uuid

import websockets

from veadk.toolkits.audio.tts.protocols import (
    MsgType,
    full_client_request,
    receive_message,
)

TTS_WS_URL = "wss://openspeech.bytedance.com/api/v1/tts/ws_binary"


async def tts_request(
    app_id: str,
    access_token: str,
    text: str,
    voice_type: str = "zh_female_meilinvyou_saturn_bigtts",
) -> bytes:
    APPID = app_id
    ACCESS_TOKEN = access_token
    VOICE_TYPE = voice_type
    CLUSTER = ""
    ENCODING = "wav"

    headers = {"Authorization": f"Bearer;{ACCESS_TOKEN}"}

    websocket = await websockets.connect(
        TTS_WS_URL, additional_headers=headers, max_size=10 * 1024 * 1024
    )
    audio_data = bytearray()

    try:
        cluster = (
            CLUSTER or "volcano_icl" if VOICE_TYPE.startswith("S_") else "volcano_tts"
        )
        request = {
            "app": {"appid": APPID, "token": ACCESS_TOKEN, "cluster": cluster},
            "user": {"uid": str(uuid.uuid4())},
            "audio": {"voice_type": VOICE_TYPE, "encoding": ENCODING},
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "operation": "submit",
            },
        }
        await full_client_request(websocket, json.dumps(request).encode())

        while True:
            msg = await receive_message(websocket)
            if msg.type == MsgType.AudioOnlyServer:
                audio_data.extend(msg.payload)
                if msg.sequence < 0:
                    break
    finally:
        await websocket.close()

    return bytes(audio_data)
