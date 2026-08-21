# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Contracts for Studio website integrations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateWebsiteIntegrationBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    domain: str = Field(min_length=1, max_length=253)
    runtime_id: str = Field(alias="runtimeId", min_length=1, max_length=256)
    runtime_name: str = Field(alias="runtimeName", min_length=1, max_length=256)
    region: str = Field(min_length=1, max_length=64)
    app_name: str = Field(alias="appName", min_length=1, max_length=256)


class BootstrapSessionBody(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class RunWebsiteChatBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str = Field(min_length=1, max_length=20_000)
    user_id: str = Field(alias="userId", min_length=1, max_length=256)
    session_id: str = Field(alias="sessionId", min_length=1, max_length=256)


class WebsiteIntegration(BaseModel):
    id: str
    owner_id: str
    domain: str
    runtime_id: str
    runtime_name: str
    region: str
    app_name: str
    token: str
    created_at: datetime

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "domain": self.domain,
            "runtimeId": self.runtime_id,
            "runtimeName": self.runtime_name,
            "region": self.region,
            "appName": self.app_name,
            "token": self.token,
            "createdAt": self.created_at.isoformat(),
        }


class WebsiteIntegrationSession(BaseModel):
    token: str
    integration_id: str
    expires_at: datetime
