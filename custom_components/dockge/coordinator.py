"""DataUpdateCoordinator for the Dockge integration."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_API_KEY, CONF_SCAN_INTERVAL, CONF_URL, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class DockgeCoordinator(DataUpdateCoordinator):
    """Coordinator to poll Dockge API for stack and scheduler data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.url = entry.data[CONF_URL].rstrip("/")
        self.api_key = entry.data[CONF_API_KEY]
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name="Dockge",
            update_interval=timedelta(seconds=scan_interval),
        )

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key}

    async def _async_update_data(self) -> dict:
        """Fetch stacks and scheduler data from Dockge API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.url}/api/stacks", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    resp.raise_for_status()
                    stacks = await resp.json()

                async with session.get(
                    f"{self.url}/api/scheduler", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    resp.raise_for_status()
                    scheduler = await resp.json()

                async with session.get(
                    f"{self.url}/api/update-history?limit=1", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    resp.raise_for_status()
                    history = await resp.json()

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with Dockge API: {err}") from err

        return {
            "stacks": stacks,
            "scheduler": scheduler,
            "last_update": history[0] if history else None,
        }

    async def api_call(self, method: str, path: str, json: dict | None = None) -> dict | list | None:
        """Make an API call to Dockge (for actions like update, toggle)."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    f"{self.url}{path}",
                    headers=self._headers(),
                    json=json,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    resp.raise_for_status()
                    if resp.content_length and resp.content_length > 0:
                        return await resp.json()
                    return None
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Dockge API call failed: {err}") from err
