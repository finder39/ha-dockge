"""Update platform for the Dockge integration."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
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
    """Set up Dockge update entities."""
    coordinator: DockgeCoordinator = hass.data[DOMAIN][entry.entry_id]
    tracked: set[str] = set()

    @callback
    def _async_add_new_entities() -> None:
        stacks = coordinator.data.get("stacks") or []
        agent_names = coordinator.data.get("agent_names", {})
        is_multi = coordinator.data.get("multi_agent", False)
        new_entities: list[UpdateEntity] = []

        for stack in stacks:
            endpoint = stack.get("endpoint", "")
            key = f"{endpoint}|{stack['name']}"
            if key in tracked:
                continue

            tracked.add(key)
            new_entities.append(
                DockgeStackUpdateEntity(
                    coordinator,
                    entry,
                    stack,
                    agent_display_name(agent_names, endpoint),
                    multi_agent=is_multi,
                )
            )

        if new_entities:
            async_add_entities(new_entities)

    _async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_entities))


class DockgeStackUpdateEntity(CoordinatorEntity, UpdateEntity):
    """Update entity for a single Dockge stack."""

    _attr_has_entity_name = True
    _attr_name = "Image Update"
    _attr_icon = "mdi:package-up"
    _attr_supported_features = UpdateEntityFeature.INSTALL

    def __init__(
        self,
        coordinator: DockgeCoordinator,
        entry: ConfigEntry,
        stack: dict,
        agent_name: str,
        *,
        multi_agent: bool = False,
    ) -> None:
        """Initialize the stack update entity."""
        super().__init__(coordinator)
        self._stack_name = stack["name"]
        self._endpoint = stack.get("endpoint", "")
        self._agent_name = agent_name
        self._attr_unique_id = (
            f"{entry.entry_id}_stack_update_{self._endpoint}_{self._stack_name}"
        )
        self._attr_device_info = stack_device_info(
            entry.entry_id,
            self._endpoint,
            self._stack_name,
            agent_name,
            multi_agent=multi_agent,
        )

    def _get_stack(self) -> dict | None:
        """Return the current stack data."""
        for stack in self.coordinator.data.get("stacks") or []:
            if (
                stack["name"] == self._stack_name
                and stack.get("endpoint", "") == self._endpoint
            ):
                return stack
        return None

    @staticmethod
    def _service_images(stack: dict) -> list[str]:
        """Return service image names from a stack."""
        services = stack.get("services") or {}
        return [
            image
            for service in services.values()
            if (image := service.get("image"))
        ]

    @property
    def available(self) -> bool:
        """Return if the update entity is available."""
        return self.coordinator.last_update_success and self._get_stack() is not None

    @property
    def in_progress(self) -> bool:
        """Return if a stack update is currently running."""
        return self.coordinator.is_stack_busy(self._endpoint, self._stack_name)

    @property
    def title(self) -> str:
        """Return the title of the software represented by this entity."""
        return self._stack_name

    @property
    def installed_version(self) -> str | None:
        """Return the currently installed stack image set."""
        stack = self._get_stack()
        if not stack:
            return None
        images = self._service_images(stack)
        return ", ".join(images) if images else stack.get("status") or "installed"

    @property
    def latest_version(self) -> str | None:
        """Return the latest available stack image set."""
        stack = self._get_stack()
        if not stack:
            return None
        installed = self.installed_version
        if stack.get("imageUpdatesAvailable"):
            return "Update available"
        return installed

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        """Return True when Dockge reports an available image update."""
        stack = self._get_stack()
        return bool(stack and stack.get("imageUpdatesAvailable"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional stack update details."""
        stack = self._get_stack()
        base: dict[str, Any] = {
            "stack_name": self._stack_name,
            "agent_name": self._agent_name,
            "processing": self.in_progress,
        }
        if not stack:
            return base

        services = stack.get("services") or {}
        updateable_services = [
            name
            for name, service in services.items()
            if service.get("imageUpdateAvailable")
        ]
        return {
            **base,
            "auto_update_enabled": stack.get("autoUpdate", False),
            "status": stack.get("status"),
            "updateable_services": updateable_services,
            "updateable_service_count": len(updateable_services),
        }

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install the latest image update for this stack."""
        endpoint_param = f"?endpoint={self._endpoint}" if self._endpoint else ""
        self.coordinator.mark_busy(self._endpoint, self._stack_name)
        await asyncio.sleep(0.1)
        try:
            await self.coordinator.api_call(
                "POST",
                f"/api/stacks/{self._stack_name}/update{endpoint_param}",
                timeout=300,
            )
        finally:
            self.coordinator.mark_done(self._endpoint, self._stack_name)
            await self.coordinator.async_request_refresh()
            self.coordinator.start_refresh_burst()
