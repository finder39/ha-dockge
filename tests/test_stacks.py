"""Tests for the unmanaged-stack helpers."""
from custom_components.dockge.stacks import (
    active_device_identifiers,
    is_managed,
    split_unmanaged,
    stack_device_identifier,
)

STACKS = [
    {"name": "loki", "endpoint": "", "isManagedByDockge": True},
    {"name": "agiledev", "endpoint": "", "isManagedByDockge": False},
    {"name": "old-dockge", "endpoint": ""},  # older Dockge: no flag
]


def test_missing_flag_counts_as_managed():
    assert is_managed({"name": "x"})
    assert is_managed({"name": "x", "isManagedByDockge": True})
    assert not is_managed({"name": "x", "isManagedByDockge": False})


def test_option_off_keeps_everything():
    shown, hidden = split_unmanaged(STACKS, False)
    assert shown == STACKS
    assert hidden == []


def test_option_on_splits_unmanaged():
    shown, hidden = split_unmanaged(STACKS, True)
    assert [s["name"] for s in shown] == ["loki", "old-dockge"]
    assert [s["name"] for s in hidden] == ["agiledev"]


def test_device_identifiers_match_device_info():
    assert stack_device_identifier("e1", "", "loki") == ("dockge", "e1__loki")
    data = {"agents": [{"endpoint": ""}], "stacks": [{"name": "loki", "endpoint": ""}]}
    assert active_device_identifiers("e1", data) == {("dockge", "e1_"), ("dockge", "e1__loki")}
