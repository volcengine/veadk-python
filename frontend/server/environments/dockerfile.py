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
import re

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

AIO_BASE_IMAGE = (
    "agentkit-cli-2107625663-cn-beijing.cr.volces.com/agentkit/"
    "agent-native-requirements-aio:0.2.1-20260831"
)

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

_PYTHON_BUILD_APT_PACKAGES = (
    "build-essential",
    "curl",
    "libbz2-dev",
    "libffi-dev",
    "libgdbm-dev",
    "liblzma-dev",
    "libncursesw5-dev",
    "libreadline-dev",
    "libsqlite3-dev",
    "libssl-dev",
    "tk-dev",
    "uuid-dev",
    "zlib1g-dev",
)

_PLAYWRIGHT_COMMON_APT_PACKAGES = (
    "xvfb",
    "fonts-noto-color-emoji",
    "fonts-unifont",
    "libfontconfig1",
    "libfreetype6",
    "xfonts-cyrillic",
    "xfonts-scalable",
    "fonts-liberation",
    "fonts-ipafont-gothic",
    "fonts-wqy-zenhei",
    "fonts-tlwg-loma-otf",
    "fonts-freefont-ttf",
)

_PLAYWRIGHT_CHROMIUM_APT_PACKAGES = {
    "ubuntu-22.04": (
        "libasound2",
        "libatk-bridge2.0-0",
        "libatk1.0-0",
        "libatspi2.0-0",
        "libcairo2",
        "libcups2",
        "libdbus-1-3",
        "libdrm2",
        "libgbm1",
        "libglib2.0-0",
        "libnspr4",
        "libnss3",
        "libpango-1.0-0",
        "libwayland-client0",
        "libx11-6",
        "libxcb1",
        "libxcomposite1",
        "libxdamage1",
        "libxext6",
        "libxfixes3",
        "libxkbcommon0",
        "libxrandr2",
    ),
    "ubuntu-24.04": (
        "libasound2t64",
        "libatk-bridge2.0-0t64",
        "libatk1.0-0t64",
        "libatspi2.0-0t64",
        "libcairo2",
        "libcups2t64",
        "libdbus-1-3",
        "libdrm2",
        "libgbm1",
        "libglib2.0-0t64",
        "libnspr4",
        "libnss3",
        "libpango-1.0-0",
        "libx11-6",
        "libxcb1",
        "libxcomposite1",
        "libxdamage1",
        "libxext6",
        "libxfixes3",
        "libxkbcommon0",
        "libxrandr2",
    ),
}


def _extend_unique(target: list[str], packages: tuple[str, ...] | list[str]) -> None:
    for package in packages:
        if package not in target:
            target.append(package)


def _apt_packages(
    config: EnvironmentInput,
    *,
    python_version: str,
    uses_ubuntu_python: bool,
    uses_aio_python: bool,
) -> list[str]:
    """Collect every system package so the generated image needs one apt update."""
    packages = ["ca-certificates"]
    if uses_aio_python:
        pass
    elif uses_ubuntu_python:
        _extend_unique(
            packages,
            [f"python{python_version}", f"python{python_version}-venv"],
        )
    else:
        _extend_unique(packages, _PYTHON_BUILD_APT_PACKAGES)

    for option_id in config.option_ids:
        package = _PACKAGES[option_id]
        if option_id in {"playwright", "chromium"}:
            continue
        if package.installer == "apt":
            _extend_unique(packages, [package.package_name])
        elif option_id == "opencli":
            _extend_unique(packages, ["curl", "xz-utils"])

    if {"playwright", "chromium"} & set(config.option_ids):
        _extend_unique(packages, _PLAYWRIGHT_COMMON_APT_PACKAGES)
        _extend_unique(
            packages,
            _PLAYWRIGHT_CHROMIUM_APT_PACKAGES[config.operating_system],
        )
    return packages


