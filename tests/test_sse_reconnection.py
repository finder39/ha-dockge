"""Tests for SSE reconnection behavior."""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
import aiohttp


class TestSSEReconnection:
    """Test SSE connection lifecycle and reconnection."""

    @pytest.mark.asyncio
    async def test_listen_loop_reconnects_on_failure(self, coordinator):
        # Recreate the stop event in the current event loop
        coordinator._sse_stop_event = asyncio.Event()
        call_count = 0

        async def mock_connect():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                coordinator._sse_stop_event.set()
            raise aiohttp.ClientError("Connection refused")

        coordinator._sse_connect = mock_connect
        await coordinator._sse_listen_loop()
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_stop_sse_cancels_task(self, coordinator):
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        coordinator._sse_task = mock_task
        coordinator._sse_session = AsyncMock()

        await coordinator.stop_sse()
        mock_task.cancel.assert_called_once()
        assert coordinator._sse_task is None

    @pytest.mark.asyncio
    async def test_start_sse_is_idempotent(self, coordinator):
        coordinator._sse_task = MagicMock()  # Already running
        await coordinator.start_sse()
        coordinator.hass.async_create_background_task.assert_not_called()

    def test_watchdog_expired_restarts_listener(self, coordinator):
        mock_task = MagicMock()
        coordinator._sse_task = mock_task
        coordinator._watchdog_expired()
        mock_task.cancel.assert_called_once()
        coordinator.hass.async_create_background_task.assert_called_once()

    def test_watchdog_reset_on_heartbeat(self, coordinator):
        coordinator._cancel_watchdog = MagicMock()
        coordinator.hass.loop.call_later = MagicMock()
        coordinator._reset_watchdog()
        coordinator._cancel_watchdog.assert_called_once()
        coordinator.hass.loop.call_later.assert_called_once_with(
            90.0, coordinator._watchdog_expired
        )
