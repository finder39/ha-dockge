"""Mock Home Assistant so the integration's pure helpers can be imported without it."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

for mod_name in [
    "voluptuous",
    "aiohttp",
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.update_coordinator",
]:
    sys.modules[mod_name] = MagicMock()
