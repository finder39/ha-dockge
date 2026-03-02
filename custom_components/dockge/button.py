"""Button platform for the Dockge integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DockgeCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dockge buttons."""
    coordinator: DockgeCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Global buttons (always present)
    entities: list[ButtonEntity] = [
        DockgeUpdateAllButton(coordinator, entry),
        DockgeTriggerScheduledButton(coordinator, entry),
    ]

    # Per-stack update buttons (dynamically tracked)
    tracked: set[str] = set()

    @callback
    def _async_add_new_entities() -> None:
        stacks = coordinator.data.get("stacks") or []
        new_entities = []
        for stack in stacks:
            key = f"{stack.get('endpoint', '')}|{stack['name']}"
            if key not in tracked:
                tracked.add(key)
                new_entities.append(
                    DockgeUpdateStackButton(coordinator, entry, stack)
                )
        if new_entities:
            async_add_entities(new_entities)

    # Add initial per-stack buttons
    stacks = coordinator.data.get("stacks") or []
    for stack in stacks:
        key = f"{stack.get('endpoint', '')}|{stack['name']}"
        tracked.add(key)
        entities.append(DockgeUpdateStackButton(coordinator, entry, stack))

    async_add_entities(entities)

    # Listen for new stacks
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_entities))


def _agent_display_name(coordinator: DockgeCoordinator, endpoint: str) -> str:
    agent_names = coordinator.data.get("agent_names", {})
    return agent_names.get(endpoint, endpoint or "primary")


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

        agent_label = _agent_display_name(coordinator, self._endpoint)
        if coordinator.data.get("multi_agent"):
            self._attr_name = f"Dockge Update {self._stack_name} ({agent_label})"
        else:
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
