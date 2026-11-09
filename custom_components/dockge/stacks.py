"""Pure helpers for working with the stack list returned by Dockge."""

from __future__ import annotations

from typing import Any

from .const import DOMAIN


def is_managed(stack: dict[str, Any]) -> bool:
    """Return True if the stack lives in Dockge's stacks folder.

    Dockge also lists every other Compose project it finds with
    `docker compose ls` (flagged `isManagedByDockge: false`). Older Dockge
    versions don't send the flag, so a missing value counts as managed.
    """
    return bool(stack.get("isManagedByDockge", True))


def split_unmanaged(
    stacks: list[dict[str, Any]], hide_unmanaged: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split stacks into (shown, hidden) according to the option."""
    if not hide_unmanaged:
        return stacks, []
    shown = [s for s in stacks if is_managed(s)]
    hidden = [s for s in stacks if not is_managed(s)]
    return shown, hidden


def stack_device_identifier(entry_id: str, endpoint: str, stack_name: str) -> tuple[str, str]:
    """Device registry identifier of a stack device (matches devices.stack_device_info)."""
    return (DOMAIN, f"{entry_id}_{endpoint}_{stack_name}")


def active_device_identifiers(entry_id: str, data: dict[str, Any]) -> set[tuple[str, str]]:
    """Identifiers of every agent and stack device currently provided by the coordinator."""
    active: set[tuple[str, str]] = set()
    for agent in data.get("agents") or []:
        active.add((DOMAIN, f"{entry_id}_{agent.get('endpoint', '')}"))
    for stack in data.get("stacks") or []:
        active.add(stack_device_identifier(entry_id, stack.get("endpoint", ""), stack["name"]))
    return active
