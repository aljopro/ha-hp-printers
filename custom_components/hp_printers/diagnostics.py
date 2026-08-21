"""Diagnostics support for the HP Printers integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .api import as_diagnostics
from .coordinator import HPPrinterConfigEntry

TO_REDACT = {CONF_HOST, "serial_number", "uuid", "user_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HPPrinterConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "product_info": async_redact_data(
            as_diagnostics(coordinator.product_info), TO_REDACT
        ),
        "data": async_redact_data(as_diagnostics(coordinator.data), TO_REDACT),
    }
