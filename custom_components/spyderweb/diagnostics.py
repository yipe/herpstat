"""Downloadable diagnostics: entry settings and the last /RAWSTATUS payload, with identifiers redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import SpyderWebConfigEntry

TO_REDACT = {CONF_HOST, "mac", "ip"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SpyderWebConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "rawstatus": async_redact_data(coordinator.data.raw, TO_REDACT),
    }
