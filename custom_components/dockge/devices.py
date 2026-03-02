"""Device info helpers for the Dockge integration."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def agent_display_name(agent_names: dict[str, str], endpoint: str) -> str:
    """Get the display name for an agent endpoint."""
    return agent_names.get(endpoint, endpoint or "Primary")


def agent_device_info(entry_id: str, endpoint: str, agent_name: str) -> DeviceInfo:
    """Return DeviceInfo for an agent (server-level) device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{endpoint}")},
        name=f"Dockge - {agent_name}",
        manufacturer="Dockge",
        model="Docker Compose Manager",
        entry_type=None,
    )


def stack_device_info(
    entry_id: str, endpoint: str, stack_name: str, agent_name: str,
) -> DeviceInfo:
    """Return DeviceInfo for a stack device, child of its agent device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{endpoint}_{stack_name}")},
        name=stack_name,
        manufacturer="Dockge",
        model="Docker Compose Stack",
        via_device=(DOMAIN, f"{entry_id}_{endpoint}"),
    )
