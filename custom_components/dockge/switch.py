"""Switch platform for the Dockge integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
    """Set up Dockge switches (auto-update toggle per stack, dynamically tracked)."""
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
                is_multi = coordinator.data.get("multi_agent", False)
                new_entities.append(
                    DockgeAutoUpdateSwitch(coordinator, entry, stack, name, multi_agent=is_multi)
                )
        if new_entities:
            async_add_entities(new_entities)

    _async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_entities))


class DockgeAutoUpdateSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to toggle auto-update for a stack."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:autorenew"

    def __init__(
        self, coordinator: DockgeCoordinator, entry: ConfigEntry,
        stack: dict, agent_name: str, *, multi_agent: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self._stack_name = stack["name"]
        self._endpoint = stack.get("endpoint", "")
        self._attr_unique_id = f"{entry.entry_id}_auto_update_{self._endpoint}_{self._stack_name}"
        self._attr_name = "Auto Update"
        self._attr_device_info = stack_device_info(
            entry.entry_id, self._endpoint, self._stack_name, agent_name,
            multi_agent=multi_agent,
        )

    def _get_stack(self) -> dict | None:
        for s in self.coordinator.data.get("stacks") or []:
            if s["name"] == self._stack_name and s.get("endpoint", "") == self._endpoint:
                return s
        return None

    @property
    def is_on(self) -> bool:
        stack = self._get_stack()
        return bool(stack and stack.get("autoUpdate"))

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._get_stack() is not None

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
