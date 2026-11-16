# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Cold-start-safe declarations for Studio's canonical VeADK built-in tools."""

from __future__ import annotations

from typing import Any


BUILTIN_TOOL_DECLARATIONS: dict[str, tuple[str, dict[str, Any]]] = {
    "calculator": (
        "Evaluate a numeric arithmetic expression safely.\n\nUse this "
        "tool for arithmetic, percentages, powers, roots, logarithms, "
        "and\nbasic trigonometry. Named constants ``pi`` and ``e`` and "
        "the functions\n``abs``, ``round``, ``min``, ``max``, ``sqrt``, "
        "``log``, ``log10``,\n``exp``, ``sin``, ``cos``, ``tan``, ``floor``, "
        "and ``ceil`` are supported.\n\nArgs:\n    expression: The arithmetic "
        'expression, for example ``"(1 + 2) * 3"``.\n    precision: '
        "Decimal places for a floating-point result (0-15).\n\nReturns:\n"
        "    A dict with ``expression`` and ``result``. On invalid input, "
        "a dict with\n    an ``error`` key.",
        {
            "additionalProperties": False,
            "properties": {
                "expression": {"title": "Expression", "type": "string"},
                "precision": {"default": 10, "title": "Precision", "type": "integer"},
            },
            "required": ["expression"],
            "title": "calculatorParams",
            "type": "object",
        },
    ),
    "coding": (
        "Create code with the pre-configured OpenCode AgentKit sandbox.",
        {
            "additionalProperties": False,
            "properties": {
                "timeout": {"default": 900, "title": "Timeout", "type": "integer"},
                "workflow_prompt": {"title": "Workflow Prompt", "type": "string"},
            },
            "required": ["workflow_prompt"],
            "title": "codingParams",
            "type": "object",
        },
    ),
    "datetime": (
        "Work with dates and times, including timezone conversions.\n"
        "\nUse this tool for the current time, parsing or formatting "
        "a timestamp,\nconverting a timestamp between timezones, computing "
        "the difference between\ntwo timestamps, or adding a duration. "
        "Timestamps without an explicit offset\nuse ``timezone`` (default "
        "UTC).\n\nArgs:\n    action: One of ``now``, ``parse``, ``format``, "
        "``convert``, ``diff``,\n        ``add``.\n    value: The primary "
        "date/time string for ``parse``, ``format``,\n        ``convert``, "
        "``diff``, and ``add``.\n    value2: The second date/time string "
        "for ``diff``.\n    timezone: IANA timezone name (for example "
        "``Asia/Shanghai``) used when\n        ``value`` has no offset. "
        "Defaults to UTC.\n    target_timezone: IANA timezone name to "
        "convert to (``convert`` only).\n    format: ``strftime`` format "
        "string (``format`` only).\n    amount: Numeric amount to add "
        "(``add`` only).\n    unit: One of ``seconds``, ``minutes``, "
        "``hours``, ``days``, ``weeks``\n        (``add`` only).\n\nReturns:\n"
        "    A dict with the requested fields. On invalid input, a dict "
        "with an\n    ``error`` key.",
        {
            "additionalProperties": False,
            "properties": {
                "action": {"title": "Action", "type": "string"},
                "amount": {
                    "anyOf": [{"type": "number"}, {"type": "null"}],
                    "default": None,
                    "title": "Amount",
                },
                "format": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Format",
                },
                "target_timezone": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Target Timezone",
                },
                "timezone": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Timezone",
                },
                "unit": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Unit",
                },
                "value": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Value",
                },
                "value2": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Value2",
                },
            },
            "required": ["action"],
            "title": "datetimeParams",
            "type": "object",
        },
    ),
    "doc_generate": (
        "Generate a document and attach it to the current conversation.\n"
        "\nArgs:\n    format: One of ``docx``, ``xlsx``, ``csv``, or "
        "``md`` (case-insensitive).\n    title: Document title. Rendered "
        "as the Word title and the Markdown\n        heading; ignored "
        "for CSV.\n    content: Markdown-ish body for ``docx``/``md``; "
        "raw CSV text fallback\n        for ``csv``. Supports ``#``-``###`` "
        "headings and ``-``/``*``/``+``\n        bullets for Word.\n "
        '   sheets: For ``xlsx``, a list of ``{"name": str, "rows": '
        "list[list]}``.\n    rows: For ``csv``, a list of rows. CSV output "
        "is plain UTF-8 without a\n        byte-order mark.\n    filename: "
        "Optional output filename; the correct extension is forced.\n"
        "    tool_context: Current ADK tool context used to save the "
        "artifact. When\n        omitted, the file is written to a temporary "
        'directory instead.\n\nReturns:\n    ``{"filename", "format", '
        '"size_bytes", "mime_type",\n    "artifact_saved", "path"}`` '
        'on success, or ``{"error"}`` on failure.',
        {
            "additionalProperties": False,
            "properties": {
                "content": {"default": "", "title": "Content", "type": "string"},
                "filename": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Filename",
                },
                "format": {"title": "Format", "type": "string"},
                "rows": {
                    "anyOf": [
                        {"items": {"items": {}, "type": "array"}, "type": "array"},
                        {"type": "null"},
                    ],
                    "default": None,
                    "title": "Rows",
                },
                "sheets": {
                    "anyOf": [
                        {
                            "items": {"additionalProperties": True, "type": "object"},
                            "type": "array",
                        },
                        {"type": "null"},
                    ],
                    "default": None,
                    "title": "Sheets",
                },
                "title": {"title": "Title", "type": "string"},
            },
            "required": ["format", "title"],
            "title": "doc_generateParams",
            "type": "object",
        },
    ),
    "document_parse": (
        "Parse a document into bounded plain text.\n\nAccepts a local "
        "file path or a public http(s) URL. The format is taken from\n"
        "``format`` when supplied, otherwise inferred from the file extension, "
        "then\nfrom the response ``Content-Type``, then from the file's magic "
        "bytes, then\nfrom an HTML sniff, and finally treated as UTF-8 "
        "text.\n\nArgs:\n    source: Local path or public http(s) URL.\n"
        "    format: Optional override: pdf, docx, xlsx, csv, txt, md, "
        "json, or html.\n    max_chars: Maximum characters returned (1,000-1,000,000).\n"
        '\nReturns:\n    ``{"format", "text", "truncated", "metadata"}`` '
        'on success, or\n    ``{"error"}`` on failure.',
        {
            "additionalProperties": False,
            "properties": {
                "format": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Format",
                },
                "max_chars": {
                    "default": 200000,
                    "title": "Max Chars",
                    "type": "integer",
                },
                "source": {"title": "Source", "type": "string"},
            },
            "required": ["source"],
            "title": "document_parseParams",
            "type": "object",
        },
    ),
    "get_city_weather": (
        "Retrieves the weather information of a given city. the args must in English",
        {
            "additionalProperties": False,
            "properties": {"city": {"title": "City", "type": "string"}},
            "required": ["city"],
            "title": "get_city_weatherParams",
            "type": "object",
        },
    ),
    "get_location_weather": (
        "Retrieves the weather information of a given city. the args must in English",
        {
            "additionalProperties": False,
            "properties": {"city": {"title": "City", "type": "string"}},
            "required": ["city"],
            "title": "get_location_weatherParams",
            "type": "object",
        },
    ),
    "http_request": (
        "Make an HTTP(S) request and return the status, headers, and "
        "body.\n\nUse this tool when you need to call an HTTP API or "
        "download a small\nresource. Private/internal addresses are blocked. "
        "Redirects are only\nfollowed when ``follow_redirects`` is true "
        "(at most three hops), and every\nhop is re-validated. Set a "
        "header value to ``env:NAME`` to read a secret\nfrom environment "
        "variable ``NAME`` without exposing it in the arguments.\n\nArgs:\n"
        "    url: The absolute http(s) URL to request.\n    method: One "
        "of GET, POST, PUT, PATCH, DELETE, HEAD (case-insensitive).\n"
        "    headers: Optional request headers. ``env:NAME`` values are "
        "resolved from\n        the environment.\n    params: Optional "
        "query parameters.\n    json_body: Optional JSON-serializable "
        "request body.\n    body: Optional raw string request body. Mutually "
        "exclusive with\n        ``json_body``.\n    timeout: Request "
        "timeout in seconds (1-120).\n    max_bytes: Maximum response "
        "body size in bytes (1,000-20,000,000).\n        Larger bodies "
        "are truncated and ``truncated`` is set to true.\n    follow_redirects: "
        "Whether to follow 301/302/303/307/308 redirects.\n\nReturns:\n"
        "    A dict with ``status_code``, ``url``, ``headers``, ``content_type``,\n"
        "    ``body``, ``bytes``, and ``truncated``. On failure, a dict "
        "with an\n    ``error`` key.",
        {
            "additionalProperties": False,
            "properties": {
                "body": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Body",
                },
                "follow_redirects": {
                    "default": False,
                    "title": "Follow Redirects",
                    "type": "boolean",
                },
                "headers": {
                    "anyOf": [
                        {"additionalProperties": {"type": "string"}, "type": "object"},
                        {"type": "null"},
                    ],
                    "default": None,
                    "title": "Headers",
                },
                "json_body": {"default": None, "title": "Json Body"},
                "max_bytes": {
                    "default": 5000000,
                    "title": "Max Bytes",
                    "type": "integer",
                },
                "method": {"default": "GET", "title": "Method", "type": "string"},
                "params": {
                    "anyOf": [
                        {"additionalProperties": True, "type": "object"},
                        {"type": "null"},
                    ],
                    "default": None,
                    "title": "Params",
                },
                "timeout": {"default": 30, "title": "Timeout", "type": "integer"},
                "url": {"title": "Url", "type": "string"},
            },
            "required": ["url"],
            "title": "http_requestParams",
            "type": "object",
        },
    ),
    "image_edit": (
        "Edit images in batch according to prompts and optional settings.\n"
        "\n"
        "Each item in `params` describes a single image-edit request.\n"
        "\n"
        "Args:\n"
        "    params (list[dict]):\n"
        "        A list of image editing requests. Each item supports:\n"
        "\n"
        "        Required:\n"
        "            - origin_image (str):\n"
        "                The URL or Base64 string of the original image to "
        "edit.\n"
        "                Example:\n"
        '                  * URL: "https://example.com/image.png"\n'
        '                  * Base64: "data:image/png;base64,<BASE64>"\n'
        "\n"
        "            - prompt (str):\n"
        "                The textual description/instruction for editing the "
        "image.\n"
        "                Supports English and Chinese.\n"
        "\n"
        "        Optional:\n"
        "            - image_name (str):\n"
        "                Name/identifier for the generated image.\n"
        "\n"
        "            - response_format (str):\n"
        "                Format of the returned image.\n"
        '                * "url": JPEG link (default)\n'
        '                * "b64_json": Base64 string in JSON\n'
        "\n"
        "            - guidance_scale (float):\n"
        "                How strongly the prompt affects the result.\n"
        "                Range: [1.0, 10.0], default 2.5.\n"
        "\n"
        "            - watermark (bool):\n"
        "                Whether to add watermark.\n"
        "                Default: True.\n"
        "\n"
        "            - seed (int):\n"
        "                Random seed for reproducibility.\n"
        "                Range: [-1, 2^31-1], default -1 (random).\n"
        "\n"
        "Returns:\n"
        "    Dict: API response containing generated image metadata.\n"
        "    Example:\n"
        "    {\n"
        '        "status": "success",\n'
        '        "success_list": [{"image_name": ""}],\n'
        '        "error_list": [{}]\n'
        "    }\n"
        "\n"
        "Notes:\n"
        "    - Uses SeedEdit 3.0 model.\n"
        "    - Provide the same `seed` for consistent outputs across runs.\n"
        "    - A high `guidance_scale` enforces stricter adherence to text "
        "prompt.",
        {
            "additionalProperties": False,
            "properties": {"params": {"items": {}, "title": "Params", "type": "array"}},
            "required": ["params"],
            "title": "image_editParams",
            "type": "object",
        },
    ),
    "image_generate": (
        "Generate images with Seedream 4.0 / 4.5 / 5.0\n"
        "\n"
        "Commit batch image generation requests via tasks.\n"
        "\n"
        "Args:\n"
        "    tasks (list[dict]):\n"
        "        A list of image-generation tasks. Each task is a dict.\n"
        "    timeout (int)\n"
        "        The timeout limit for the image generation task request, "
        "in seconds, with a default value of 600 seconds.\n"
        "    model_name (str):\n"
        "        Optional model name. If not specified, use the default "
        "model from environment.\n"
        "        If during execution, this tool encounters a model-related "
        "error (note that it must be a model-related error, otherwise do "
        "not perform this action), such as `ModelNotOpen`,\n"
        "        then after reminding about the relevant issue, you can "
        "execute this tool again and downgrade the model to the following "
        "models, passing this parameter:\n"
        "        - `doubao-seedream-5-0-260128`\n"
        "        - `doubao-seedream-4-5-251128`\n"
        "        - `doubao-seedream-4-0-250828`\n"
        "Per-task schema\n"
        "---------------\n"
        "Required:\n"
        "    - task_type (str):\n"
        "        One of:\n"
        '          * "multi_image_to_group"   # 多图生组图\n'
        '          * "single_image_to_group"  # 单图生组图\n'
        '          * "text_to_group"          # 文生组图\n'
        '          * "multi_image_to_single"  # 多图生单图\n'
        '          * "single_image_to_single" # 单图生单图\n'
        '          * "text_to_single"         # 文生单图\n'
        "    - prompt (str)\n"
        "        Text description of the desired image(s). 中文/English 均可。\n"
        '        若要指定生成图片的数量，请在prompt中添加"生成N张图片"，其中N为具体的数字。\n'
        "Optional:\n"
        "    - size (str)\n"
        "        指定生成图像的大小，有两种用法（二选一，不可混用）：\n"
        "        方式 1：分辨率级别\n"
        '            可选值: "1K", "2K", "4K"\n'
        "            模型会结合 prompt 中的语义推断合适的宽高比、长宽。\n"
        "        方式 2：具体宽高值\n"
        '            格式: "<宽度>x<高度>"，如 "2048x2048", "2384x1728"\n'
        "            约束:\n"
        "                * 总像素数范围: [1024x1024, 4096x4096]\n"
        "                * 宽高比范围: [1/16, 16]\n"
        "            推荐值:\n"
        "                - 1:1   → 2048x2048\n"
        "                - 4:3   → 2384x1728\n"
        "                - 3:4   → 1728x2304\n"
        "                - 16:9  → 2560x1440\n"
        "                - 9:16  → 1440x2560\n"
        "                - 3:2   → 2496x1664\n"
        "                - 2:3   → 1664x2496\n"
        "                - 21:9  → 3024x1296\n"
        '        默认值: "2048x2048"\n'
        "    - response_format (str)\n"
        '        Return format: "url" (default, URL 24h 过期) | "b64_json".\n'
        "    - watermark (bool)\n"
        "        Add watermark. Default: true.\n"
        '    - image (str | list[str])   # 仅"非文生图"需要。文生图请不要提供 image\n'
        "        Reference image(s) as URL or Base64.\n"
        '        * 生成"单图"的任务：传入 string（exactly 1 image）。\n'
        '        * 生成"组图"的任务：传入 array（2–10 images）。\n'
        "    - sequential_image_generation (str)\n"
        '        控制是否生成"组图"。Default: "disabled".\n'
        '        * 若要生成组图：必须设为 "auto"。\n'
        "    - max_images (int)\n"
        "        仅当生成组图时生效。控制模型能生成的最多张数，范围 [1, 15]， 不设置默认为15。\n"
        "        注意这个参数不等于生成的图片数量，而是模型最多能生成的图片数量。\n"
        "        在单图组图场景最多 14；多图组图场景需满足 (len(images)+max_images ≤ 15)。\n"
        "    - tools (list[dict])\n"
        "        工具配置，用于增强生成能力。目前支持联网搜索工具。\n"
        '        格式: [{"type": "web_search"}]\n'
        "        注意：仅文生图（text_to_single / text_to_group）场景支持此参数，\n"
        "        图生图场景（包含 image 参数）不支持使用 tools。\n"
        "    - output_format (str)\n"
        '        输出图片格式。枚举值: "png", "jpeg"。\n'
        '        默认值: "jpeg"（不传时模型默认）。\n'
        "        注意：仅 Seedream 5.0 支持该字段，存量模型指定会报错。\n"
        "Model 行为说明（如何由参数推断模式）\n"
        "---------------------------------\n"
        '1) 文生单图: 不提供 image 且 (S 未设置或 S="disabled") → 1 张图。\n'
        '2) 文生组图: 不提供 image 且 S="auto" → 组图，数量由 max_images 控制。\n'
        '3) 单图生单图: image=string 且 (S 未设置或 S="disabled") → 1 张图。\n'
        '4) 单图生组图: image=string 且 S="auto" → 组图，数量 ≤14。\n'
        '5) 多图生单图: image=array (2–10) 且 (S 未设置或 S="disabled") → 1 张图。\n'
        '6) 多图生组图: image=array (2–10) 且 S="auto" → 组图，需满足总数 ≤15。\n'
        "返回结果\n"
        "--------\n"
        "    Dict with generation summary.\n"
        "    Example:\n"
        "    {\n"
        '        "status": "success",\n'
        '        "success_list": [\n'
        '            {"image_name": "url"}\n'
        "        ],\n"
        '        "error_list": ["image_name"],\n'
        '        "error_detail_list": [\n'
        '            {"task_idx": 0, "error": {"code": "InvalidParameter", '
        '"message": "..."}}\n'
        "        ]\n"
        "    }\n"
        "Notes:\n"
        '- 组图任务必须 sequential_image_generation="auto"。\n'
        '- 如果想要指定生成组图的数量，请在prompt里添加数量说明，例如："生成3张图片"。\n'
        "- size 推荐使用 2048x2048 或表格里的标准比例，确保生成质量。",
        {
            "additionalProperties": False,
            "properties": {
                "model_name": {
                    "default": None,
                    "title": "Model Name",
                    "type": "string",
                },
                "tasks": {
                    "items": {"additionalProperties": True, "type": "object"},
                    "title": "Tasks",
                    "type": "array",
                },
                "timeout": {"default": 600, "title": "Timeout", "type": "integer"},
            },
            "required": ["tasks"],
            "title": "image_generateParams",
            "type": "object",
        },
    ),
    "image_transform": (
        "Apply ordered Pillow operations to an image and save the result.\n"
        "\n``source`` may be a local path or an http(s) URL. Operations "
        "are applied in\norder; each item is a dict with a ``type``:\n"
        "\n- ``resize``: ``width`` and/or ``height`` (positive ints). "
        "When only one\n  side is given the aspect ratio is preserved. "
        "With both sides and\n  ``keep_aspect`` true (default) the image "
        "fits inside the box.\n- ``crop``: ``left``, ``top``, ``right``, "
        "``bottom`` pixel coordinates.\n- ``rotate``: ``degrees`` (float), "
        "expanding the canvas and filling with\n  white (RGB) or transparency "
        "(RGBA).\n- ``flip``: ``direction`` equal to ``horizontal`` or "
        "``vertical``.\n- ``thumbnail``: ``max_size`` (positive int), "
        "preserving aspect ratio.\n- ``grayscale``: converts the image "
        "to grayscale.\n- ``convert``: ``format`` of ``png``, ``jpeg`` "
        "or ``webp``; the output\n  format is applied after every operation.\n"
        "\nArgs:\n    source: Local image path or public http(s) URL.\n"
        "    operations: Ordered list of operation dicts (at most 20).\n"
        "    output_format: png, jpeg or webp. Defaults to the source "
        "format when it\n        is png/jpeg/webp, otherwise png.\n  "
        "  quality: Encoder quality from 1 to 100 for jpeg/webp only.\n"
        "    filename: Optional output filename; sanitized with the right "
        "extension.\n    tool_context: Current ADK tool context used "
        "to save the result artifact.\n\nReturns:\n    A dict with filename, "
        "format, width, height, size_bytes, mime_type,\n    artifact_saved "
        "and path. On failure, a dict with an ``error`` key.",
        {
            "additionalProperties": False,
            "properties": {
                "filename": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Filename",
                },
                "operations": {
                    "items": {"additionalProperties": True, "type": "object"},
                    "title": "Operations",
                    "type": "array",
                },
                "output_format": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Output Format",
                },
                "quality": {"default": 90, "title": "Quality", "type": "integer"},
                "source": {"title": "Source", "type": "string"},
            },
            "required": ["source", "operations"],
            "title": "image_transformParams",
            "type": "object",
        },
    ),
    "image_understand": (
        "Describe one or more images in detail with a vision model.\n"
        "\nArgs:\n    images: Local image paths or public http(s) URLs "
        "(1 to 8 items).\n    prompt: What to ask about the images. The "
        "default requests a detailed\n        description covering objects, "
        "text, layout and notable details.\n    model_name: Optional "
        'vision model override.\n\nReturns:\n    ``{"text": ..., "model": '
        '...}`` on success, otherwise\n    ``{"error": ...}``.',
        {
            "additionalProperties": False,
            "properties": {
                "images": {
                    "items": {"type": "string"},
                    "title": "Images",
                    "type": "array",
                },
                "model_name": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Model Name",
                },
                "prompt": {
                    "default": "Describe the image in detail.",
                    "title": "Prompt",
                    "type": "string",
                },
            },
            "required": ["images"],
            "title": "image_understandParams",
            "type": "object",
        },
    ),
    "link_reader": (
        "Use this tool when you need to fetch content from web pages, PDFs, "
        "or Douyin videos.\n"
        "It retrieves the title and main content from the provided URLs.\n"
        "\n"
        'Examples: {"url_list": ["abc.com", "xyz.com"]}\n'
        "Args:\n"
        "    url_list (list[str]): A list of URLs to parse (maximum 3).\n"
        "Returns:\n"
        "    list[dict]: A list of dictionaries, each containing the title "
        "and content of the corresponding URL.",
        {
            "additionalProperties": False,
            "properties": {
                "url_list": {
                    "items": {"type": "string"},
                    "title": "Url List",
                    "type": "array",
                }
            },
            "required": ["url_list"],
            "title": "link_readerParams",
            "type": "object",
        },
    ),
    "mindmap_generate": (
        "Build a Mermaid mindmap and a deterministic SVG from a Markdown "
        "outline.\n\nHeadings (``#`` through ``######``) nest by level; "
        "``-``/``*``/``+`` bullets\nnest by two-space indentation. Blank "
        "lines and plain text are ignored.\n\nArgs:\n    title: Root "
        "node label.\n    markdown: Outline using headings and/or indented "
        "bullets.\n    filename: Optional base filename; ``.mmd`` and "
        "``.svg`` are generated.\n    tool_context: Current ADK tool "
        "context. When omitted, both files are\n        written to a "
        'temporary directory instead.\n\nReturns:\n    ``{"title", '
        '"mermaid", "mmd_filename", "svg_filename", "nodes",\n'
        '    "artifact_saved", "mmd_path", "svg_path"}`` on success, '
        'or\n    ``{"error"}`` on failure.',
        {
            "additionalProperties": False,
            "properties": {
                "filename": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Filename",
                },
                "markdown": {"title": "Markdown", "type": "string"},
                "title": {"title": "Title", "type": "string"},
            },
            "required": ["title", "markdown"],
            "title": "mindmap_generateParams",
            "type": "object",
        },
    ),
    "ocr": (
        "Transcribe text from an image with a vision model.\n\nArgs:\n"
        "    image: Local image path or public http(s) URL.\n    language: "
        "Expected text language, or ``auto`` to let the model decide.\n"
        "    model_name: Optional vision model override.\n\nReturns:\n"
        '    ``{"text": ..., "language": ..., "model": ...}`` on '
        'success, otherwise\n    ``{"error": ...}``.',
        {
            "additionalProperties": False,
            "properties": {
                "image": {"title": "Image", "type": "string"},
                "language": {"default": "auto", "title": "Language", "type": "string"},
                "model_name": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "title": "Model Name",
                },
            },
            "required": ["image"],
            "title": "ocrParams",
            "type": "object",
        },
    ),
    "parallel_web_search": (
        "Search queries from websites in parallel.\n"
        "\n"
        "Args:\n"
        "    queries: The queries to search. Each query will be "
        "searched in parallel.\n"
        "\n"
        "Returns:\n"
        "    A dict of query to result documents.",
        {
            "additionalProperties": False,
            "properties": {
                "queries": {
                    "items": {"type": "string"},
                    "title": "Queries",
                    "type": "array",
                }
            },
            "required": ["queries"],
            "title": "parallel_web_searchParams",
            "type": "object",
        },
    ),
    "ppt_generate": (
        "Create a real PPTX file and attach it to the current conversation.\n"
        "\n"
        "Plan the complete deck before calling this tool. ``deck_markdown`` "
        "uses a\n"
        "simple flat format to avoid complex nested arguments: start every "
        "content\n"
        "slide with ``## Slide title``; add one plain-text summary line "
        "followed by\n"
        "3-7 ``- bullet`` lines. Add an optional ``Sources: URL | URL`` line "
        "when\n"
        "external claims or assets are used. The title slide is added "
        "automatically.\n"
        "\n"
        "Args:\n"
        "    title: Audience-facing deck title.\n"
        "    deck_markdown: Ordered content slides in the flat Markdown "
        "format.\n"
        "    tool_context: Current ADK tool context used to save the "
        "result.\n"
        "    subtitle: Optional title-slide subtitle.\n"
        "    theme: Visual theme: blue, dark, warm, or green.\n"
        "    filename: Download filename ending in .pptx.\n"
        "\n"
        "Returns:\n"
        "    Metadata for the saved PowerPoint artifact.",
        {
            "additionalProperties": False,
            "properties": {
                "deck_markdown": {"title": "Deck Markdown", "type": "string"},
                "filename": {
                    "default": "presentation.pptx",
                    "title": "Filename",
                    "type": "string",
                },
                "subtitle": {"default": "", "title": "Subtitle", "type": "string"},
                "theme": {"default": "blue", "title": "Theme", "type": "string"},
                "title": {"title": "Title", "type": "string"},
            },
            "required": ["title", "deck_markdown"],
            "title": "ppt_generateParams",
            "type": "object",
        },
    ),
    "qrcode_generate": (
        "Generate a PNG QR code for text or a URL and save it.\n\nArgs:\n"
        "    content: Text or URL to encode (non-empty, at most 2000 "
        "characters).\n    filename: Output filename; a .png extension "
        "is enforced.\n    box_size: Pixels per QR module, from 1 to "
        "50.\n    border: Quiet-zone size in modules, from 0 to 20.\n"
        "    fill_color: Pillow color name or hex value for the dark "
        "modules.\n    back_color: Pillow color name or hex value for "
        "the background.\n    tool_context: Current ADK tool context "
        "used to save the result artifact.\n\nReturns:\n    A dict with "
        "filename, format, width, height, size_bytes, mime_type,\n   "
        " artifact_saved and path. On failure, a dict with an ``error`` "
        "key.",
        {
            "additionalProperties": False,
            "properties": {
                "back_color": {
                    "default": "white",
                    "title": "Back Color",
                    "type": "string",
                },
                "border": {"default": 4, "title": "Border", "type": "integer"},
                "box_size": {"default": 10, "title": "Box Size", "type": "integer"},
                "content": {"title": "Content", "type": "string"},
                "filename": {
                    "default": "qrcode.png",
                    "title": "Filename",
                    "type": "string",
                },
                "fill_color": {
                    "default": "black",
                    "title": "Fill Color",
                    "type": "string",
                },
            },
            "required": ["content"],
            "title": "qrcode_generateParams",
            "type": "object",
        },
    ),
    "run_code": (
        "Run code in a code sandbox and return the output.\n"
        "For C++ code, don't execute it directly, compile and execute via "
        "Python; write sources and object files to /tmp.\n"
        "\n"
        "Args:\n"
        "    code (str): The code to run.\n"
        "    language (str): The execution language. Use ``python3`` for code or "
        "``bash`` for shell scripts.\n"
        "    timeout (int, optional): The timeout in seconds for the code "
        "execution.\n"
        "        Defaults to 300 and must be between 1 and 300 seconds.\n"
        "    exec_dir (str, optional): Working directory for Bash execution. "
        "Defaults to ``/tmp``.\n"
        "    env (dict[str, str], optional): Environment variables for Bash "
        "execution.\n"
        "    hard_timeout (int, optional): Hard timeout for Bash execution. "
        "Defaults\n"
        "        to 300 and must be between 1 and 300 seconds.\n"
        "    max_output_length (int, optional): Maximum Bash output length. "
        "Defaults to 30000.\n"
        "\n"
        "Returns:\n"
        "    str: The output of the code execution.",
        {
            "additionalProperties": False,
            "properties": {
                "code": {"title": "Code", "type": "string"},
                "env": {
                    "anyOf": [
                        {"additionalProperties": {"type": "string"}, "type": "object"},
                        {"type": "null"},
                    ],
                    "default": None,
                    "title": "Env",
                },
                "exec_dir": {"default": "/tmp", "title": "Exec Dir", "type": "string"},
                "hard_timeout": {
                    "default": 300,
                    "title": "Hard Timeout",
                    "type": "integer",
                },
                "language": {"title": "Language", "type": "string"},
                "max_output_length": {
                    "default": 30000,
                    "title": "Max Output Length",
                    "type": "integer",
                },
                "timeout": {"default": 300, "title": "Timeout", "type": "integer"},
            },
            "required": ["code", "language"],
            "title": "run_codeParams",
            "type": "object",
        },
    ),
    "speech_to_text": (
        "Transcribe speech in an audio file into text.\n\nSupports local "
        "wav/mp3/ogg/opus files (up to 100 MB) and public http(s)\naudio "
        "URLs. The service auto-detects the spoken language.\n\nArgs:\n"
        "    audio: Local file path or public http(s) URL of the audio.\n"
        "    timeout: Request timeout in seconds, between 1 and 600.\n"
        "\nReturns:\n    A dict with ``text``, ``duration_ms``, ``utterances`` "
        "and ``log_id``,\n    or a dict with ``error`` when transcription "
        "fails.",
        {
            "additionalProperties": False,
            "properties": {
                "audio": {"title": "Audio", "type": "string"},
                "timeout": {"default": 300, "title": "Timeout", "type": "integer"},
            },
            "required": ["audio"],
            "title": "speech_to_textParams",
            "type": "object",
        },
    ),
    "text_to_speech": (
        "TTS provides users with the ability to convert text to speech, "
        "turning the text content of LLM into audio.\n"
        "Use this tool when you need to convert text content into audible "
        "speech.\n"
        "It transforms plain text into natural-sounding speech, as well as "
        "exporting the generated audio in pcm format.\n"
        "\n"
        "Args:\n"
        "    text: The text to convert.\n"
        "\n"
        "Returns:\n"
        "    A dict with the saved audio path.",
        {
            "additionalProperties": False,
            "properties": {"text": {"title": "Text", "type": "string"}},
            "required": ["text"],
            "title": "text_to_speechParams",
            "type": "object",
        },
    ),
    "vesearch": (
        "Search information from Internet, social media, news sites, etc.\n"
        "\n"
        "Args:\n"
        "    query: The query string to search.\n"
        "\n"
        "Returns:\n"
        "    Summarized search results.",
        {
            "additionalProperties": False,
            "properties": {"query": {"title": "Query", "type": "string"}},
            "required": ["query"],
            "title": "vesearchParams",
            "type": "object",
        },
    ),
    "video_generate": (
        "Generate videos in batch from text prompts, with support for "
        "multiple input modes:\n"
        "text-to-video, image-to-video (first/last frame), and multimodal "
        "reference generation.\n"
        "\n"
        "This API creates video-generation tasks asynchronously. Each item "
        "in `params` describes\n"
        "a single video generation request. The function submits all items "
        "and polls for results.\n"
        "\n"
        "If polling times out, the task_id will be returned so you can "
        "query the status later\n"
        "using the video_task_query tool.\n"
        "\n"
        "Args:\n"
        "    params (list[dict]):\n"
        "        A list of video generation requests. Each item is a dict "
        "with the following fields.\n"
        "\n"
        "        Required per item:\n"
        "            - video_name (str):\n"
        "                Name/identifier of the output video file.\n"
        "\n"
        "            - prompt (str):\n"
        "                Text describing the video to generate. Supports "
        "Chinese and English.\n"
        "                For multimodal reference generation, use [图1], "
        "[图2], [视频1], [音频1]\n"
        "                to reference specific input materials in your "
        "prompt.\n"
        "\n"
        "        Optional per item - Input Materials:\n"
        "            - first_frame (str):\n"
        "                URL for the first frame image (role = "
        "first_frame).\n"
        "                Use when you want the video to start from a "
        "specific image.\n"
        "\n"
        "            - last_frame (str):\n"
        "                URL for the last frame image (role = "
        "last_frame).\n"
        "                Use when you want the video to end on a specific "
        "image.\n"
        "\n"
        "            - reference_images (list[str]):\n"
        "                1-4 reference image URLs for style/content "
        "guidance (role = reference_image).\n"
        "                The model extracts features from these images and "
        "applies them to the output.\n"
        "                Use [图1], [图2], etc. in prompt to reference "
        "specific images.\n"
        "\n"
        "            - reference_videos (list[str]):\n"
        "                0-3 reference video URLs for multimodal "
        "generation (role = reference_video).\n"
        "                Video constraints: mp4/mov format, 2-15s duration "
        "per video,\n"
        "                total duration <= 15s, size <= 50MB, 24-60 FPS.\n"
        "                Use [视频1], [视频2], etc. in prompt to reference "
        "specific videos.\n"
        "\n"
        "            - reference_audios (list[str]):\n"
        "                0-3 reference audio URLs for multimodal "
        "generation (role = reference_audio).\n"
        "                Audio constraints: mp3/wav format, 2-15s duration "
        "per audio,\n"
        "                total duration <= 15s, size <= 15MB.\n"
        "                Use [音频1], [音频2], etc. in prompt to reference "
        "specific audios.\n"
        "                Note: Audio cannot be used alone; must have at "
        "least one image or video.\n"
        "\n"
        "        Optional per item - Video Output Parameters:\n"
        "            - ratio (str):\n"
        '                Aspect ratio. Options: "16:9" (default), "9:16", '
        '"4:3", "3:4", "1:1",\n'
        '                "2:1", "21:9", "adaptive" (auto-select based on '
        "input).\n"
        "                Note: Reference image scenarios do not support "
        "all ratios.\n"
        "\n"
        "            - duration (int):\n"
        "                Video length in seconds. Range: 2-12s depending "
        "on model.\n"
        "                - Seedance 1.5 pro: 4-12s\n"
        "                - Seedance 1.0 pro: 2-12s\n"
        "                - Seedance 1.0 pro-fast: 2-12s\n"
        "\n"
        "            - resolution (str):\n"
        '                Video resolution. Options: "480p", "720p", '
        '"1080p".\n'
        "                Default varies by model (e.g., Seedance 1.0 pro "
        "defaults to 1080p).\n"
        "                Note: Reference image scenarios do not support "
        "resolution parameter.\n"
        "\n"
        "            - frames (int):\n"
        "                Total frame count. Must be in [29, 289] and "
        "follow format 25 + 4n.\n"
        "                Alternative to duration for controlling video "
        "length.\n"
        "\n"
        "            - camera_fixed (bool):\n"
        "                Lock camera movement. true = fixed camera, false "
        "= allow movement.\n"
        "                Default: false. Note: Not supported in reference "
        "image scenarios.\n"
        "\n"
        "            - seed (int):\n"
        "                Random seed for reproducibility. Range: [-1, "
        "2^32-1].\n"
        "                Default: -1 (auto seed). Same seed may yield "
        "similar results.\n"
        "\n"
        "            - watermark (bool):\n"
        "                Whether to add watermark. Default: false.\n"
        "\n"
        "            - generate_audio (bool):\n"
        "                Whether to generate audio. Only Seedance 1.5 pro "
        "supports this.\n"
        "                If True, audio (ambi",
        {
            "additionalProperties": False,
            "properties": {
                "batch_size": {"default": 10, "title": "Batch Size", "type": "integer"},
                "max_wait_seconds": {
                    "default": 1200,
                    "title": "Max Wait Seconds",
                    "type": "integer",
                },
                "model_name": {
                    "default": "doubao-seedance-2-0-260128",
                    "title": "Model Name",
                    "type": "string",
                },
                "params": {"items": {}, "title": "Params", "type": "array"},
            },
            "required": ["params"],
            "title": "video_generateParams",
            "type": "object",
        },
    ),
    "video_task_query": (
        "Query the status of a video generation task.\n"
        "\n"
        "Use this tool to check the status of a previously submitted "
        "video generation task.\n"
        "If the task is completed, the video URL will be returned.\n"
        "\n"
        "Args:\n"
        "    task_id (str):\n"
        "        The task ID returned from video_generate when the task "
        "was submitted.\n"
        '        Format: "cgt-xxxxxxxxxxxx-xxxxx"\n'
        "\n"
        "    tool_context (ToolContext):\n"
        "        The tool context provided by the ADK framework.\n"
        "\n"
        "Returns:\n"
        "    Dict:\n"
        "        {\n"
        '            "task_id": "cgt-xxxxxxxxxxxx-xxxxx",\n'
        '            "status": "succeeded" | "running" | "failed" | '
        '"queued",\n'
        '            "video_url": "https://..." | None,\n'
        '            "error": {...} | None,\n'
        '            "model": "doubao-seedance-x-x",\n'
        '            "created_at": timestamp,\n'
        '            "updated_at": timestamp,\n'
        '            "execution_expires_after": seconds\n'
        "        }\n"
        "\n"
        "Status Values:\n"
        "    - queued: Task is waiting in queue\n"
        "    - running: Task is being processed\n"
        "    - succeeded: Task completed, video_url available\n"
        "    - failed: Task failed, check error field\n"
        "\n"
        "Example:\n"
        "    # Query a task status\n"
        '    result = await video_task_query("cgt-20260222165751-wsnw8", '
        "tool_context)\n"
        '    if result["status"] == "succeeded":\n'
        "        print(f\"Video ready: {result['video_url']}\")\n"
        '    elif result["status"] == "running":\n'
        '        print("Still processing, please wait...")\n'
        '    elif result["status"] == "failed":\n'
        "        print(f\"Task failed: {result['error']}\")",
        {
            "additionalProperties": False,
            "properties": {"task_id": {"title": "Task Id", "type": "string"}},
            "required": ["task_id"],
            "title": "video_task_queryParams",
            "type": "object",
        },
    ),
    "web_fetch": (
        "Fetch a web page over HTTP(S) and return its readable main content.\n"
        "\n"
        "Performs a plain HTTP GET (no JavaScript execution) and extracts the "
        "page's\n"
        "readable text. Handles HTML pages (converted to markdown/text) and "
        "**PDF**\n"
        "URLs (text extracted via pypdf). Follows HTTP and `<meta refresh>` "
        "redirects.\n"
        "Use it to read articles, docs, or any public URL the user references. "
        "For\n"
        "pages that require login or render entirely via JavaScript, the "
        "content may\n"
        "be incomplete.\n"
        "\n"
        "Args:\n"
        "    url: The http(s) URL to fetch.\n"
        '    extract_mode: "markdown" (default, keeps headings/links/lists) or '
        '"text"\n'
        "        (plain text with markdown decoration removed).\n"
        "    max_chars: Truncate the extracted content to at most this many "
        "characters.\n"
        "\n"
        "Returns:\n"
        '    A dict with keys: "url" (final URL after redirects), "title", '
        '"content",\n'
        '    and "truncated" (bool). On failure, a dict with an "error" key.',
        {
            "additionalProperties": False,
            "properties": {
                "extract_mode": {
                    "default": "markdown",
                    "title": "Extract Mode",
                    "type": "string",
                },
                "max_chars": {
                    "default": 50000,
                    "title": "Max Chars",
                    "type": "integer",
                },
                "url": {"title": "Url", "type": "string"},
            },
            "required": ["url"],
            "title": "web_fetchParams",
            "type": "object",
        },
    ),
    "web_search": (
        "Search a query in websites.\n"
        "\n"
        "Args:\n"
        "    query: The query to search.\n"
        "\n"
        "Returns:\n"
        "    A list of result documents.",
        {
            "additionalProperties": False,
            "properties": {"query": {"title": "Query", "type": "string"}},
            "required": ["query"],
            "title": "web_searchParams",
            "type": "object",
        },
    ),
}


__all__ = ["BUILTIN_TOOL_DECLARATIONS"]
