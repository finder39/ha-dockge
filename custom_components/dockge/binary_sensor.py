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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dockge binary sensors (one per stack, dynamically tracked)."""
    coordinator: DockgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    tracked: set[str] = set()

    @callback
    def _async_add_new_entities() -> None:
        """Add entities for any new stacks found in coordinator data."""
        stacks = coordinator.data.get("stacks") or []
        new_entities = []
        for stack in stacks:
            key = f"{stack.get('endpoint', '')}|{stack['name']}"
            if key not in tracked:
                tracked.add(key)
                new_entities.append(
                    DockgeStackUpdateAvailableBinarySensor(coordinator, entry, stack)
                )
        if new_entities:
            async_add_entities(new_entities)

    # Add initial entities
    _async_add_new_entities()

    # Listen for coordinator updates to add new stacks dynamically
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_entities))


def _agent_display_name(coordinator: DockgeCoordinator, endpoint: str) -> str:
    """Get the display name for an agent endpoint."""
    agent_names = coordinator.data.get("agent_names", {})
    return agent_names.get(endpoint, endpoint or "primary")


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

        # Include agent name in entity name when multi-agent
        agent_label = _agent_display_name(coordinator, self._endpoint)
        if coordinator.data.get("multi_agent"):
            self._attr_name = f"Dockge {self._stack_name} ({agent_label}) Update Available"
        else:
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
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._get_stack() is not None

    @property
    def extra_state_attributes(self) -> dict:
        stack = self._get_stack()
        agent_name = _agent_display_name(self.coordinator, self._endpoint)
        if not stack:
            return {"endpoint": self._endpoint, "agent": agent_name}
        return {
            "endpoint": self._endpoint,
            "agent": agent_name,
            "auto_update_enabled": stack.get("autoUpdate", False),
            "status": stack.get("status"),
        }
