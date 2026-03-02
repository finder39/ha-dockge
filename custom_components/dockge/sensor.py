"""Sensor platform for the Dockge integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DockgeCoordinator
from .devices import agent_device_info, agent_display_name, stack_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dockge sensors."""
    coordinator: DockgeCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Agent-level sensors
    entities: list[SensorEntity] = []
    agents = coordinator.data.get("agents") or []
    agent_names = coordinator.data.get("agent_names", {})

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

    # Per-container sensors (dynamically tracked)
    tracked_containers: set[str] = set()

    @callback
    def _async_add_new_container_sensors() -> None:
        stacks = coordinator.data.get("stacks") or []
        names = coordinator.data.get("agent_names", {})
        new_entities: list[SensorEntity] = []
        for stack in stacks:
            endpoint = stack.get("endpoint", "")
            aname = agent_display_name(names, endpoint)
            services = stack.get("services") or {}
            for svc_name, svc_data in services.items():
                key = f"{endpoint}|{stack['name']}|{svc_name}"
                if key not in tracked_containers:
                    tracked_containers.add(key)
                    new_entities.append(
                        DockgeContainerSensor(
                            coordinator, entry, stack["name"],
                            endpoint, aname, svc_name, svc_data,
                        )
                    )
        if new_entities:
            async_add_entities(new_entities)

    # Add initial containers
    stacks = coordinator.data.get("stacks") or []
    for stack in stacks:
        endpoint = stack.get("endpoint", "")
        aname = agent_display_name(agent_names, endpoint)
        services = stack.get("services") or {}
        for svc_name, svc_data in services.items():
            key = f"{endpoint}|{stack['name']}|{svc_name}"
            tracked_containers.add(key)
            entities.append(
                DockgeContainerSensor(
                    coordinator, entry, stack["name"],
                    endpoint, aname, svc_name, svc_data,
                )
            )

    async_add_entities(entities)
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_container_sensors))


class DockgeContainerSensor(CoordinatorEntity, SensorEntity):
    """Sensor representing an individual container within a stack."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:docker"

    def __init__(
        self, coordinator: DockgeCoordinator, entry: ConfigEntry,
        stack_name: str, endpoint: str, agent_name: str,
        service_name: str, service_data: dict,
    ) -> None:
        super().__init__(coordinator)
        self._stack_name = stack_name
        self._endpoint = endpoint
        self._service_name = service_name
        self._attr_unique_id = f"{entry.entry_id}_container_{endpoint}_{stack_name}_{service_name}"
        self._attr_name = service_name
        self._attr_device_info = stack_device_info(
            entry.entry_id, endpoint, stack_name, agent_name,
        )

    def _get_service(self) -> dict | None:
        for s in self.coordinator.data.get("stacks") or []:
            if s["name"] == self._stack_name and s.get("endpoint", "") == self._endpoint:
                services = s.get("services") or {}
                return services.get(self._service_name)
        return None

    @property
    def native_value(self) -> str | None:
        svc = self._get_service()
        if not svc:
            return None
        return svc.get("state")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._get_service() is not None

    @staticmethod
    def _split_image(image: str) -> tuple[str, str]:
        """Split 'registry/name:tag' into (name, tag)."""
        if ":" in image and not image.endswith(":"):
            name, tag = image.rsplit(":", 1)
            # Avoid splitting on port numbers (e.g. registry:5000/image)
            if "/" in tag:
                return image, "latest"
            return name, tag
        return image, "latest"

    @property
    def extra_state_attributes(self) -> dict:
        svc = self._get_service()
        if not svc:
            return {}
        image = svc.get("image", "")
        image_name, image_tag = self._split_image(image)
        return {
            "container_name": svc.get("containerName"),
            "image": image,
            "image_name": image_name,
            "image_tag": image_tag,
            "status": svc.get("status"),
            "health": svc.get("health"),
            "image_update_available": svc.get("imageUpdateAvailable", False),
        }


class DockgeUpdatesAvailableSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing count of stacks with available image updates."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:update"

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
