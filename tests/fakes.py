"""Shared test doubles for the HP Printers integration.

The integration uses ``homeassistant.helpers.update_coordinator.CoordinatorEntity``
as the base class for its entities. That class requires a coordinator with
``config_entry``, ``client``, ``product_info``, and ``data`` attributes, but
it never calls back into a real Home Assistant instance — entity construction
and ``value_fn`` evaluation are pure Python. These helpers produce stand-ins
that satisfy that surface so tests can drive the entity layer without a live
``HomeAssistant``.
"""

from datetime import UTC, datetime
from typing import Any

from custom_components.hp_printers.models import (
    Consumable,
    EventLogEntry,
    JobEntry,
    PrinterData,
    ProductInfo,
    SubunitUsage,
)


class FakeClient:
    """Stub of :class:`LEDMClient` that exposes only ``base_url``."""

    base_url = "http://printer.local"


class FakeConfigEntry:
    """Stub of a ``ConfigEntry`` with a stable id and title."""

    entry_id = "test-entry"
    title = "Office printer"


class FakeCoordinator:
    """Coordinator double; ``data`` is mutable so tests can drive refreshes."""

    def __init__(
        self,
        product_info: ProductInfo,
        data: PrinterData,
    ) -> None:
        """Initialize."""
        self.product_info = product_info
        self.data = data
        self.client = FakeClient()
        self.config_entry = FakeConfigEntry()


def make_product_info(**overrides: Any) -> ProductInfo:
    """Build a populated ``ProductInfo`` for tests."""
    fields: dict[str, Any] = {
        "make_and_model": "HP Color LaserJet MFP M182nw",
        "make_and_model_family": "HP Color LaserJet MFP",
        "serial_number": "SN-TEST-1234",
        "product_number": "7KW56A",
        "uuid": "00000000-0000-0000-0000-000000000000",
        "service_id": None,
        "firmware_date": "2025-04-01",
        "manufactured_at": datetime(2021, 6, 15, tzinfo=UTC),
        "language_pack_version": "1",
        "password_set": False,
        "duplex_unit": "installed",
        "friendly_name": "Office printer",
        "power_save": "enabled",
        "power_save_timeout": "300",
        "shutdown_delay": "0",
    }
    fields.update(overrides)
    return ProductInfo(**fields)


def make_printer_data(**overrides: Any) -> PrinterData:
    """Build a populated ``PrinterData`` for tests."""
    fields: dict[str, Any] = {
        "status": "ready",
        "status_message": "Ready to print.",
        "consumables": {},
        "printer": SubunitUsage(
            total_impressions=1234,
            monochrome_impressions=900,
            color_impressions=334,
            simplex_sheets=1000,
            duplex_sheets=234,
            jam_events=2,
            mispick_events=5,
        ),
        "scanner": SubunitUsage(
            scan_images=10,
            adf_images=7,
            flatbed_images=3,
            duplex_sheets=2,
            jam_events=0,
            mispick_events=0,
        ),
        "copy": SubunitUsage(
            total_impressions=20,
            monochrome_impressions=15,
            color_impressions=5,
            adf_images=12,
            flatbed_images=8,
        ),
        "events": [],
        "jobs": [],
        "genuine_color_impressions": 200,
        "genuine_mono_impressions": 800,
        "assert_text": None,
        "genuine_supplies_only": False,
    }
    fields.update(overrides)
    return PrinterData(**fields)


def make_consumable(**overrides: Any) -> Consumable:
    """Build a populated ``Consumable`` for tests."""
    fields: dict[str, Any] = {
        "label_code": "K",
        "color_name": "black",
        "consumable_type": "toner",
        "brand": "genuinehp",
        "state": "ok",
        "level_percent": 75.0,
        "pages_remaining": 1500,
        "total_impressions": 500,
        "station": 1,
        "serial_number": "CTR-1234",
        "part_number": "CF500A",
        "max_capacity": 2200,
        "installed_at": datetime(2025, 1, 2, tzinfo=UTC),
        "manufactured_at": datetime(2024, 11, 1, tzinfo=UTC),
        "warranty_expires_at": datetime(2026, 1, 2, tzinfo=UTC),
        "counterfeit_refills": 0,
        "genuine_refills": 0,
        "family_name": "CF500A-family",
        "raw_level_percent": 74.6,
        "low_threshold_percent": 10.0,
        "measured_state": "ok",
        "previous_drum_life": 80,
        "previous_developer_life": 60,
        "previous_engine_toner_remaining": 5,
        "previous_part_number": "CF500A",
        "previous_serial_number": "CTR-PREV-9999",
    }
    fields.update(overrides)
    return Consumable(**fields)


def make_event(**overrides: Any) -> EventLogEntry:
    """Build an :class:`EventLogEntry` for tests."""
    fields: dict[str, Any] = {
        "sequence": 42,
        "code": "13.20.00",
        "impressions": 1234,
    }
    fields.update(overrides)
    return EventLogEntry(**fields)


def make_job(**overrides: Any) -> JobEntry:
    """Build a :class:`JobEntry` for tests."""
    fields: dict[str, Any] = {
        "application_id": "AcmePrint",
        "user_id": "jane",
        "name": "Quarterly report",
        "monochrome_impressions": 10,
        "color_impressions": 0,
        "total_impressions": 10,
    }
    fields.update(overrides)
    return JobEntry(**fields)
