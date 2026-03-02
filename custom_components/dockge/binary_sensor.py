"""Binary sensor platform for the Dockge integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DockgeCoordinator
from .devices import agent_display_name, stack_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dockge binary sensors (one per stack, dynamically tracked)."""
    coordinator: DockgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    tracked: set[str] = set()

    @callback
    def _async_add_new_entities() -> None:
        stacks = coordinator.data.get("stacks") or []
        agent_names = coordinator.data.get("agent_names", {})
        new_entities = []
        for stack in stacks:
            key = f"{stack.get('endpoint', '')}|{stack['name']}"
            if key not in tracked:
                tracked.add(key)
                endpoint = stack.get("endpoint", "")
                name = agent_display_name(agent_names, endpoint)
                new_entities.append(
                    DockgeStackUpdateAvailableBinarySensor(
                        coordinator, entry, stack, name,
                    )
                )
        if new_entities:
            async_add_entities(new_entities)

    _async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_entities))


class DockgeStackUpdateAvailableBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that is on when a stack has image updates available."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.UPDATE

    def __init__(
        self, coordinator: DockgeCoordinator, entry: ConfigEntry,
        stack: dict, agent_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._stack_name = stack["name"]
        self._endpoint = stack.get("endpoint", "")
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_stack_{self._endpoint}_{self._stack_name}"
        self._attr_name = "Update Available"
        self._attr_device_info = stack_device_info(
            entry.entry_id, self._endpoint, self._stack_name, agent_name,
        )

    def _get_stack(self) -> dict | None:
        for s in self.coordinator.data.get("stacks") or []:
            if s["name"] == self._stack_name and s.get("endpoint", "") == self._endpoint:
                return s
        return None

    @property
    def is_on(self) -> bool:
        stack = self._get_stack()
        return bool(stack and stack.get("imageUpdatesAvailable"))

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._get_stack() is not None

    @property
    def extra_state_attributes(self) -> dict:
        stack = self._get_stack()
        if not stack:
            return {}
        return {
            "auto_update_enabled": stack.get("autoUpdate", False),
            "status": stack.get("status"),
        }
