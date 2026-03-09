"""The Dockge integration."""

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er

from .const import DOMAIN
from .coordinator import DockgeCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "button", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dockge from a config entry."""
    _LOGGER.debug("Setting up Dockge entry %s with data: %s", entry.entry_id, {k: v for k, v in entry.data.items() if k != "api_key"})
    try:
        coordinator = DockgeCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        _LOGGER.exception("Failed to set up Dockge coordinator")
        raise

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    def _resolve_endpoint(agent_name: str) -> str:
        """Resolve agent display name to endpoint. Empty string = primary."""
        if not agent_name:
            return ""
        # Build reverse map: lowercase name → endpoint
        agent_names_map = coordinator.data.get("agent_names", {})
        for ep, name in agent_names_map.items():
            if name.lower() == agent_name.lower():
                return ep
        # If no match, treat as raw endpoint for backwards compat
        return agent_name

    STACK_ACTION_SCHEMA = vol.Schema({
        vol.Required("stack_name"): cv.string,
        vol.Optional("agent", default=""): cv.string,
    })

    async def _handle_stack_action(call, action_path: str) -> None:
        stack_name = call.data["stack_name"]
        endpoint = _resolve_endpoint(call.data.get("agent", ""))
        endpoint_param = f"?endpoint={endpoint}" if endpoint else ""
        coordinator.mark_busy(endpoint, stack_name)
        await asyncio.sleep(0.1)  # Let event loop propagate busy state to frontend
        try:
            await coordinator.api_call("POST", f"/api/stacks/{stack_name}/{action_path}{endpoint_param}")
        finally:
            coordinator.mark_done(endpoint, stack_name)
            await coordinator.async_request_refresh()
            coordinator.start_refresh_burst()

    def _make_stack_handler(action_path: str):
        async def handler(call) -> None:
            await _handle_stack_action(call, action_path)
        return handler

    for service_name, path in [
        ("start_stack", "start"),
        ("stop_stack", "stop"),
        ("restart_stack", "restart"),
        ("update_stack", "update"),
        ("check_updates", "check-updates"),
    ]:
        hass.services.async_register(
            DOMAIN, service_name,
            _make_stack_handler(path),
            schema=STACK_ACTION_SCHEMA,
        )

    async def _handle_update_all(call) -> None:
        endpoint = _resolve_endpoint(call.data.get("agent", ""))
        endpoint_param = f"?endpoint={endpoint}" if endpoint else ""
        stacks = coordinator.data.get("stacks") or []
        busy_keys = []
        for stack in stacks:
            ep = stack.get("endpoint", "")
            if endpoint == "" or ep == endpoint:
                coordinator.mark_busy(ep, stack["name"])
                busy_keys.append((ep, stack["name"]))
        await asyncio.sleep(0.1)  # Let event loop propagate busy state to frontend
        try:
            await coordinator.api_call("POST", f"/api/update-all{endpoint_param}")
        finally:
            for ep, name in busy_keys:
                coordinator.mark_done(ep, name)
            await coordinator.async_request_refresh()
            coordinator.start_refresh_burst()

    hass.services.async_register(
        DOMAIN, "update_all", _handle_update_all,
        schema=vol.Schema({vol.Optional("agent", default=""): cv.string}),
    )

    async def _handle_trigger_auto_updates(call) -> None:
        await coordinator.api_call("POST", "/api/scheduler/trigger")
        await coordinator.async_request_refresh()
        coordinator.start_refresh_burst()

    hass.services.async_register(
        DOMAIN, "trigger_auto_updates", _handle_trigger_auto_updates,
        schema=vol.Schema({}),
    )

    async def _handle_system_prune(call) -> None:
        endpoint = _resolve_endpoint(call.data.get("agent", ""))
        endpoint_param = f"?endpoint={endpoint}" if endpoint else ""
        await coordinator.api_call("POST", f"/api/system/prune{endpoint_param}")
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, "system_prune", _handle_system_prune,
        schema=vol.Schema({vol.Optional("agent", default=""): cv.string}),
    )

    # NOTE: We intentionally do NOT auto-delete stale devices/entities.
    # Agents and stacks that are temporarily offline would get removed and
    # reappear on next poll, which is jarring. Instead, users can manually
    # delete stale devices from the HA device page.

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    for svc in ["start_stack", "stop_stack", "restart_stack", "update_stack", "check_updates", "update_all", "trigger_auto_updates", "system_prune"]:
        hass.services.async_remove(DOMAIN, svc)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _cleanup_stale_devices(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: DockgeCoordinator
) -> None:
    """Remove devices and entities that no longer exist."""
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    agents = coordinator.data.get("agents") or []
    stacks = coordinator.data.get("stacks") or []

    # Determine which agent endpoints returned stacks vs are known but empty
    # (empty agents are likely temporarily disconnected — don't clean up their devices)
    endpoints_with_stacks = {s.get("endpoint", "") for s in stacks}
    empty_agent_endpoints = {
        a.get("endpoint", "") for a in agents
    } - endpoints_with_stacks

    if empty_agent_endpoints:
        agent_names = coordinator.data.get("agent_names", {})
        empty_names = [agent_names.get(ep, ep) for ep in empty_agent_endpoints]
        _LOGGER.debug(
            "Skipping cleanup for agents with no stacks (likely disconnected): %s",
            empty_names,
        )

    # Build set of active device identifiers
    active_ids: set[tuple[str, str]] = set()
    for agent in agents:
        ep = agent.get("endpoint", "")
        active_ids.add((DOMAIN, f"{entry.entry_id}_{ep}"))
    for stack in stacks:
        ep = stack.get("endpoint", "")
        active_ids.add((DOMAIN, f"{entry.entry_id}_{ep}_{stack['name']}"))

    # Build set of valid entity unique_ids
    eid = entry.entry_id
    valid_unique_ids: set[str] = set()

    if len(agents) > 1:
        valid_unique_ids.add(f"{eid}_global_summary")

    for agent in agents:
        ep = agent.get("endpoint", "")
        valid_unique_ids.add(f"{eid}_updates_available_{ep}")
        valid_unique_ids.add(f"{eid}_agent_summary_{ep}")
        valid_unique_ids.add(f"{eid}_version_{ep}")
        # Scheduler sensors are primary-only
        if ep == "":
            valid_unique_ids.add(f"{eid}_scheduler_status_{ep}")
            valid_unique_ids.add(f"{eid}_last_update_{ep}")
            valid_unique_ids.add(f"{eid}_next_auto_update_{ep}")
            valid_unique_ids.add(f"{eid}_next_image_check_{ep}")

    for stack in stacks:
        ep = stack.get("endpoint", "")
        sname = stack["name"]
        valid_unique_ids.add(f"{eid}_stack_{ep}_{sname}")
        for svc_name in (stack.get("services") or {}):
            valid_unique_ids.add(f"{eid}_container_{ep}_{sname}_{svc_name}")
            valid_unique_ids.add(f"{eid}_container_update_{ep}_{sname}_{svc_name}")

    # Also include button/switch unique_ids
    for stack in stacks:
        ep = stack.get("endpoint", "")
        sname = stack["name"]
        valid_unique_ids.add(f"{eid}_update_{ep}_{sname}")
        valid_unique_ids.add(f"{eid}_check_updates_{ep}_{sname}")
        valid_unique_ids.add(f"{eid}_auto_update_{ep}_{sname}")

    # Build set of device identifiers belonging to disconnected agents
    # These are agents in /api/agents but returning no stacks — keep all their devices/entities
    protected_device_ids: set[tuple[str, str]] = set()
    for ep in empty_agent_endpoints:
        if not ep:
            continue
        # Protect the agent device itself
        protected_device_ids.add((DOMAIN, f"{eid}_{ep}"))
        # Protect any stack devices under this agent (from prior data)
        for device in dr.async_entries_for_config_entry(device_reg, entry.entry_id):
            for ident in device.identifiers:
                if len(ident) > 1 and ident[0] == DOMAIN and ident[1].startswith(f"{eid}_{ep}_"):
                    protected_device_ids.add(ident)

    # Build set of entity unique_ids belonging to protected devices
    protected_entity_prefixes = tuple(f"{eid}_" + suffix for ep in empty_agent_endpoints if ep for suffix in [
        f"container_{ep}_", f"container_update_{ep}_", f"stack_{ep}_",
        f"update_{ep}_", f"check_updates_{ep}_", f"auto_update_{ep}_",
    ])

    # Remove stale entities — but skip entities belonging to disconnected agents
    for ent in er.async_entries_for_config_entry(entity_reg, entry.entry_id):
        if ent.unique_id in valid_unique_ids:
            continue
        if protected_entity_prefixes and ent.unique_id.startswith(protected_entity_prefixes):
            continue
        _LOGGER.info("Removing stale Dockge entity: %s (%s)", ent.entity_id, ent.unique_id)
        entity_reg.async_remove(ent.entity_id)

    # Remove stale devices — but skip devices belonging to disconnected agents
    for device in dr.async_entries_for_config_entry(device_reg, entry.entry_id):
        if device.identifiers.intersection(active_ids):
            continue
        if device.identifiers.intersection(protected_device_ids):
            _LOGGER.debug("Keeping device for disconnected agent: %s", device.name)
            continue
        _LOGGER.info("Removing stale Dockge device: %s", device.name)
        device_reg.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
