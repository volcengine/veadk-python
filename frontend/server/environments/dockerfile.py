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

"""Deterministic Dockerfile generation for Studio environments."""

from __future__ import annotations

from dataclasses import dataclass

from .models import EnvironmentInput


@dataclass(frozen=True)
class _Package:
    label: str
    description: str
    installer: str
    package_name: str


_OPERATING_SYSTEMS = {
    "ubuntu-22.04": ("Ubuntu 22.04", "ubuntu:22.04"),
    "ubuntu-24.04": ("Ubuntu 24.04", "ubuntu:24.04"),
}

_PYTHON_PATCH_VERSIONS = {
    "3.10": "3.10.18",
    "3.12": "3.12.11",
}

_VEADK_RUNTIME_REQUIREMENT = (
    '"veadk-python[a2ui,database,eval,extensions,harness,harness-sidecar,pdf,speech]'
    '>=1.1.1"'
)

_PACKAGES = {
    "lark-cli": _Package("lark-cli", "飞书开放平台命令行工具", "pip", "lark-cli"),
    "pandoc": _Package("pandoc", "文档格式转换工具", "apt", "pandoc"),
    "opencli": _Package(
        "opencli",
        "将网站与桌面应用转换为命令行工具",
        "npm",
        "@jackwener/opencli@1.8.7",
    ),
    "uv": _Package("uv", "快速 Python 包与项目管理器", "pip", "uv"),
    "ripgrep": _Package("ripgrep", "高性能文本检索工具", "apt", "ripgrep"),
    "jq": _Package("jq", "JSON 查询与转换工具", "apt", "jq"),
    "github-cli": _Package("GitHub CLI", "在终端中管理 GitHub 工作流", "apt", "gh"),
    "playwright": _Package(
        "Playwright", "浏览器自动化与端到端测试", "pip", "playwright"
    ),
    "chromium": _Package("Chromium", "无头浏览器运行时", "apt", "chromium"),
    "git": _Package("Git", "代码版本管理", "apt", "git"),
    "curl": _Package("curl", "网络请求与文件下载", "apt", "curl"),
    "ffmpeg": _Package("FFmpeg", "音视频转码与处理", "apt", "ffmpeg"),
    "imagemagick": _Package("ImageMagick", "图片转换与批处理", "apt", "imagemagick"),
}


