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

"""Runtime support for DeepSeek Harness native tool plugins."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from veadk.runtime.piagent.tools_bridge import PiToolBundle, PiToolSpec
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_REQUEST_BYTES = 1_000_000
_REQUEST_READ_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class DeepSeekHarnessToolRegistration:
    """Stable DSH tool registration input for one manager."""

    specs: tuple[PiToolSpec, ...]
    digest: str

    @property
    def has_tools(self) -> bool:
        return bool(self.specs)

    @classmethod
    def from_bundle(cls, bundle: PiToolBundle) -> DeepSeekHarnessToolRegistration:
        specs = tuple(bundle.specs)
        data = json.dumps(
            [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                    "original_name": spec.original_name,
                }
                for spec in specs
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        return cls(
            specs=specs,
            digest=hashlib.sha256(data.encode("utf-8")).hexdigest(),
        )


class DeepSeekHarnessToolServer:
    """Long-lived localhost bridge used by one DSH manager."""

    def __init__(
        self,
        *,
        server: asyncio.AbstractServer | None,
        url: str,
        token: str,
        tmpdir: tempfile.TemporaryDirectory[str],
        plugin_path: str,
        patch_path: str,
    ) -> None:
        self.url = url
        self.patch_path = patch_path
        self.plugin_path = plugin_path
        self._server = server
        self._token = token
        self._tmpdir = tmpdir
        self._active_bundle: PiToolBundle | None = None

    @classmethod
    async def create(
        cls,
        registration: DeepSeekHarnessToolRegistration,
        *,
        dsh_home: str,
    ) -> DeepSeekHarnessToolServer | None:
        if not registration.has_tools:
            return None

        token = secrets.token_urlsafe(24)
        server: asyncio.AbstractServer | None = None
        tmpdir: tempfile.TemporaryDirectory[str] | None = None
        try:
            instance = cls(
                server=None,
                url="",
                token=token,
                tmpdir=tempfile.TemporaryDirectory(
                    prefix="veadk-deepseek-harness-tools-"
                ),
                plugin_path="",
                patch_path="",
            )

            server = await asyncio.start_server(
                instance._handle_client,
                host="127.0.0.1",
                port=0,
            )
            socket = server.sockets[0]
            host, port = socket.getsockname()[:2]
            instance._server = server
            instance.url = f"http://{host}:{port}"
            tmpdir = instance._tmpdir
            plugin_dir = Path(tmpdir.name) / "profiles" / "node_modules" / "veadk-tools"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            plugin = plugin_dir / "index.mjs"
            patch = Path(tmpdir.name) / "veadk-dsh-tools.patch.yml"
            plugin.write_text(
                render_plugin(registration.specs, instance.url, token),
                encoding="utf-8",
            )
            patch.write_text(
                "- insert:\n"
                "    - id: veadk-tools\n"
                f"      name: {json.dumps(str(plugin), ensure_ascii=False)}\n",
                encoding="utf-8",
            )
            instance.plugin_path = str(plugin)
            instance.patch_path = str(patch)
            logger.info(
                "deepseek_harness: generated DSH tool plugin for %s",
                [spec.name for spec in registration.specs],
            )
            return instance
        except Exception:
            if server is not None:
                server.close()
                await server.wait_closed()
            if tmpdir is not None:
                tmpdir.cleanup()
            raise

    def activate(self, bundle: PiToolBundle) -> None:
        self._active_bundle = bundle

    def deactivate(self) -> None:
        self._active_bundle = None

    def close_now(self) -> None:
        if self._server is not None:
            self._server.close()
        self._tmpdir.cleanup()

    async def wait_closed(self) -> None:
        if self._server is not None:
            await self._server.wait_closed()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request = await _read_http_json(reader)
            status, payload = await self._dispatch(request)
            await _write_json_response(writer, status, payload)
        except Exception as e:  # noqa: BLE001 - bridge protocol failures
            await _write_json_response(writer, 500, {"ok": False, "error": str(e)})
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "deepseek_harness: failed to close tool bridge writer: %s",
                    type(e).__name__,
                )

    async def _dispatch(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if request["method"] != "POST" or request["path"] != "/call":
            return 404, {"ok": False, "error": "not found"}
        auth = request["headers"].get("authorization", "")
        if auth != f"Bearer {self._token}":
            return 401, {"ok": False, "error": "unauthorized"}

        bundle = self._active_bundle
        if bundle is None:
            return 409, {"ok": False, "error": "no active VeADK tool invocation"}

        body = request["body"]
        tool_name = str(body.get("toolName") or "")
        args = body.get("args")
        if not isinstance(args, dict):
            args = {}

        executor = bundle.executors.get(tool_name)
        if executor is None:
            return 404, {"ok": False, "error": f"unknown tool: {tool_name}"}

        tool_call_id = str(body.get("toolCallId") or "")
        result = await executor(args, tool_call_id)
        return 200, {"ok": True, "result": _tool_result_to_text(result)}


async def _read_http_json(reader: asyncio.StreamReader) -> dict[str, Any]:
    head = await asyncio.wait_for(
        reader.readuntil(b"\r\n\r\n"),
        timeout=_REQUEST_READ_TIMEOUT_SECONDS,
    )
    if len(head) > _MAX_REQUEST_BYTES:
        raise ValueError("request headers are too large")
    header_text = head.decode("iso-8859-1")
    lines = header_text.split("\r\n")
    method, path, _version = lines[0].split(" ", 2)
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    length = int(headers.get("content-length", "0") or "0")
    if length > _MAX_REQUEST_BYTES:
        raise ValueError("request body is too large")
    raw_body = (
        await asyncio.wait_for(
            reader.readexactly(length),
            timeout=_REQUEST_READ_TIMEOUT_SECONDS,
        )
        if length
        else b"{}"
    )
    try:
        body = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as e:
        raise ValueError("invalid JSON request body") from e
    if not isinstance(body, dict):
        raise TypeError("request body must be a JSON object")
    return {"method": method, "path": path, "headers": headers, "body": body}


async def _write_json_response(
    writer: asyncio.StreamWriter, status: int, payload: dict[str, Any]
) -> None:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    reason = {
        200: "OK",
        400: "Bad Request",
        401: "Unauthorized",
        404: "Not Found",
        409: "Conflict",
        500: "Internal Server Error",
    }.get(status, "OK")
    header = (
        f"HTTP/1.1 {status} {reason}\r\n"
        "Content-Type: application/json; charset=utf-8\r\n"
        f"Content-Length: {len(data)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    writer.write(header + data)
    await writer.drain()


def render_plugin(
    specs: tuple[PiToolSpec, ...] | list[PiToolSpec], bridge_url: str, token: str
) -> str:
    registrations = "\n\n".join(_render_tool(spec) for spec in specs)
    return (
        "import { defineTool } from '@deepseek-ai/dsh-tools';\n\n"
        "export const name = 'veadk-tools';\n"
        "export const inject = ['tools'];\n\n"
        f"const BRIDGE_URL = {_js(bridge_url)};\n"
        f"const TOKEN = {_js(token)};\n\n"
        "async function callBridge(toolName, toolCallId, args, signal) {\n"
        "  const response = await fetch(`${BRIDGE_URL}/call`, {\n"
        "    method: 'POST',\n"
        "    signal,\n"
        "    headers: {\n"
        "      Authorization: `Bearer ${TOKEN}`,\n"
        "      'Content-Type': 'application/json',\n"
        "    },\n"
        "    body: JSON.stringify({ toolName, toolCallId, args: args ?? {} }),\n"
        "  });\n"
        "  let data = {};\n"
        "  try { data = await response.json(); } catch (_) {}\n"
        "  if (!response.ok || !data.ok) {\n"
        "    throw new Error(data.error || `VeADK tool bridge failed: ${response.status}`);\n"
        "  }\n"
        "  return String(data.result ?? '');\n"
        "}\n\n"
        "export function apply(ctx) {\n"
        f"{registrations}\n"
        "}\n"
    )


def _render_tool(spec: PiToolSpec) -> str:
    parameters = _schema_to_dsh_parameters(spec.parameters)
    return (
        "  ctx.tools.register(defineTool({\n"
        f"    name: {_js(spec.name)},\n"
        f"    description: {_js(spec.description)},\n"
        f"    parameters: {_js(parameters)},\n"
        "    output: {\n"
        "      schema: { type: 'string' },\n"
        "      render: (_args, value) => [{ type: 'text', text: value }],\n"
        "    },\n"
        "    async execute(args, exec) {\n"
        f"      return await callBridge({_js(spec.name)}, String(exec.callId), args, exec.signal);\n"
        "    },\n"
        "  }));"
    )


def _schema_to_dsh_parameters(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    required = set(schema.get("required") or [])
    rendered: dict[str, Any] = {}
    for name, prop_schema in properties.items():
        prop = _schema_to_dsh_value(prop_schema)
        if name in required:
            prop["required"] = True
        rendered[str(name)] = prop
    return rendered


def _schema_to_dsh_value(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"type": "json"}

    for union_key in ("oneOf", "anyOf"):
        union_items = schema.get(union_key)
        if isinstance(union_items, list) and union_items:
            return {
                **_annotations(schema),
                "oneOf": [_schema_to_dsh_value(item) for item in union_items],
            }

    if "const" in schema:
        value_type = _json_value_type(schema["const"])
        return {**_annotations(schema), "type": value_type, "const": schema["const"]}

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        non_null = [item for item in schema_type if item != "null"]
        if len(non_null) == 1:
            schema_type = non_null[0]
        else:
            return {"type": "json", **_annotations(schema)}

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        value_type = _json_value_type(enum_values[0])
        return {**_annotations(schema), "type": value_type, "enum": enum_values}

    if schema_type in {"string", "number", "integer", "boolean", "null"}:
        return {"type": schema_type, **_annotations(schema)}
    if schema_type == "array":
        return {
            "type": "array",
            "items": _schema_to_dsh_value(schema.get("items") or {}),
            **_annotations(schema),
        }
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        required = set(schema.get("required") or [])
        rendered = {}
        for name, prop_schema in properties.items():
            prop = _schema_to_dsh_value(prop_schema)
            if name in required:
                prop["required"] = True
            rendered[str(name)] = prop
        result = {
            "type": "object",
            "properties": rendered,
            **_annotations(schema),
        }
        if "additionalProperties" in schema:
            additional = schema["additionalProperties"]
            if isinstance(additional, dict):
                result["additionalProperties"] = _schema_to_dsh_value(additional)
            else:
                result["additionalProperties"] = bool(additional)
        return result
    return {"type": "json", **_annotations(schema)}


def _annotations(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        key: schema[key]
        for key in ("description", "title", "default", "examples")
        if key in schema
    }


def _json_value_type(value: Any) -> str:
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return "json"


def _tool_result_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        if hasattr(value, "model_dump"):
            value = value.model_dump()
    except Exception:  # noqa: BLE001
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        return str(value)


def _js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
