"""Coordinator for the HP Printers integration."""

from datetime import timedelta
import logging
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HPPrinterError, LEDMClient
from .const import DOMAIN
from .models import PrinterData, ProductInfo

_LOGGER = logging.getLogger(__name__)

type HPPrinterConfigEntry = ConfigEntry[HPPrinterDataUpdateCoordinator]

# ProductConfigDyn is effectively static -- it only changes when firmware or a
# language pack is installed -- so it is refreshed on a slow cadence rather
# than on every poll.
STATIC_REFRESH_INTERVAL = timedelta(hours=6).total_seconds()


class HPPrinterDataUpdateCoordinator(DataUpdateCoordinator[PrinterData]):
    """Fetch data from a printer's LEDM endpoints."""

    config_entry: HPPrinterConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: HPPrinterConfigEntry,
        client: LEDMClient,
        product_info: ProductInfo,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.product_info = product_info
        self.device_name = config_entry.title
        self._static_fetched_at = monotonic()

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> PrinterData:
        """Fetch the current printer state."""
        try:
            data = await self.client.async_get_data()
            if monotonic() - self._static_fetched_at > STATIC_REFRESH_INTERVAL:
                self.product_info = await self.client.async_get_product_info()
                self._static_fetched_at = monotonic()
        except HPPrinterError as error:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_error",
                translation_placeholders={
                    "device": self.device_name,
                    "error": repr(error),
                },
            ) from error
        return data