def build_dockerfile(config: EnvironmentInput) -> str:
    """Build the canonical Dockerfile when the user did not provide one."""
    if config.dockerfile:
        return validate_dockerfile(config.dockerfile)

    os_label, base_image = _OPERATING_SYSTEMS[config.operating_system]
    python_version = config.language.removeprefix("python-")
    python_patch_version = _PYTHON_PATCH_VERSIONS[python_version]
    selected_options = set(config.option_ids)
    uses_ubuntu_python = (
        config.operating_system == "ubuntu-22.04" and python_version == "3.10"
    ) or (config.operating_system == "ubuntu-24.04" and python_version == "3.12")
    lines = [
        f"# Operating system: {os_label}",
        f"FROM {base_image}",
        "",
        "ARG DEBIAN_FRONTEND=noninteractive",
        "ARG PIP_INDEX_URL=https://pypi.org/simple",
        "ARG PYTHON_SOURCE_BASE_URL=https://www.python.org/ftp/python",
        "ARG PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.playwright.dev",
        "ARG PIP_DEFAULT_TIMEOUT=300",
        "ARG PIP_RETRIES=10",
        "",
        "# Ubuntu repositories: keep the official hosts, use HTTPS, and tolerate transient builder egress failures.",
        'RUN printf \'Acquire::Retries "5";\\nAcquire::ForceIPv4 "true";\\nAcquire::http::Timeout "60";\\nAcquire::https::Timeout "60";\\n\' > /etc/apt/apt.conf.d/80-veadk-network \\',
        "    && sed -i 's|http://archive.ubuntu.com|https://archive.ubuntu.com|g; s|http://security.ubuntu.com|https://security.ubuntu.com|g' /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true",
        "",
        "ENV PYTHONDONTWRITEBYTECODE=1 \\",
        "    PYTHONUNBUFFERED=1 \\",
        "    PIP_NO_CACHE_DIR=1",
        "",
        f"# Python {python_version}",
        "RUN apt-get update \\",
    ]
    if uses_ubuntu_python:
        lines.extend(
            (
                f"    && apt-get install -y --no-install-recommends ca-certificates python{python_version} python{python_version}-venv \\",
                f"    && python{python_version} -m venv /opt/venv \\",
                "    && rm -rf /var/lib/apt/lists/*",
            )
        )
    else:
        lines.extend(
            (
                "    && apt-get install -y --no-install-recommends build-essential ca-certificates curl libbz2-dev libffi-dev libgdbm-dev liblzma-dev libncursesw5-dev libreadline-dev libsqlite3-dev libssl-dev tk-dev uuid-dev zlib1g-dev \\",
                f'    && curl --retry 5 --retry-all-errors --connect-timeout 30 -fsSL "${{PYTHON_SOURCE_BASE_URL}}/{python_patch_version}/Python-{python_patch_version}.tgz" -o /tmp/python.tgz \\',
                "    && mkdir -p /tmp/python-source \\",
                "    && tar -xzf /tmp/python.tgz --strip-components=1 -C /tmp/python-source \\",
                "    && cd /tmp/python-source \\",
                "    && ./configure --prefix=/opt/python --with-ensurepip=install \\",
                '    && make -j"$(nproc)" \\',
                "    && make install \\",
                f"    && /opt/python/bin/python{python_version} -m venv /opt/venv \\",
                "    && rm -rf /tmp/python-source /tmp/python.tgz /var/lib/apt/lists/*",
            )
        )
    lines.extend(("", 'ENV PATH="/opt/venv/bin:$PATH"'))
    if {"playwright", "chromium"} & selected_options:
        lines.extend(
            (
                "",
                "ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \\",
                "    PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=300000",
            )
        )
    lines.extend(
        (
            "",
            "WORKDIR /workspace",
            "",
            "# VeADK: preinstall the complete Agent runtime dependency profile.",
            "# lxml-html-clean: VeADK Studio webpage content runtime dependency.",
            "# Agent images based on this environment only need to copy user code.",
            "RUN python -m pip install --upgrade \\",
            f"    {_VEADK_RUNTIME_REQUIREMENT} \\",
            '    "agentkit-sdk-python==0.8.4" \\',
            '    "starlette<1.0.0" \\',
            "    lxml-html-clean",
            'ENV VEADK_ENVIRONMENT_IMAGE="1"',
        )
    )
    for option_id in config.option_ids:
        package = _PACKAGES[option_id]
        lines.extend(("", f"# {package.label}: {package.description}"))
        if option_id == "github-cli":
            lines.extend(
                (
                    "RUN apt-get update \\",
                    "    && apt-get install -y --no-install-recommends wget \\",
                    "    && mkdir -p -m 755 /etc/apt/keyrings \\",
                    "    && wget -qO /etc/apt/keyrings/githubcli-archive-keyring.gpg https://cli.github.com/packages/githubcli-archive-keyring.gpg \\",
                    "    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \\",
                    '    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \\',
                    "    && apt-get update \\",
                    "    && apt-get install -y --no-install-recommends gh \\",
                    "    && rm -rf /var/lib/apt/lists/*",
                )
            )
        elif option_id == "opencli":
            lines.extend(
                (
                    "RUN apt-get update \\",
                    "    && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \\",
                    '    && node_arch="$(dpkg --print-architecture)" \\',
                    '    && case "$node_arch" in amd64) node_arch=x64 ;; arm64) node_arch=arm64 ;; *) echo "Unsupported architecture: $node_arch" >&2; exit 1 ;; esac \\',
                    '    && curl --retry 5 --connect-timeout 30 -fsSL "https://nodejs.org/dist/v22.18.0/node-v22.18.0-linux-${node_arch}.tar.xz" -o /tmp/node.tar.xz \\',
                    "    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \\",
                    f"    && npm install --global {package.package_name} \\",
                    "    && npm cache clean --force \\",
                    "    && rm -f /tmp/node.tar.xz \\",
                    "    && rm -rf /var/lib/apt/lists/*",
                )
            )
        elif option_id == "playwright":
            lines.append("RUN python -m pip install --upgrade playwright")
            if "chromium" not in selected_options:
                lines.append("RUN python -m playwright install --with-deps chromium")
        elif option_id == "chromium":
            if "playwright" not in selected_options:
                lines.append("RUN python -m pip install --upgrade playwright")
            lines.append("RUN python -m playwright install --with-deps chromium")
        elif package.installer == "apt":
            lines.extend(
                (
                    "RUN apt-get update \\",
                    f"    && apt-get install -y --no-install-recommends {package.package_name} \\",
                    "    && rm -rf /var/lib/apt/lists/*",
                )
            )
        else:
            lines.append(f"RUN python -m pip install --upgrade {package.package_name}")
    lines.extend(("", 'CMD ["/bin/bash"]'))
    return "\n".join(lines)


def validate_dockerfile(value: str) -> str:
    dockerfile = value.strip()
    if "\x00" in dockerfile:
        raise ValueError("Dockerfile 不能包含空字符。")
    if not any(
        line.lstrip().upper().startswith("FROM ")
        for line in dockerfile.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ):
        raise ValueError("Dockerfile 必须包含 FROM 指令。")
    return dockerfile


__all__ = ["build_dockerfile", "validate_dockerfile"]
