"""Sensor platform for the Dockge integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DockgeCoordinator
from .devices import agent_device_info, agent_display_name


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dockge sensors."""
    coordinator: DockgeCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Create global sensors for each agent endpoint
    entities: list[SensorEntity] = []
    agents = coordinator.data.get("agents") or []
    agent_names = coordinator.data.get("agent_names", {})

    # If no agents returned, create sensors under a default "Primary" agent
    if not agents:
        agents = [{"endpoint": ""}]

    for agent in agents:
        endpoint = agent.get("endpoint", "")
        name = agent_display_name(agent_names, endpoint)
        entities.extend([
            DockgeUpdatesAvailableSensor(coordinator, entry, endpoint, name),
            DockgeSchedulerStatusSensor(coordinator, entry, endpoint, name),
            DockgeLastUpdateSensor(coordinator, entry, endpoint, name),
        ])

    async_add_entities(entities)


class DockgeUpdatesAvailableSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing count of stacks with available image updates."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:update"
    _attr_translation_key = "updates_available"

    def __init__(
        self, coordinator: DockgeCoordinator, entry: ConfigEntry,
        endpoint: str, agent_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._endpoint = endpoint
        self._attr_unique_id = f"{entry.entry_id}_updates_available_{endpoint}"
        self._attr_name = "Updates Available"
        self._attr_device_info = agent_device_info(entry.entry_id, endpoint, agent_name)

    @property
    def native_value(self) -> int:
        stacks = self.coordinator.data.get("stacks") or []
        return sum(
            1 for s in stacks
            if s.get("imageUpdatesAvailable") and s.get("endpoint", "") == self._endpoint
        )

    @property
    def extra_state_attributes(self) -> dict:
        stacks = self.coordinator.data.get("stacks") or []
        agent_stacks = [s for s in stacks if s.get("endpoint", "") == self._endpoint]
        return {"total_stacks": len(agent_stacks)}


class DockgeSchedulerStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing scheduler enabled/disabled status."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self, coordinator: DockgeCoordinator, entry: ConfigEntry,
        endpoint: str, agent_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_scheduler_status_{endpoint}"
        self._attr_name = "Scheduler"
        self._attr_device_info = agent_device_info(entry.entry_id, endpoint, agent_name)

    @property
    def native_value(self) -> str:
        scheduler = self.coordinator.data.get("scheduler") or {}
        return "enabled" if scheduler.get("enabled") else "disabled"

    @property
    def extra_state_attributes(self) -> dict:
        scheduler = self.coordinator.data.get("scheduler") or {}
        return {
            "cron_expression": scheduler.get("cronExpression"),
            "prune_after_update": scheduler.get("pruneAfterUpdate"),
            "prune_all_after_update": scheduler.get("pruneAllAfterUpdate"),
        }


class DockgeLastUpdateSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing timestamp of the most recent update."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:history"

    def __init__(
        self, coordinator: DockgeCoordinator, entry: ConfigEntry,
        endpoint: str, agent_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_update_{endpoint}"
        self._attr_name = "Last Update"
        self._attr_device_info = agent_device_info(entry.entry_id, endpoint, agent_name)

    @property
    def native_value(self) -> str | None:
        entry = self.coordinator.data.get("last_update")
        if not entry:
            return None
        return entry.get("completedAt") or entry.get("startedAt")

    @property
    def extra_state_attributes(self) -> dict:
        entry = self.coordinator.data.get("last_update")
        if not entry:
            return {}
        return {
            "stack": entry.get("stackName"),
            "endpoint": entry.get("endpoint", ""),
            "success": entry.get("success"),
            "trigger": entry.get("triggerType"),
            "duration_ms": entry.get("durationMs"),
        }
