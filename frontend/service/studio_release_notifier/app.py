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

"""Authenticated release notifications for every group joined by the app bot."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
import tos
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool


class Release(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    changelog: list[str] | str
    date: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}$")

    @field_validator("changelog")
    @classmethod
    def validate_changelog(cls, value: list[str] | str) -> list[str]:
        values = [value] if isinstance(value, str) else value
        items = [
            part.strip() for item in values for part in re.split(r"[;；\n]+", item)
        ]
        items = [item for item in items if item]
        if not items or len(items) > 50 or sum(map(len, items)) > 6000:
            raise ValueError(
                "Changelog must contain 1–50 items and at most 6000 characters"
            )
        return items


def escape_markdown(value: str) -> str:
    value = html.escape(value)
    return re.sub(r"([*~`\[\]\\])", lambda match: f"&#{ord(match[0])};", value)


def build_card(release: Release, *, preview: bool = False) -> dict[str, Any]:
    header: dict[str, Any] = {
        "template": "blue",
        "title": {"tag": "plain_text", "content": "Studio · Release Note"},
        "subtitle": {
            "tag": "plain_text",
            "content": f"{release.version}  ·  {release.date}",
        },
    }
    elements: list[dict[str, Any]] = [
        {
            "tag": "column_set",
            "flex_mode": "none",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "background_style": "blue-50",
                    "padding": "12px",
                    "vertical_spacing": "8px",
                    "elements": [
                        {"tag": "markdown", "content": "**本次更新**"},
                        {
                            "tag": "markdown",
                            "content": "\n".join(
                                f"- {escape_markdown(item)}"
                                for item in release.changelog
                            ),
                        },
                    ],
                }
            ],
        }
    ]
    if preview:
        header["text_tag_list"] = [
            {
                "tag": "text_tag",
                "text": {"tag": "plain_text", "content": "预览示例"},
                "color": "blue",
            }
        ]
        elements.append(
            {
                "tag": "markdown",
                "text_size": "notation",
                "content": "<font color='grey'>版本与更新内容仅用于样式预览，不代表真实发版</font>",
            }
        )
    return {
        "schema": "2.0",
        "config": {
            "width_mode": "default",
            "summary": {
                "content": f"Studio {release.version} · {'样式预览' if preview else '本次更新'}"
            },
        },
        "header": header,
        "body": {
            "direction": "vertical",
            "padding": "12px",
            "vertical_spacing": "12px",
            "elements": elements,
        },
    }


class Feishu:
    def __init__(self) -> None:
        self.client = httpx.Client(
            base_url="https://open.feishu.cn/open-apis/", timeout=20
        )
        data = self.call(
            "POST",
            "auth/v3/tenant_access_token/internal",
            json={
                "app_id": os.environ["FEISHU_APP_ID"],
                "app_secret": os.environ["FEISHU_APP_SECRET"],
            },
        )
        self.client.headers["Authorization"] = f"Bearer {data['tenant_access_token']}"

    def call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu API error code {data.get('code')}")
        return data

    def groups(self) -> list[str]:
        groups: set[str] = set()
        page = ""
        seen: set[str] = set()
        while True:
            data = self.call(
                "GET", "im/v1/chats", params={"page_size": 100, "page_token": page}
            )["data"]
            groups.update(item["chat_id"] for item in data.get("items", []))
            if not data.get("has_more"):
                return sorted(groups)
            page = data.get("page_token", "")
            if not page or page in seen:
                raise RuntimeError("Invalid Feishu pagination cursor")
            seen.add(page)

    def send(
        self, recipient: str, card: dict[str, Any], key: str, *, direct: bool = False
    ) -> str:
        data = self.call(
            "POST",
            "im/v1/messages",
            params={"receive_id_type": "open_id" if direct else "chat_id"},
            json={
                "receive_id": recipient,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
                "uuid": key,
            },
        )
        return data["data"]["message_id"]


class Store:
    def __init__(self) -> None:
        credentials = json.loads(Path("/var/run/secrets/iam/credential").read_text())
        region = os.environ["NOTIFIER_TOS_REGION"]
        self.client = tos.TosClientV2(
            credentials["access_key_id"],
            credentials["secret_access_key"],
            security_token=credentials["session_token"],
            endpoint=f"tos-{region}.volces.com",
            region=region,
        )
        self.bucket = os.environ["NOTIFIER_TOS_BUCKET"]

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            response = self.client.get_object(
                self.bucket, f"veadk/studio/release-notifications/{key}.json"
            )
        except tos.exceptions.TosServerError as error:
            if error.status_code == 404:
                return None
            raise
        return json.loads(response.read())

    def put(self, key: str, value: dict[str, Any], *, create: bool = False) -> bool:
        try:
            self.client.put_object(
                self.bucket,
                f"veadk/studio/release-notifications/{key}.json",
                content=json.dumps(value).encode(),
                content_type="application/json",
                forbid_overwrite=create,
            )
            return True
        except tos.exceptions.TosServerError as error:
            if create and error.status_code == 409:
                return False
            raise


def broadcast(release: Release, bot: Feishu, store: Store) -> dict[str, Any]:
    key = hashlib.sha256(release.version.encode()).hexdigest()
    payload = release.model_dump()
    manifest = store.get(key)
    if manifest is None:
        groups = bot.groups()
        if not groups:
            raise HTTPException(409, "Bot has not joined any groups")
        store.put(key, {"release": payload, "groups": groups}, create=True)
        manifest = store.get(key)
    if manifest is None:
        raise RuntimeError("Release record was not persisted")
    if manifest["release"] != payload:
        raise HTTPException(409, "Version already registered with different content")
    results = []
    card = build_card(release)
    for group in manifest["groups"]:
        delivery = f"{key}/{group}"
        try:
            state = store.get(delivery)
            if state and state.get("message_id"):
                results.append({"chat_id": group, "status": "already_sent"})
                continue
            if state is None:
                store.put(delivery, {"started": time.time()}, create=True)
                state = store.get(delivery)
            if state is None:
                raise RuntimeError("Delivery record was not persisted")
            # Feishu deduplicates UUIDs for one hour. Ambiguous old attempts need review.
            if time.time() - state["started"] > 3500:
                results.append({"chat_id": group, "status": "needs_review"})
                continue
            uuid = hashlib.sha256(delivery.encode()).hexdigest()[:40]
            message = bot.send(group, card, uuid)
            store.put(delivery, {**state, "message_id": message})
            results.append({"chat_id": group, "status": "sent"})
        except (httpx.HTTPError, RuntimeError, tos.exceptions.TosError):
            results.append({"chat_id": group, "status": "failed"})
    return {
        "ok": all(item["status"] in {"sent", "already_sent"} for item in results),
        "version": release.version,
        "deliveries": results,
    }


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def authenticate(request: Request, call_next: Any) -> Any:
    from fastapi.responses import JSONResponse

    expected = os.environ.get("STUDIO_RELEASE_WEBHOOK_KEY", "")
    supplied = request.headers.get("x-api-key", "")
    if len(expected) < 32 or not hmac.compare_digest(
        expected.encode(), supplied.encode()
    ):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/readyz")
def ready() -> dict[str, bool]:
    Store().get("health")
    return {"ok": True}


@app.get("/groups")
def groups() -> dict[str, Any]:
    bot = Feishu()
    try:
        return {"groups": bot.groups()}
    finally:
        bot.client.close()


def deliver(release: Release, preview: bool) -> dict[str, Any]:
    bot = Feishu()
    try:
        if preview:
            recipient = os.environ.get("NOTIFIER_PREVIEW_USER_ID", "")
            if not recipient:
                raise HTTPException(409, "Preview recipient is not configured")
            uuid = hashlib.sha256(
                f"preview/{release.model_dump_json()}".encode()
            ).hexdigest()[:40]
            return {
                "ok": True,
                "message_id": bot.send(
                    recipient, build_card(release, preview=True), uuid, direct=True
                ),
            }
        return broadcast(release, bot, Store())
    finally:
        bot.client.close()


@app.post("/release")
@app.post("/preview")
async def notify(request: Request) -> Any:
    from fastapi.responses import JSONResponse
    from pydantic import ValidationError

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 32_000:
            raise HTTPException(413, "Request is too large")
    try:
        release = Release.model_validate_json(body)
    except ValidationError:
        raise HTTPException(422, "Invalid version, date or changelog") from None
    try:
        result = await run_in_threadpool(
            deliver, release, request.url.path == "/preview"
        )
    except (httpx.HTTPError, RuntimeError, tos.exceptions.TosError):
        raise HTTPException(
            502, "Notification dependency failed; retry with the same payload"
        ) from None
    return JSONResponse(result, status_code=200 if result["ok"] else 502)
