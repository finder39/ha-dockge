"""The Dockge integration."""

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
        await coordinator.api_call("POST", f"/api/stacks/{stack_name}/{action_path}{endpoint_param}")

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
        await coordinator.api_call("POST", f"/api/update-all{endpoint_param}")

    hass.services.async_register(
        DOMAIN, "update_all", _handle_update_all,
        schema=vol.Schema({vol.Optional("agent", default=""): cv.string}),
    )

    async def _handle_trigger_auto_updates(call) -> None:
        await coordinator.api_call("POST", "/api/scheduler/trigger")

    hass.services.async_register(
        DOMAIN, "trigger_auto_updates", _handle_trigger_auto_updates,
        schema=vol.Schema({}),
    )

    # Clean up devices for stacks that no longer exist
    _cleanup_stale_devices(hass, entry, coordinator)
    entry.async_on_unload(
        coordinator.async_add_listener(lambda: _cleanup_stale_devices(hass, entry, coordinator))
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    for svc in ["start_stack", "stop_stack", "restart_stack", "update_stack", "check_updates", "update_all", "trigger_auto_updates"]:
        hass.services.async_remove(DOMAIN, svc)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _cleanup_stale_devices(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: DockgeCoordinator
) -> None:
    """Remove devices for stacks/agents that no longer exist."""
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    # Build set of active device identifiers from current coordinator data
    active_ids: set[tuple[str, str]] = set()
    agents = coordinator.data.get("agents") or []
    for agent in agents:
        ep = agent.get("endpoint", "")
        active_ids.add((DOMAIN, f"{entry.entry_id}_{ep}"))
    stacks = coordinator.data.get("stacks") or []
    for stack in stacks:
        ep = stack.get("endpoint", "")
        active_ids.add((DOMAIN, f"{entry.entry_id}_{ep}_{stack['name']}"))

    # Find and remove devices that belong to this entry but are no longer active
    for device in dr.async_entries_for_config_entry(device_reg, entry.entry_id):
        # Check if any of the device's identifiers are still active
        if device.identifiers.intersection(active_ids):
            continue

        # Remove all entities for this device first
        for entity in er.async_entries_for_device(entity_reg, device.id, include_disabled_entities=True):
            if entity.config_entry_id == entry.entry_id:
                entity_reg.async_remove(entity.entity_id)

        # Remove the device
        _LOGGER.info("Removing stale Dockge device: %s", device.name)
        device_reg.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
