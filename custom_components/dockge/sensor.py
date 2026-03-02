"""Sensor platform for the Dockge integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DockgeCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dockge sensors."""
    coordinator: DockgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        DockgeUpdatesAvailableSensor(coordinator, entry),
        DockgeSchedulerStatusSensor(coordinator, entry),
        DockgeLastUpdateSensor(coordinator, entry),
    ])


class DockgeUpdatesAvailableSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing count of stacks with available image updates (across all agents)."""

    _attr_icon = "mdi:update"

    def __init__(self, coordinator: DockgeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_updates_available"
        self._attr_name = "Dockge Updates Available"

    @property
    def native_value(self) -> int:
        stacks = self.coordinator.data.get("stacks") or []
        return sum(1 for s in stacks if s.get("imageUpdatesAvailable"))

    @property
    def extra_state_attributes(self) -> dict:
        stacks = self.coordinator.data.get("stacks") or []
        total = len(stacks)
        agents = self.coordinator.data.get("agents") or []
        return {
            "total_stacks": total,
            "total_agents": len(agents),
        }


class DockgeSchedulerStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing scheduler enabled/disabled status."""

    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: DockgeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_scheduler_status"
        self._attr_name = "Dockge Scheduler"

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

    _attr_icon = "mdi:history"

    def __init__(self, coordinator: DockgeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_update"
        self._attr_name = "Dockge Last Update"

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
