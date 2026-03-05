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
    """Set up Dockge binary sensors."""
    coordinator: DockgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    tracked_stacks: set[str] = set()
    tracked_containers: set[str] = set()

    @callback
    def _async_add_new_entities() -> None:
        stacks = coordinator.data.get("stacks") or []
        agent_names = coordinator.data.get("agent_names", {})
        is_multi = coordinator.data.get("multi_agent", False)
        new_entities: list[BinarySensorEntity] = []
        for stack in stacks:
            endpoint = stack.get("endpoint", "")
            aname = agent_display_name(agent_names, endpoint)
            stack_key = f"{endpoint}|{stack['name']}"

            # Stack-level update available
            if stack_key not in tracked_stacks:
                tracked_stacks.add(stack_key)
                new_entities.append(
                    DockgeStackUpdateAvailableBinarySensor(
                        coordinator, entry, stack, aname,
                        multi_agent=is_multi,
                    )
                )

            # Per-container update available
            services = stack.get("services") or {}
            for svc_name in services:
                container_key = f"{endpoint}|{stack['name']}|{svc_name}"
                if container_key not in tracked_containers:
                    tracked_containers.add(container_key)
                    new_entities.append(
                        DockgeContainerUpdateAvailableBinarySensor(
                            coordinator, entry, stack["name"],
                            endpoint, aname, svc_name,
                            multi_agent=is_multi,
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
        stack: dict, agent_name: str, *, multi_agent: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self._stack_name = stack["name"]
        self._endpoint = stack.get("endpoint", "")
        self._attr_unique_id = f"{entry.entry_id}_stack_{self._endpoint}_{self._stack_name}"
        self._attr_name = "Update Available"
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


class DockgeContainerUpdateAvailableBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that is on when an individual container has an image update available."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.UPDATE

    def __init__(
        self, coordinator: DockgeCoordinator, entry: ConfigEntry,
        stack_name: str, endpoint: str, agent_name: str, service_name: str,
        *, multi_agent: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self._stack_name = stack_name
        self._endpoint = endpoint
        self._service_name = service_name
        self._attr_unique_id = f"{entry.entry_id}_container_update_{endpoint}_{stack_name}_{service_name}"
        self._attr_name = f"{service_name} Update Available"
        self._attr_device_info = stack_device_info(
            entry.entry_id, endpoint, stack_name, agent_name,
            multi_agent=multi_agent,
        )

    def _get_service(self) -> dict | None:
        for s in self.coordinator.data.get("stacks") or []:
            if s["name"] == self._stack_name and s.get("endpoint", "") == self._endpoint:
                services = s.get("services") or {}
                return services.get(self._service_name)
        return None

    @property
    def is_on(self) -> bool:
        svc = self._get_service()
        return bool(svc and svc.get("imageUpdateAvailable"))

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._get_service() is not None
