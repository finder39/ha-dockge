"""Shared test fixtures for dockge integration tests."""
from __future__ import annotations
import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Mock homeassistant and third-party modules before importing custom_components
_ha_mocks = {}
for mod_name in [
    "voluptuous",
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.entity_platform",
    "homeassistant.components",
    "homeassistant.components.sensor",
    "homeassistant.components.binary_sensor",
    "homeassistant.components.button",
    "homeassistant.components.switch",
]:
    mock = MagicMock()
    _ha_mocks[mod_name] = mock
    sys.modules[mod_name] = mock

# Set up DataUpdateCoordinator as a real base class (so our coordinator can inherit)
class _FakeDataUpdateCoordinator:
    pass

sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = _FakeDataUpdateCoordinator
sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed = Exception


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.loop = asyncio.get_event_loop()
    hass.async_create_background_task = MagicMock(return_value=MagicMock())
    hass.async_create_task = MagicMock()
    return hass


@pytest.fixture
def coordinator(mock_hass):
    """Create a DockgeCoordinator with mocked dependencies."""
    from custom_components.dockge.coordinator import DockgeCoordinator

    with patch.object(DockgeCoordinator, "__init__", lambda self, *a, **kw: None):
        coord = DockgeCoordinator.__new__(DockgeCoordinator)
        coord.hass = mock_hass
        coord.url = "http://localhost:5001"
        coord.api_key = "test-api-key"
        coord._busy_stacks = set()
        coord._sse_task = None
        coord._sse_session = None
        coord._sse_stop_event = asyncio.Event()
        coord._sse_watchdog_handle = None
        coord.data = {
            "stacks": [],
            "agents": [],
            "agent_names": {},
            "multi_agent": False,
            "scheduler": {},
            "last_update": None,
        }
        coord.async_set_updated_data = MagicMock()
        coord.async_request_refresh = AsyncMock()
        coord.logger = MagicMock()
        return coord
