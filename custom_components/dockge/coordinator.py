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

    def _agent_name_map(self, agents: list[dict]) -> dict[str, str]:
        """Build endpoint -> agent name mapping."""
        mapping: dict[str, str] = {}
        for agent in agents:
            endpoint = agent.get("endpoint", "")
            name = agent.get("name", "")
            if name:
                mapping[endpoint] = name
        return mapping

    async def _async_update_data(self) -> dict:
        """Fetch agents, stacks, scheduler, and last update from Dockge API."""
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch agents (for name mapping)
                async with session.get(
                    f"{self.url}/api/agents", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    resp.raise_for_status()
                    agents_resp = await resp.json()

                # Fetch all stacks (from all agents) — longer timeout since it proxies to agents
                async with session.get(
                    f"{self.url}/api/stacks", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    resp.raise_for_status()
                    stacks_resp = await resp.json()

                # Fetch scheduler status
                async with session.get(
                    f"{self.url}/api/scheduler", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    resp.raise_for_status()
                    scheduler_resp = await resp.json()

                # Fetch most recent update history entry
                async with session.get(
                    f"{self.url}/api/update-history?limit=1", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    resp.raise_for_status()
                    history_resp = await resp.json()

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with Dockge API: {err}") from err

        # Unwrap API envelope responses
        agents = agents_resp.get("agents", []) if isinstance(agents_resp, dict) else []
        stacks = stacks_resp.get("stacks", []) if isinstance(stacks_resp, dict) else []
        scheduler = scheduler_resp if isinstance(scheduler_resp, dict) else {}
        history_entries = history_resp.get("entries", []) if isinstance(history_resp, dict) else []
        last_update = history_entries[0] if history_entries else None

        # Build agent name map for entity naming
        agent_names = self._agent_name_map(agents)
        multi_agent = len(agents) > 1

        # Preserve stacks from agents that are known but returned no stacks
        # (e.g. agent temporarily disconnected from Dockge primary)
        if self.data and multi_agent:
            known_endpoints = {a.get("endpoint", "") for a in agents}
            returned_endpoints = {s.get("endpoint", "") for s in stacks}
            missing_endpoints = known_endpoints - returned_endpoints
            if missing_endpoints:
                prev_stacks = self.data.get("stacks") or []
                for prev in prev_stacks:
                    if prev.get("endpoint", "") in missing_endpoints:
                        stacks.append(prev)
                _LOGGER.debug(
                    "Preserved stacks from temporarily missing agents: %s",
                    missing_endpoints,
                )

        return {
            "agents": agents,
            "agent_names": agent_names,
            "multi_agent": multi_agent,
            "stacks": stacks,
            "scheduler": scheduler,
            "last_update": last_update,
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
                    try:
                        return await resp.json()
                    except (aiohttp.ContentTypeError, ValueError):
                        return None
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Dockge API call failed: {err}") from err
