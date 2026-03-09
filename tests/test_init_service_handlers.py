"""Tests for the actual service handler functions in __init__.py.

These test that _handle_stack_action clears busy state when API returns (fallback),
but does NOT clear it for self-update responses (agent still restarting).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


class TestInitServiceHandlers:
    """Test that __init__.py service handlers manage busy state correctly."""

    @pytest.fixture
    def setup_integration(self, coordinator, mock_hass):
        """Set up the full integration service registration."""
        coordinator.api_call = AsyncMock(return_value={"ok": True})
        coordinator.async_request_refresh = AsyncMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.start_sse = AsyncMock()
        coordinator.stop_sse = AsyncMock()
        coordinator.data = {
            "stacks": [
                {"name": "nginx", "endpoint": ""},
                {"name": "grafana", "endpoint": "192.168.1.100:5001"},
            ],
            "agents": [
                {"endpoint": "", "name": "Primary"},
                {"endpoint": "192.168.1.100:5001", "name": "Porygon"},
            ],
            "agent_names": {"": "Primary", "192.168.1.100:5001": "Porygon"},
            "multi_agent": True,
            "scheduler": {},
            "last_update": None,
        }
        return coordinator

    async def _setup_and_get_services(self, coordinator, mock_hass):
        """Register services and return the handler map."""
        import custom_components.dockge.__init__ as init_mod

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {
            "url": "http://localhost:5001",
            "api_key": "test-key",
            "scan_interval": 600,
        }

        with patch.object(init_mod, "DockgeCoordinator", return_value=coordinator):
            with patch.object(mock_hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock):
                mock_hass.data = {}
                await init_mod.async_setup_entry(mock_hass, entry)

        registered = {}
        for call_args in mock_hass.services.async_register.call_args_list:
            domain, name, handler = call_args[0][:3]
            registered[name] = handler
        return registered

    @pytest.mark.asyncio
    async def test_normal_operation_clears_busy_on_return(self, setup_integration, mock_hass):
        """Normal (non-self-update) operations should clear busy when API returns."""
        coord = setup_integration
        services = await self._setup_and_get_services(coord, mock_hass)

        service_call = MagicMock()
        service_call.data = {"stack_name": "nginx", "agent": ""}

        await services["check_updates"](service_call)

        # Should be cleared — API returned successfully, not a self-update
        assert not coord.is_stack_busy("", "nginx"), (
            "Normal operation should clear busy when API returns"
        )

    @pytest.mark.asyncio
    async def test_self_update_preserves_busy(self, setup_integration, mock_hass):
        """Self-update responses should NOT clear busy — SSE handles it after reconnect."""
        coord = setup_integration
        coord.api_call = AsyncMock(return_value={
            "ok": True,
            "selfUpdate": True,
            "message": "Self-update initiated",
        })
        services = await self._setup_and_get_services(coord, mock_hass)

        service_call = MagicMock()
        service_call.data = {"stack_name": "agents", "agent": "Porygon"}

        await services["update_stack"](service_call)

        # Should still be busy — agent is restarting, SSE will clear it
        assert coord.is_stack_busy("192.168.1.100:5001", "agents"), (
            "Self-update should keep busy state — agent hasn't restarted yet"
        )

    @pytest.mark.asyncio
    async def test_api_failure_clears_busy(self, setup_integration, mock_hass):
        """API failure should clear busy state immediately."""
        coord = setup_integration
        coord.api_call = AsyncMock(side_effect=Exception("Connection refused"))
        services = await self._setup_and_get_services(coord, mock_hass)

        service_call = MagicMock()
        service_call.data = {"stack_name": "nginx", "agent": ""}

        with pytest.raises(Exception, match="Connection refused"):
            await services["update_stack"](service_call)

        assert not coord.is_stack_busy("", "nginx"), (
            "API failure should clear busy state"
        )
