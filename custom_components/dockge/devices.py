"""Device info helpers for the Dockge integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def agent_display_name(agent_names: dict[str, str], endpoint: str) -> str:
    """Get the display name for an agent endpoint."""
    return agent_names.get(endpoint, endpoint or "Primary")


def agent_device_info(
    entry_id: str, endpoint: str, agent_name: str, *, multi_agent: bool = False,
    version: str | None = None,
) -> DeviceInfo:
    """Return DeviceInfo for an agent (server-level) device."""
    if multi_agent:
        name = f"Dockge Server ({agent_name})"
    else:
        name = "Dockge Server"
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{endpoint}")},
        name=name,
        manufacturer="Dockge",
        model="Docker Compose Manager",
        entry_type=DeviceEntryType.SERVICE,
        sw_version=version,
    )


def stack_device_info(
    entry_id: str, endpoint: str, stack_name: str, agent_name: str,
    *, multi_agent: bool = False,
) -> DeviceInfo:
    """Return DeviceInfo for a stack device, child of its agent device."""
    if multi_agent:
        name = f"{stack_name} ({agent_name})"
    else:
        name = stack_name
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{endpoint}_{stack_name}")},
        name=name,
        manufacturer="Dockge",
        model="Docker Compose Stack",
        via_device=(DOMAIN, f"{entry_id}_{endpoint}"),
    )
