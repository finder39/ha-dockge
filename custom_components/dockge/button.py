"""Button platform for the Dockge integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DockgeCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dockge buttons."""
    coordinator: DockgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    stacks = coordinator.data.get("stacks") or []

    entities: list[ButtonEntity] = [
        DockgeUpdateAllButton(coordinator, entry),
        DockgeTriggerScheduledButton(coordinator, entry),
    ]
    for stack in stacks:
        entities.append(DockgeUpdateStackButton(coordinator, entry, stack))

    async_add_entities(entities)


class DockgeUpdateStackButton(CoordinatorEntity, ButtonEntity):
    """Button to trigger update for a single stack."""

    _attr_icon = "mdi:package-up"

    def __init__(
        self, coordinator: DockgeCoordinator, entry: ConfigEntry, stack: dict
    ) -> None:
        super().__init__(coordinator)
        self._stack_name = stack["name"]
        self._endpoint = stack.get("endpoint", "")
        self._attr_unique_id = f"{entry.entry_id}_update_{self._endpoint}_{self._stack_name}"
        self._attr_name = f"Dockge Update {self._stack_name}"

    async def async_press(self) -> None:
        endpoint_param = f"?endpoint={self._endpoint}" if self._endpoint else ""
        await self.coordinator.api_call(
            "POST", f"/api/stacks/{self._stack_name}/update{endpoint_param}"
        )
        await self.coordinator.async_request_refresh()


class DockgeUpdateAllButton(CoordinatorEntity, ButtonEntity):
    """Button to trigger update for all stacks."""

    _attr_icon = "mdi:package-variant-closed-plus"

    def __init__(self, coordinator: DockgeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_update_all"
        self._attr_name = "Dockge Update All"

    async def async_press(self) -> None:
        await self.coordinator.api_call("POST", "/api/update-all")
        await self.coordinator.async_request_refresh()


class DockgeTriggerScheduledButton(CoordinatorEntity, ButtonEntity):
    """Button to trigger the scheduled update run."""

    _attr_icon = "mdi:clock-start"

    def __init__(self, coordinator: DockgeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_trigger_scheduled"
        self._attr_name = "Dockge Trigger Scheduled Run"

    async def async_press(self) -> None:
        await self.coordinator.api_call("POST", "/api/scheduler/trigger")
        await self.coordinator.async_request_refresh()
