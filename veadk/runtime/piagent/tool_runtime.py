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

"""Runtime support for Pi custom tools.

This module owns the per-turn localhost bridge and the generated Pi extension
that calls back into it. ADK tool collection/execution lives in tools_bridge.py.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import tempfile
from pathlib import Path
from typing import Any

from veadk.runtime.piagent.tools_bridge import PiToolBundle, PiToolSpec
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_REQUEST_BYTES = 1_000_000


class PiToolRuntime:
    """Per-turn Pi tool bridge plus generated extension file."""

    def __init__(self, bundle: PiToolBundle):
        self.bundle = bundle
        self.url = ""
        self.extension_path = ""
        self.tool_names: list[str] = []
        self._server: asyncio.AbstractServer | None = None
        self._token = secrets.token_urlsafe(24)
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None

    async def __aenter__(self) -> "PiToolRuntime":
        if not self.bundle.has_tools:
            return self

        self._server = await asyncio.start_server(
            self._handle_client,
            host="127.0.0.1",
            port=0,
        )
        socket = self._server.sockets[0]
        host, port = socket.getsockname()[:2]
        self.url = f"http://{host}:{port}"

        self._tmpdir = tempfile.TemporaryDirectory(prefix="veadk-piagent-tools-")
        extension = Path(self._tmpdir.name) / "veadk-tools.ts"
        extension.write_text(
            render_extension(self.bundle.specs, self.url, self._token),
            encoding="utf-8",
        )
        self.extension_path = str(extension)
        self.tool_names = [spec.name for spec in self.bundle.specs]
        logger.info(f"piagent: generated tool extension for {self.tool_names}")
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    @property
    def enabled(self) -> bool:
        return bool(self.extension_path and self.tool_names)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None

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
            except Exception:  # noqa: BLE001
                pass

    async def _dispatch(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if request["method"] != "POST" or request["path"] != "/call":
            return 404, {"ok": False, "error": "not found"}
        auth = request["headers"].get("authorization", "")
        if auth != f"Bearer {self._token}":
            return 401, {"ok": False, "error": "unauthorized"}

        body = request["body"]
        tool_name = str(body.get("toolName") or "")
        args = body.get("args")
        if not isinstance(args, dict):
            args = {}

        executor = self.bundle.executors.get(tool_name)
        if executor is None:
            return 404, {"ok": False, "error": f"unknown tool: {tool_name}"}

        result = _tool_result_to_pi_result(await executor(args))
        return 200, {"ok": True, "result": result}


async def _read_http_json(reader: asyncio.StreamReader) -> dict[str, Any]:
    head = await reader.readuntil(b"\r\n\r\n")
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
    raw_body = await reader.readexactly(length) if length else b"{}"
    try:
        body = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as e:
        raise ValueError("invalid JSON request body") from e
    if not isinstance(body, dict):
        raise ValueError("request body must be a JSON object")
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


def render_extension(specs: list[PiToolSpec], bridge_url: str, token: str) -> str:
    registrations = "\n\n".join(_render_tool(spec) for spec in specs)
    return (
        'import { Type } from "typebox";\n\n'
        f"const BRIDGE_URL = {_js(bridge_url)};\n"
        f"const TOKEN = {_js(token)};\n\n"
        "async function callBridge(toolName, toolCallId, params, signal) {\n"
        "  const response = await fetch(`${BRIDGE_URL}/call`, {\n"
        '    method: "POST",\n'
        "    signal,\n"
        "    headers: {\n"
        '      "Authorization": `Bearer ${TOKEN}`,\n'
        '      "Content-Type": "application/json",\n'
        "    },\n"
        "    body: JSON.stringify({ toolName, toolCallId, args: params ?? {} }),\n"
        "  });\n"
        "  let data = {};\n"
        "  try { data = await response.json(); } catch (_) {}\n"
        "  if (!response.ok || !data.ok) {\n"
        "    throw new Error(data.error || `VeADK tool bridge failed: ${response.status}`);\n"
        "  }\n"
        "  return data.result ?? {\n"
        '    content: [{ type: "text", text: String(data.content ?? "") }],\n'
        "    details: data.details ?? {},\n"
        "  };\n"
        "}\n\n"
        "export default function (pi) {\n"
        f"{registrations}\n"
        "}\n"
    )


def _render_tool(spec: PiToolSpec) -> str:
    parameters = _schema_to_typebox(spec.parameters)
    return (
        "  pi.registerTool({\n"
        f"    name: {_js(spec.name)},\n"
        f"    label: {_js(spec.label)},\n"
        f"    description: {_js(spec.description)},\n"
        f"    parameters: {parameters},\n"
        "    async execute(toolCallId, params, signal, _onUpdate, _ctx) {\n"
        f"      return await callBridge({_js(spec.name)}, toolCallId, params, signal);\n"
        "    },\n"
        "  });"
    )


def _schema_to_typebox(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "Type.Object({})"

    for union_key in ("anyOf", "oneOf"):
        union_items = schema.get(union_key)
        if isinstance(union_items, list) and union_items:
            variants = ", ".join(_schema_to_typebox(item) for item in union_items)
            options = _type_options(schema.get("description"))
            return f"Type.Union([{variants}]{options})"

    if "const" in schema:
        options = _type_options(schema.get("description"))
        return f"Type.Literal({_js(schema['const'])}{options})"

    schema_type = schema.get("type")
    description = schema.get("description")
    options = _type_options(description)

    if isinstance(schema_type, list):
        variants = ", ".join(
            "Type.Null()" if item == "null" else _schema_to_typebox({"type": item})
            for item in schema_type
            if isinstance(item, str)
        )
        return f"Type.Union([{variants}]{options})" if variants else "Type.Any()"

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        literals = ", ".join(f"Type.Literal({_js(v)})" for v in enum_values)
        return f"Type.Union([{literals}]{options})"

    if schema_type == "string":
        return f"Type.String({options.lstrip(', ')})" if options else "Type.String()"
    if schema_type == "integer":
        return f"Type.Integer({options.lstrip(', ')})" if options else "Type.Integer()"
    if schema_type == "number":
        return f"Type.Number({options.lstrip(', ')})" if options else "Type.Number()"
    if schema_type == "boolean":
        return f"Type.Boolean({options.lstrip(', ')})" if options else "Type.Boolean()"
    if schema_type == "array":
        items = _schema_to_typebox(schema.get("items") or {})
        return f"Type.Array({items}{options})"
    if schema_type == "object" or "properties" in schema:
        return _object_schema_to_typebox(schema, options)
    return f"Type.Any({options.lstrip(', ')})" if options else "Type.Any()"


def _object_schema_to_typebox(schema: dict[str, Any], options: str) -> str:
    props = schema.get("properties")
    if not isinstance(props, dict):
        props = {}
    if not props and isinstance(schema.get("additionalProperties"), dict):
        value_type = _schema_to_typebox(schema["additionalProperties"])
        return f"Type.Record(Type.String(), {value_type}{options})"
    required = set(schema.get("required") or [])
    rendered: list[str] = []
    for name, subschema in props.items():
        expr = _schema_to_typebox(subschema)
        if name not in required:
            expr = f"Type.Optional({expr})"
        rendered.append(f"{_js_prop(str(name))}: {expr}")
    body = ", ".join(rendered)
    return f"Type.Object({{{body}}}{options})"


def _type_options(description: Any) -> str:
    if not description:
        return ""
    return f", {{ description: {_js(str(description))} }}"


def _js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _js_prop(name: str) -> str:
    if name.replace("_", "").isalnum() and (name[:1].isalpha() or name.startswith("_")):
        return name
    return _js(name)


def _tool_result_to_pi_result(value: Any) -> dict[str, Any]:
    """Normalize ADK tool output into the result shape expected by Pi tools."""

    if isinstance(value, dict) and isinstance(value.get("content"), list):
        result = dict(value)
        result.setdefault("details", {})
        return result

    if isinstance(value, str):
        text = value
        structured = {"result": value}
    else:
        structured = value
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            text = str(value)

    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
        "details": {},
        "isError": bool(isinstance(value, dict) and value.get("isError")),
    }
