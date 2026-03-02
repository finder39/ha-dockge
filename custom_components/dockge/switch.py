"""Switch platform for the Dockge integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DockgeCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dockge switches (auto-update toggle per stack)."""
    coordinator: DockgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    stacks = coordinator.data.get("stacks") or []
    async_add_entities([
        DockgeAutoUpdateSwitch(coordinator, entry, stack) for stack in stacks
    ])


class DockgeAutoUpdateSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to toggle auto-update for a stack."""

    _attr_icon = "mdi:autorenew"

    def __init__(
        self, coordinator: DockgeCoordinator, entry: ConfigEntry, stack: dict
    ) -> None:
        super().__init__(coordinator)
        self._stack_name = stack["name"]
        self._endpoint = stack.get("endpoint", "")
        self._attr_unique_id = f"{entry.entry_id}_auto_update_{self._endpoint}_{self._stack_name}"
        self._attr_name = f"Dockge {self._stack_name} Auto Update"

    def _get_stack(self) -> dict | None:
        for s in self.coordinator.data.get("stacks") or []:
            if s["name"] == self._stack_name and s.get("endpoint", "") == self._endpoint:
                return s
        return None

    @property
    def is_on(self) -> bool:
        stack = self._get_stack()
        return bool(stack and stack.get("autoUpdate"))

    async def _set_auto_update(self, enabled: bool) -> None:
        endpoint_param = f"?endpoint={self._endpoint}" if self._endpoint else ""
        await self.coordinator.api_call(
            "PUT",
            f"/api/stacks/{self._stack_name}/auto-update{endpoint_param}",
            json={"enabled": enabled},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_auto_update(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_auto_update(False)
