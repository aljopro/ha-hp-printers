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

# Consecutive-failure backoff. A printer that is asleep, powered off, or has
# dropped off the network refuses every connection until it comes back, and
# retrying at the normal cadence is both pointless and -- on models whose
# firmware has faults on the sleep/wake path -- actively unhelpful. The
# interval doubles per consecutive failure and is restored on the first
# success.
MAX_BACKOFF_INTERVAL = timedelta(minutes=10)
MAX_BACKOFF_DOUBLINGS = 6


def backoff_interval(base: timedelta, failures: int) -> timedelta:
    """Return the polling interval to use after ``failures`` failures in a row.

    ``failures`` of 0 means the last poll succeeded, which restores the
    configured interval. The result never exceeds ``MAX_BACKOFF_INTERVAL``,
    and never drops below the configured interval -- a user who asks for
    slow polling does not get faster polling because the printer is down.
    """
    if failures <= 0:
        return base
    doublings = min(failures, MAX_BACKOFF_DOUBLINGS)
    return min(base * 2**doublings, max(MAX_BACKOFF_INTERVAL, base))


async def async_fetch_update(
    client: LEDMClient,
    product_info: ProductInfo,
    static_fetched_at: float,
    device_name: str,
) -> tuple[PrinterData, ProductInfo, float]:
    """Fetch dynamic data and refresh static product info when stale.

    Raises ``UpdateFailed`` if the printer cannot be reached. The function
    is factored out of the coordinator class so it can be unit-tested
    without standing up a Home Assistant instance.
    """
    try:
        data = await client.async_get_data()
        if monotonic() - static_fetched_at > STATIC_REFRESH_INTERVAL:
            product_info = await client.async_get_product_info()
            static_fetched_at = monotonic()
    except HPPrinterError as error:
        raise UpdateFailed(
            translation_domain=DOMAIN,
            translation_key="update_error",
            translation_placeholders={
                "device": device_name,
                "error": repr(error),
            },
        ) from error
    return data, product_info, static_fetched_at


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
        self._base_interval = update_interval
        self._consecutive_failures = 0

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> PrinterData:
        """Fetch the current printer state, backing off while it is failing."""
        try:
            (
                data,
                self.product_info,
                self._static_fetched_at,
            ) = await async_fetch_update(
                self.client,
                self.product_info,
                self._static_fetched_at,
                self.device_name,
            )
        except UpdateFailed:
            self._consecutive_failures += 1
            self._apply_backoff()
            raise

        if self._consecutive_failures:
            _LOGGER.debug(
                "%s answered again after %s failed attempts; restoring the %s"
                " second interval",
                self.device_name,
                self._consecutive_failures,
                self._base_interval.total_seconds(),
            )
            self._consecutive_failures = 0
            self._apply_backoff()
        return data

    def _apply_backoff(self) -> None:
        """Widen or restore the polling interval for the current failure run."""
        interval = backoff_interval(self._base_interval, self._consecutive_failures)
        if interval != self.update_interval:
            _LOGGER.debug(
                "%s: polling interval is now %s seconds (%s consecutive failures)",
                self.device_name,
                interval.total_seconds(),
                self._consecutive_failures,
            )
            self.update_interval = interval
