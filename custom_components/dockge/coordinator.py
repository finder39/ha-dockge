"""DataUpdateCoordinator for the Dockge integration."""

from __future__ import annotations

import asyncio
import json
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
        self._busy_stacks: set[str] = set()
        self._sse_task: asyncio.Task | None = None
        self._sse_session: aiohttp.ClientSession | None = None
        self._sse_stop_event = asyncio.Event()
        self._sse_watchdog_handle: asyncio.TimerHandle | None = None
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
        """Fetch agents, stacks, scheduler, and last update from Dockge API.

        Retries every 15 seconds for up to 5 minutes if the API is unreachable
        (e.g. after Dockge updates its own stack and restarts).
        """
        max_retries = 20  # 20 * 15s = 5 minutes
        last_err: Exception | None = None

        for attempt in range(max_retries):
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

                break  # Success — exit retry loop

            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_err = err
                if attempt < max_retries - 1:
                    _LOGGER.debug(
                        "Dockge API unreachable (attempt %d/%d), retrying in 15s: %s",
                        attempt + 1, max_retries, err,
                    )
                    await asyncio.sleep(15)
                else:
                    raise UpdateFailed(
                        f"Dockge API unreachable after {max_retries} retries (~5 min): {err}"
                    ) from err

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

    async def api_call(
        self, method: str, path: str, json: dict | None = None, *, retry: bool = False,
    ) -> dict | list | None:
        """Make an API call to Dockge (for actions like update, toggle).

        If retry=True, retries every 15s for up to 5 minutes on failure.
        Use this when the call may cause Dockge to restart (e.g. self-update).
        """
        max_attempts = 20 if retry else 1  # 20 * 15s = 5 minutes

        for attempt in range(max_attempts):
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
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                if attempt < max_attempts - 1:
                    _LOGGER.debug(
                        "API call %s %s failed (attempt %d/%d), retrying in 15s: %s",
                        method, path, attempt + 1, max_attempts, err,
                    )
                    await asyncio.sleep(15)
                else:
                    raise UpdateFailed(
                        f"Dockge API call failed: {err}"
                    ) from err
        return None

    def _busy_key(self, endpoint: str, stack_name: str) -> str:
        """Build a unique key for a busy stack."""
        return f"{endpoint}_{stack_name}"

    def is_stack_busy(self, endpoint: str, stack_name: str) -> bool:
        """Check if a stack is currently processing an operation."""
        return self._busy_key(endpoint, stack_name) in self._busy_stacks

    def mark_busy(self, endpoint: str, stack_name: str) -> None:
        """Mark a stack as busy and notify entities immediately."""
        key = self._busy_key(endpoint, stack_name)
        self._busy_stacks.add(key)
        _LOGGER.debug("Stack marked BUSY: %s (busy set: %s)", key, self._busy_stacks)
        # Pass a shallow copy so HA detects the data as "changed" and pushes to frontend
        self.async_set_updated_data({**self.data})

    def mark_done(self, endpoint: str, stack_name: str) -> None:
        """Mark a stack as no longer busy and notify entities immediately."""
        key = self._busy_key(endpoint, stack_name)
        self._busy_stacks.discard(key)
        _LOGGER.debug("Stack marked DONE: %s (busy set: %s)", key, self._busy_stacks)
        self.async_set_updated_data({**self.data})

    async def start_sse(self) -> None:
        """Start the SSE listener background task."""
        if self._sse_task is not None:
            return
        self._sse_stop_event.clear()
        self._sse_task = self.hass.async_create_background_task(
            self._sse_listen_loop(), "dockge_sse_listener"
        )

    async def stop_sse(self) -> None:
        """Stop the SSE listener."""
        self._sse_stop_event.set()
        if self._sse_task is not None:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except (asyncio.CancelledError, Exception):
                pass
            self._sse_task = None
        if self._sse_session is not None:
            await self._sse_session.close()
            self._sse_session = None
        self._cancel_watchdog()

    async def _sse_listen_loop(self) -> None:
        """Reconnecting SSE listener loop."""
        while not self._sse_stop_event.is_set():
            try:
                await self._sse_connect()
            except asyncio.CancelledError:
                return
            except Exception:
                _LOGGER.warning("SSE connection failed, retrying in 5s", exc_info=True)
            # Wait 5s before reconnecting (unless stopped)
            try:
                await asyncio.wait_for(self._sse_stop_event.wait(), timeout=5.0)
                return  # Stop event was set
            except asyncio.TimeoutError:
                pass  # Timeout = time to reconnect

    async def _sse_connect(self) -> None:
        """Open SSE connection and process events until disconnected."""
        if self._sse_session is None:
            self._sse_session = aiohttp.ClientSession()

        url = f"{self.url}/api/events"
        headers = {"X-API-Key": self.api_key}

        _LOGGER.debug("Connecting to SSE at %s", url)
        async with self._sse_session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=None)
        ) as resp:
            if resp.status != 200:
                _LOGGER.warning("SSE connection rejected: HTTP %s", resp.status)
                return

            _LOGGER.info("SSE connected to %s", url)
            self._reset_watchdog()

            event_name = ""
            async for line_bytes in resp.content:
                if self._sse_stop_event.is_set():
                    return

                line = line_bytes.decode("utf-8").rstrip("\n\r")

                if line.startswith("event: "):
                    event_name = line[7:]
                elif line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        data = json.loads(data_str)
                    except (json.JSONDecodeError, ValueError):
                        _LOGGER.warning("SSE malformed data: %s", data_str)
                        continue
                    self._handle_sse_event(event_name, data)
                    event_name = ""

        _LOGGER.warning("SSE connection closed by server")

    def _handle_sse_event(self, event: str, data: dict) -> None:
        """Handle a received SSE event."""
        if event == "heartbeat":
            self._reset_watchdog()
            return

        if event == "connected":
            _LOGGER.debug("SSE connected event received")
            self._reset_watchdog()
            return

        if event == "operation_started":
            stack = data.get("stack", "")
            endpoint = data.get("endpoint", "")
            _LOGGER.debug("SSE operation_started: %s on %s", stack, endpoint)
            self.mark_busy(endpoint, stack)
            return

        if event == "operation_completed":
            stack = data.get("stack", "")
            endpoint = data.get("endpoint", "")
            success = data.get("success", False)
            _LOGGER.debug(
                "SSE operation_completed: %s on %s (success=%s)", stack, endpoint, success
            )
            self.mark_done(endpoint, stack)
            self.hass.async_create_task(self.async_request_refresh())
            return

        if event == "image_check_completed":
            _LOGGER.debug("SSE image_check_completed")
            self.hass.async_create_task(self.async_request_refresh())
            return

        if event == "scheduler_run_completed":
            _LOGGER.debug("SSE scheduler_run_completed")
            self.hass.async_create_task(self.async_request_refresh())
            return

        _LOGGER.debug("SSE unknown event: %s", event)

    def _reset_watchdog(self) -> None:
        """Reset the heartbeat watchdog timer (90s)."""
        self._cancel_watchdog()
        self._sse_watchdog_handle = self.hass.loop.call_later(
            90.0, self._watchdog_expired
        )

    def _cancel_watchdog(self) -> None:
        """Cancel the watchdog timer."""
        if self._sse_watchdog_handle is not None:
            self._sse_watchdog_handle.cancel()
            self._sse_watchdog_handle = None

    def _watchdog_expired(self) -> None:
        """Called when no heartbeat received for 90s — force reconnect."""
        _LOGGER.warning("SSE heartbeat watchdog expired, forcing reconnect")
        if self._sse_task is not None:
            self._sse_task.cancel()
            self._sse_task = None
        self._sse_task = self.hass.async_create_background_task(
            self._sse_listen_loop(), "dockge_sse_listener"
        )
