# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from veadk.integrations.ve_faas.ve_faas import VeFaaS


def test_create_image_function_binds_configured_iam_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    client.create_function.return_value = SimpleNamespace(
        id="function-id",
        project_name="default",
    )
    fake = object.__new__(VeFaaS)
    fake.client = client
    fake.project_name = "default"
    monkeypatch.setenv(
        "IAM_ROLE",
        "trn:iam::123:role/VeADKFrontendServiceRole",
    )
    monkeypatch.setattr(
        "veadk.config.veadk_environments",
        {"CLOUD_PROVIDER": "volcengine"},
    )

    name, function_id = VeFaaS._create_image_function(
        fake,
        "studio-function",
        "registry.example.com/studio:latest",
    )

    request = client.create_function.call_args.args[0]
    assert name == "studio-function"
    assert function_id == "function-id"
    assert request.command == "bash ./run.sh"
    assert request.role == "trn:iam::123:role/VeADKFrontendServiceRole"
    assert request.project_name == "default"
