# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""A dependency-free example of a first-party Studio Tool extension."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from frontend.server.studio_tools.registry import (
    StudioTool,
    StudioToolExecutionError,
    StudioToolRegistry,
)

_DEFAULT_TIMEZONE = "Asia/Shanghai"


def _current_time(arguments: dict[str, Any]) -> dict[str, str]:
    timezone_name = str(arguments.get("timezone") or _DEFAULT_TIMEZONE).strip()
    try:
        timezone = ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise StudioToolExecutionError(
            f"Unknown IANA timezone: {timezone_name}"
        ) from error

    current = datetime.now(timezone)
    return {
        "timezone": timezone_name,
        "iso8601": current.isoformat(timespec="seconds"),
        "date": current.date().isoformat(),
        "time": current.time().isoformat(timespec="seconds"),
        "weekday": current.strftime("%A"),
    }


def register_tools(registry: StudioToolRegistry) -> None:
    """Register the current-time extension with the Studio BFF."""

    registry.register(
        StudioTool(
            name="current_time",
            display_name="当前时间",
            description="Return the current date and time in an IANA timezone.",
            input_schema={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 128,
                        "default": _DEFAULT_TIMEZONE,
                        "description": (
                            "IANA timezone name, for example Asia/Shanghai or UTC."
                        ),
                    }
                },
                "additionalProperties": False,
            },
            executor=_current_time,
            executor_revision="studio-extension-current-time-v1",
            timeout_ms=1_000,
            risk_level="low",
        )
    )


__all__ = ["register_tools"]
