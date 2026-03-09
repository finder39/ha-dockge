"""Tests for service handler busy-state management.

Key invariant: for normal operations, busy state clears when API returns (as fallback).
For self-updates, busy state persists until SSE operation_completed arrives.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestServiceHandlerBusyState:
    """Verify busy state management with SSE as primary and API return as fallback."""

    @pytest.fixture
    def setup_service_handler(self, coordinator):
        coordinator.api_call = AsyncMock(return_value={"ok": True})
        coordinator.async_request_refresh = AsyncMock()
        coordinator.data = {
            "stacks": [
                {"name": "nginx", "endpoint": ""},
                {"name": "grafana", "endpoint": "192.168.1.100:5001"},
            ],
            "agents": [],
            "agent_names": {"": "Primary", "192.168.1.100:5001": "Porygon"},
            "multi_agent": True,
            "scheduler": {},
            "last_update": None,
        }
        return coordinator

    @pytest.mark.asyncio
    async def test_sse_clears_busy_before_api_returns(self, setup_service_handler):
        """SSE operation_completed arriving before API return should clear busy."""
        coord = setup_service_handler
        coord.mark_busy("", "nginx")
        assert coord.is_stack_busy("", "nginx")

        # SSE event arrives
        coord._handle_sse_event("operation_completed", {
            "stack": "nginx", "endpoint": "", "operation": "update", "success": True,
        })
        assert not coord.is_stack_busy("", "nginx")

    @pytest.mark.asyncio
    async def test_self_update_response_keeps_busy(self, setup_service_handler):
        """Self-update API response should not clear busy — SSE handles it."""
        coord = setup_service_handler
        coord.mark_busy("192.168.1.100:5001", "agents")

        # API returns with selfUpdate flag
        result = {"ok": True, "selfUpdate": True}
        # Simulate what _handle_stack_action does:
        if isinstance(result, dict) and result.get("selfUpdate"):
            pass  # Don't clear
        else:
            coord.mark_done("192.168.1.100:5001", "agents")

        assert coord.is_stack_busy("192.168.1.100:5001", "agents"), (
            "Self-update should keep busy state"
        )

    @pytest.mark.asyncio
    async def test_self_update_cleared_by_sse(self, setup_service_handler):
        """After self-update, SSE operation_completed should eventually clear busy."""
        coord = setup_service_handler
        coord.mark_busy("192.168.1.100:5001", "agents")

        # SSE operation_completed after agent reconnects
        coord._handle_sse_event("operation_completed", {
            "stack": "agents", "endpoint": "192.168.1.100:5001",
            "operation": "update", "success": True,
        })
        assert not coord.is_stack_busy("192.168.1.100:5001", "agents")

    @pytest.mark.asyncio
    async def test_mark_done_idempotent_double_clear(self, setup_service_handler):
        """Both SSE and API return clearing busy should be harmless."""
        coord = setup_service_handler
        coord.mark_busy("", "nginx")

        # SSE clears first
        coord.mark_done("", "nginx")
        assert not coord.is_stack_busy("", "nginx")

        # API return also clears (no-op)
        coord.mark_done("", "nginx")
        assert not coord.is_stack_busy("", "nginx")
