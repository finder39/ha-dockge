"""Tests for SSE event handling in the coordinator."""
import pytest


class TestSSEEventHandling:
    """Test _handle_sse_event processes events correctly."""

    def test_heartbeat_resets_watchdog(self, coordinator):
        """Heartbeat event should reset the watchdog timer."""
        from unittest.mock import MagicMock
        coordinator._reset_watchdog = MagicMock()
        coordinator._handle_sse_event("heartbeat", {"timestamp": "2026-03-08T00:00:00Z"})
        coordinator._reset_watchdog.assert_called_once()

    def test_connected_resets_watchdog(self, coordinator):
        from unittest.mock import MagicMock
        coordinator._reset_watchdog = MagicMock()
        coordinator._handle_sse_event("connected", {"message": "connected"})
        coordinator._reset_watchdog.assert_called_once()

    def test_operation_started_marks_busy(self, coordinator):
        coordinator._handle_sse_event("operation_started", {
            "stack": "nginx", "endpoint": "", "operation": "update",
        })
        assert coordinator.is_stack_busy("", "nginx")
        coordinator.async_set_updated_data.assert_called()

    def test_operation_started_agent_stack(self, coordinator):
        coordinator._handle_sse_event("operation_started", {
            "stack": "grafana", "endpoint": "192.168.1.100:5001", "operation": "update",
        })
        assert coordinator.is_stack_busy("192.168.1.100:5001", "grafana")
        assert not coordinator.is_stack_busy("", "grafana")

    def test_operation_completed_marks_done(self, coordinator):
        coordinator._busy_stacks.add("_nginx")
        coordinator._handle_sse_event("operation_completed", {
            "stack": "nginx", "endpoint": "", "operation": "update", "success": True,
        })
        assert not coordinator.is_stack_busy("", "nginx")

    def test_operation_completed_triggers_refresh(self, coordinator):
        coordinator._handle_sse_event("operation_completed", {
            "stack": "nginx", "endpoint": "", "operation": "update", "success": True,
        })
        coordinator.hass.async_create_task.assert_called()

    def test_operation_completed_failure_still_marks_done(self, coordinator):
        coordinator._busy_stacks.add("_nginx")
        coordinator._handle_sse_event("operation_completed", {
            "stack": "nginx", "endpoint": "", "operation": "update", "success": False,
        })
        assert not coordinator.is_stack_busy("", "nginx")

    def test_image_check_completed_triggers_refresh(self, coordinator):
        coordinator._handle_sse_event("image_check_completed", {
            "stacks": [{"name": "nginx", "endpoint": "", "updatesAvailable": True}],
        })
        coordinator.hass.async_create_task.assert_called()

    def test_scheduler_run_completed_triggers_refresh(self, coordinator):
        coordinator._handle_sse_event("scheduler_run_completed", {
            "updated": ["nginx"], "failed": [], "nextRun": "2026-03-09T03:00:00Z",
        })
        coordinator.hass.async_create_task.assert_called()

    def test_unknown_event_does_not_crash(self, coordinator):
        coordinator._handle_sse_event("unknown_event_type", {"foo": "bar"})

    def test_malformed_event_missing_fields(self, coordinator):
        """Empty stack name should be ignored, not marked busy."""
        coordinator._handle_sse_event("operation_started", {})
        assert not coordinator.is_stack_busy("", "")

    def test_mark_done_idempotent(self, coordinator):
        coordinator._handle_sse_event("operation_completed", {
            "stack": "not-busy", "endpoint": "", "operation": "update", "success": True,
        })
        assert not coordinator.is_stack_busy("", "not-busy")

    def test_dual_signal_dedup(self, coordinator):
        """SSE completing after manual mark_done should be harmless."""
        coordinator.mark_busy("", "nginx")
        assert coordinator.is_stack_busy("", "nginx")
        coordinator.mark_done("", "nginx")
        assert not coordinator.is_stack_busy("", "nginx")
        # SSE arrives late - no-op
        coordinator._handle_sse_event("operation_completed", {
            "stack": "nginx", "endpoint": "", "operation": "update", "success": True,
        })
        assert not coordinator.is_stack_busy("", "nginx")
