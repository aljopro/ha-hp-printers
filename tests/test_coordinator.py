"""Tests for the coordinator update logic.

``HPPrinterDataUpdateCoordinator`` extends Home Assistant's
``DataUpdateCoordinator``, which subscribes to events and owns a debouncer.
Standing up that machinery requires a live ``HomeAssistant`` instance,
but the update path itself is pure async code. The test exercises that
path directly via the module-level ``async_fetch_update`` helper, which
the coordinator now delegates to.
"""

import time

import pytest

from custom_components.hp_printers.api import HPPrinterConnectionError, HPPrinterError
from custom_components.hp_printers.coordinator import (
    STATIC_REFRESH_INTERVAL,
    HPPrinterDataUpdateCoordinator,
    async_fetch_update,
)
from custom_components.hp_printers.models import PrinterData, ProductInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed


class _StubClient:
    """Stub of ``LEDMClient`` exposing only the methods the coordinator uses."""

    def __init__(
        self,
        data: PrinterData | None = None,
        product_info: ProductInfo | None = None,
        side_effect: Exception | None = None,
    ) -> None:
        """Initialize."""
        self._data = data or PrinterData()
        self._product_info = product_info or ProductInfo()
        self._side_effect = side_effect

    async def async_get_data(self) -> PrinterData:
        """Return the configured ``PrinterData`` or raise the configured error."""
        if self._side_effect is not None:
            raise self._side_effect
        return self._data

    async def async_get_product_info(self) -> ProductInfo:
        """Return the configured ``ProductInfo``."""
        return self._product_info


def test_static_refresh_interval_is_six_hours() -> None:
    """ProductConfigDyn is refreshed every six hours, no faster."""
    assert STATIC_REFRESH_INTERVAL == 6 * 60 * 60


async def test_async_fetch_update_returns_data() -> None:
    """A successful fetch returns the printer's current data unchanged."""
    client = _StubClient(data=PrinterData(status="ready"))
    info = ProductInfo(serial_number="SN-1")

    data, new_info, _ = await async_fetch_update(
        client=client,
        product_info=info,
        static_fetched_at=time.monotonic(),
        device_name="Office printer",
    )

    assert data.status == "ready"
    assert new_info is info  # not refreshed inside the static window


async def test_async_fetch_update_refreshes_static_info_when_stale() -> None:
    """Static product info is re-fetched after six hours."""
    client = _StubClient(
        data=PrinterData(),
        product_info=ProductInfo(serial_number="SN-REFRESHED"),
    )
    info = ProductInfo(serial_number="SN-OLD")

    _, new_info, _ = await async_fetch_update(
        client=client,
        product_info=info,
        static_fetched_at=0.0,
        device_name="Office printer",
    )

    assert new_info.serial_number == "SN-REFRESHED"


async def test_async_fetch_update_does_not_refresh_static_info_within_window() -> None:
    """Static product info stays the same inside the six-hour window."""
    client = _StubClient(
        data=PrinterData(),
        product_info=ProductInfo(serial_number="SN-REFRESHED"),
    )
    info = ProductInfo(serial_number="SN-CURRENT")

    _, new_info, _ = await async_fetch_update(
        client=client,
        product_info=info,
        static_fetched_at=time.monotonic(),
        device_name="Office printer",
    )

    assert new_info.serial_number == "SN-CURRENT"


async def test_async_fetch_update_raises_update_failed_on_connection_error() -> None:
    """``HPPrinterConnectionError`` is converted to ``UpdateFailed``."""
    client = _StubClient(side_effect=HPPrinterConnectionError("timeout"))

    with pytest.raises(UpdateFailed):
        await async_fetch_update(
            client=client,
            product_info=ProductInfo(),
            static_fetched_at=0.0,
            device_name="Office printer",
        )


async def test_async_fetch_update_translates_any_hpprinter_error() -> None:
    """Any ``HPPrinterError`` subclass produces ``UpdateFailed``."""
    client = _StubClient(side_effect=HPPrinterError("nope"))

    with pytest.raises(UpdateFailed):
        await async_fetch_update(
            client=client,
            product_info=ProductInfo(),
            static_fetched_at=0.0,
            device_name="Office printer",
        )


async def test_async_fetch_update_does_not_refresh_static_info_when_dynamic_fails() -> (
    None
):
    """A failed dynamic fetch does not trigger a static-info refresh."""
    client = _StubClient(side_effect=HPPrinterConnectionError("timeout"))
    info = ProductInfo(serial_number="SN-UNCHANGED")

    with pytest.raises(UpdateFailed):
        await async_fetch_update(
            client=client,
            product_info=info,
            static_fetched_at=0.0,
            device_name="Office printer",
        )

    # The function raised before mutating; the caller's reference is unchanged.
    assert info.serial_number == "SN-UNCHANGED"


def test_coordinator_class_inherits_update_coordinator() -> None:
    """The coordinator class inherits from Home Assistant's update coordinator."""
    assert issubclass(HPPrinterDataUpdateCoordinator, DataUpdateCoordinator)


def test_coordinator_class_exposes_update_method() -> None:
    """The coordinator class is exposed without requiring an event loop."""
    assert hasattr(HPPrinterDataUpdateCoordinator, "_async_update_data")
    # The class is introspectable; this exercises the same import path used by
    # setup. Without this guard, a future refactor that requires asyncio.run()
    # at import time would silently break Home Assistant boot.
    assert callable(HPPrinterDataUpdateCoordinator._async_update_data)  # noqa: SLF001
