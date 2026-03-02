"""Binary sensor platform for the Dockge integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DockgeCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dockge binary sensors (one per stack)."""
    coordinator: DockgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    stacks = coordinator.data.get("stacks") or []
    async_add_entities([
        DockgeStackUpdateAvailableBinarySensor(coordinator, entry, stack)
        for stack in stacks
    ])


class DockgeStackUpdateAvailableBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that is on when a stack has image updates available."""

    _attr_device_class = BinarySensorDeviceClass.UPDATE

    def __init__(
        self, coordinator: DockgeCoordinator, entry: ConfigEntry, stack: dict
    ) -> None:
        super().__init__(coordinator)
        self._stack_name = stack["name"]
        self._endpoint = stack.get("endpoint", "")
        self._attr_unique_id = f"{entry.entry_id}_stack_{self._endpoint}_{self._stack_name}"
        self._attr_name = f"Dockge {self._stack_name} Update Available"

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
    def extra_state_attributes(self) -> dict:
        stack = self._get_stack()
        if not stack:
            return {"endpoint": self._endpoint}
        return {
            "endpoint": self._endpoint,
            "auto_update_enabled": stack.get("autoUpdate", False),
            "status": stack.get("status"),
        }
