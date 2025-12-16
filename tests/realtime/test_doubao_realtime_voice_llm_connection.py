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

import pytest
from unittest.mock import AsyncMock
from veadk.realtime.doubao_realtime_voice_llm_connection import (
    DoubaoRealtimeVoiceLlmConnection,
)
from google.genai import types


@pytest.mark.asyncio
async def test_send_realtime_with_blob():
    """Test sending Blob input."""
    # Setup
    mock_session = AsyncMock()
    connection = DoubaoRealtimeVoiceLlmConnection(gemini_session=mock_session)
    connection._gemini_session = mock_session

    blob_input = types.Blob()

    # Execute
    await connection.send_realtime(blob_input)

    # Verify
    mock_session.send_realtime_input.assert_called_once_with(media=blob_input)


@pytest.mark.asyncio
async def test_send_realtime_with_activity_start():
    """Test sending ActivityStart input."""
    # Setup
    mock_session = AsyncMock()
    connection = DoubaoRealtimeVoiceLlmConnection(gemini_session=mock_session)
    connection._gemini_session = mock_session

    activity_start = types.ActivityStart()

    # Execute
    await connection.send_realtime(activity_start)

    # Verify
    mock_session.send_realtime_input.assert_called_once_with(
        activity_start=activity_start
    )


@pytest.mark.asyncio
async def test_send_realtime_with_activity_end():
    """Test sending ActivityEnd input."""
    # Setup
    mock_session = AsyncMock()
    connection = DoubaoRealtimeVoiceLlmConnection(gemini_session=mock_session)
    connection._gemini_session = mock_session

    activity_end = types.ActivityEnd()

    # Execute
    await connection.send_realtime(activity_end)

    # Verify
    mock_session.send_realtime_input.assert_called_once_with(activity_end=activity_end)


@pytest.mark.asyncio
async def test_send_realtime_with_unsupported_type():
    """Test sending unsupported input type."""
    # Setup
    mock_session = AsyncMock()
    connection = DoubaoRealtimeVoiceLlmConnection(gemini_session=mock_session)
    connection._gemini_session = mock_session

    unsupported_input = "unsupported_type"

    # Execute & Verify
    with pytest.raises(ValueError) as excinfo:
        await connection.send_realtime(unsupported_input)

    assert "Unsupported input type" in str(excinfo.value)
