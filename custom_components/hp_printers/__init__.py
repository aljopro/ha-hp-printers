"""The HP Printers integration."""

from datetime import timedelta
import logging

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HPPrinterError, LEDMClient
from .const import (
    CONF_SCAN_INTERVAL_SECONDS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSL,
    DOMAIN,
)
from .coordinator import HPPrinterConfigEntry, HPPrinterDataUpdateCoordinator
from .helpers import printer_ssl_context

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: HPPrinterConfigEntry) -> bool:
    """Set up HP Printers from a config entry."""
    client = LEDMClient(
        async_get_clientsession(hass, verify_ssl=False),
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        entry.data.get(CONF_SSL, DEFAULT_SSL),
        printer_ssl_context(),
    )

    try:
        product_info = await client.async_validate()
    except HPPrinterError as error:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"device": entry.title, "error": repr(error)},
        ) from error

    # Guard against the entry being pointed at a different printer, which is
    # easy to do on DHCP when an address is reused.
    if entry.unique_id and product_info.serial_number != entry.unique_id:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="serial_mismatch",
            translation_placeholders={"device": entry.title},
        )

    interval = timedelta(
        seconds=entry.options.get(
            CONF_SCAN_INTERVAL_SECONDS, int(DEFAULT_SCAN_INTERVAL.total_seconds())
        )
    )

    coordinator = HPPrinterDataUpdateCoordinator(
        hass, entry, client, product_info, interval
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HPPrinterConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