def build_dockerfile(config: EnvironmentInput) -> str:
    """Build the canonical Dockerfile when the user did not provide one."""
    if config.dockerfile:
        return validate_dockerfile(config.dockerfile)
    if config.base_environment == "codex-sandbox":
        raise ValueError("Codex Sandbox 预制环境必须提供包含基础镜像的 Dockerfile。")

    os_label, ubuntu_base_image = _OPERATING_SYSTEMS[config.operating_system]
    uses_aio_python = config.base_environment == "aio-sandbox"
    python_version = config.language.removeprefix("python-")
    python_patch_version = _PYTHON_PATCH_VERSIONS[python_version]
    selected_options = set(config.option_ids)
    uses_ubuntu_python = (
        config.operating_system == "ubuntu-22.04" and python_version == "3.10"
    ) or (config.operating_system == "ubuntu-24.04" and python_version == "3.12")
    apt_packages = _apt_packages(
        config,
        python_version=python_version,
        uses_ubuntu_python=uses_ubuntu_python,
        uses_aio_python=uses_aio_python,
    )
    lines = (
        [
            f"ARG AIO_BASE_IMAGE={AIO_BASE_IMAGE}",
            "ARG AIO_BASE_PLATFORM=linux/amd64",
            "",
            f"# Base environment: AIO Sandbox ({os_label})",
            "FROM --platform=${AIO_BASE_PLATFORM} ${AIO_BASE_IMAGE}",
        ]
        if uses_aio_python
        else [f"# Operating system: {os_label}", f"FROM {ubuntu_base_image}"]
    )
    lines.extend(
        [
            "",
            "ARG DEBIAN_FRONTEND=noninteractive",
            "ARG APT_MIRROR_URL=http://archive.ubuntu.com/ubuntu",
            "ARG PIP_INDEX_URL=https://pypi.org/simple",
            "ARG PYTHON_SOURCE_BASE_URL=https://www.python.org/ftp/python",
            "ARG PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.playwright.dev",
            "ARG PIP_DEFAULT_TIMEOUT=300",
            "ARG PIP_RETRIES=10",
            "",
            "# Install all system dependencies in one transaction from the provider-local mirror.",
            "RUN set -eux; \\",
            '    mirror="${APT_MIRROR_URL%/}"; \\',
            "    for source_file in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources; do \\",
            '        [ -f "$source_file" ] || continue; \\',
            '        sed -i -E "s#https?://(archive|security).ubuntu.com/ubuntu/?#${mirror}#g" "$source_file"; \\',
            "    done; \\",
            '    printf \'Acquire::Retries "5";\\nAcquire::ForceIPv4 "true";\\nAcquire::http::Timeout "60";\\nAcquire::https::Timeout "60";\\n\' > /etc/apt/apt.conf.d/80-veadk-network; \\',
            "    apt-get update; \\",
            "    apt-get install -y --no-install-recommends \\",
            *(f"    {package} \\" for package in apt_packages),
            "    ; rm -rf /var/lib/apt/lists/*",
            "",
            "ENV PYTHONDONTWRITEBYTECODE=1 \\",
            "    PYTHONUNBUFFERED=1 \\",
            "    PIP_NO_CACHE_DIR=1",
            "",
            f"# Python {python_version}",
        ]
    )
    if uses_aio_python:
        lines.extend(
            (
                "# Keep Studio dependencies isolated from AIO's system interpreter.",
                "RUN /opt/python3.12/bin/python -m venv /opt/veadk-environment/.venv",
                "",
                "ENV VIRTUAL_ENV=/opt/veadk-environment/.venv \\",
                "    BASH_VENV_PATH=/opt/veadk-environment/.venv \\",
                '    PATH="/opt/veadk-environment/.venv/bin:$PATH"',
            )
        )
    elif uses_ubuntu_python:
        lines.append(f"RUN python{python_version} -m venv /opt/venv")
    else:
        lines.extend(
            (
                f'RUN curl --retry 5 --retry-all-errors --connect-timeout 30 -fsSL "${{PYTHON_SOURCE_BASE_URL}}/{python_patch_version}/Python-{python_patch_version}.tgz" -o /tmp/python.tgz \\',
                "    && mkdir -p /tmp/python-source \\",
                "    && tar -xzf /tmp/python.tgz --strip-components=1 -C /tmp/python-source \\",
                "    && cd /tmp/python-source \\",
                "    && ./configure --prefix=/opt/python --with-ensurepip=install \\",
                '    && make -j"$(nproc)" \\',
                "    && make install \\",
                f"    && /opt/python/bin/python{python_version} -m venv /opt/venv \\",
                "    && rm -rf /tmp/python-source /tmp/python.tgz",
            )
        )
    if not uses_aio_python:
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
    browser_installed = False
    for option_id in config.option_ids:
        package = _PACKAGES[option_id]
        lines.extend(("", f"# {package.label}: {package.description}"))
        if option_id == "opencli":
            lines.extend(
                (
                    'RUN node_arch="$(dpkg --print-architecture)" \\',
                    '    && case "$node_arch" in amd64) node_arch=x64 ;; arm64) node_arch=arm64 ;; *) echo "Unsupported architecture: $node_arch" >&2; exit 1 ;; esac \\',
                    '    && curl --retry 5 --connect-timeout 30 -fsSL "https://nodejs.org/dist/v22.18.0/node-v22.18.0-linux-${node_arch}.tar.xz" -o /tmp/node.tar.xz \\',
                    "    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \\",
                    f"    && npm install --global {package.package_name} \\",
                    "    && npm cache clean --force \\",
                    "    && rm -f /tmp/node.tar.xz",
                )
            )
        elif option_id in {"playwright", "chromium"}:
            if not browser_installed:
                lines.append("RUN python -m pip install --upgrade playwright")
                lines.append("RUN python -m playwright install chromium")
                browser_installed = True
        elif package.installer != "apt":
            lines.append(f"RUN python -m pip install --upgrade {package.package_name}")
    if uses_aio_python:
        lines.extend(
            (
                "",
                "# Keep AIO's inherited /opt/gem/run.sh startup chain and shell API.",
                "EXPOSE 8080",
            )
        )
    else:
        lines.extend(("", 'CMD ["/bin/bash"]'))
    return "\n".join(lines)


def environment_base_image(config: EnvironmentInput) -> str:
    if config.base_environment == "aio-sandbox":
        return AIO_BASE_IMAGE
    if config.base_environment == "codex-sandbox":
        match = re.search(
            r"^\s*FROM(?:\s+--platform=\S+)?\s+(\S+)",
            config.dockerfile,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        return match.group(1) if match else ""
    return _OPERATING_SYSTEMS[config.operating_system][1]


def environment_capabilities(config: EnvironmentInput) -> list[str]:
    if config.base_environment in {"aio-sandbox", "codex-sandbox"}:
        return ["shell-exec"]
    return []


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


__all__ = [
    "AIO_BASE_IMAGE",
    "build_dockerfile",
    "environment_base_image",
    "environment_capabilities",
    "validate_dockerfile",
]
