"""Tests for the diagnostics redaction pipeline.

The diagnostics file intentionally redacts host, serial, UUID, and user
identifiers before exposing LEDM data, so a bug here would silently leak
private information. These tests assert every documented field is or
isn't redacted.
"""

from datetime import UTC, datetime

import pytest

from custom_components.hp_printers.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
)
from custom_components.hp_printers.models import Consumable, JobEntry, PrinterData
from homeassistant.components.diagnostics import REDACTED
from homeassistant.const import CONF_HOST

from .fakes import make_printer_data, make_product_info


class _StubEntry:
    """Stand-in for a HA ``ConfigEntry`` with ``runtime_data``."""

    def __init__(self, runtime_data):
        """Initialize."""
        self.runtime_data = runtime_data

    data = {CONF_HOST: "192.0.2.42", "port": 80, "ssl": False}
    options = {"scan_interval_seconds": 60}


class _StubCoordinator:
    """Coordinator exposing ``product_info`` and ``data``."""

    def __init__(self, product_info, data):
        """Initialize."""
        self.product_info = product_info
        self.data = data


async def test_to_redact_includes_host_serial_uuid_user() -> None:
    """The redaction set covers every documented identifier."""
    assert CONF_HOST in TO_REDACT
    assert "serial_number" in TO_REDACT
    assert "uuid" in TO_REDACT
    assert "user_id" in TO_REDACT


async def test_diagnostics_redacts_host_in_entry() -> None:
    """The host stored on the config entry shows up as ``**`` in diagnostics."""
    product_info = make_product_info(serial_number="SN-SECRET-1234")
    data = make_printer_data()

    diagnostics = await async_get_config_entry_diagnostics(
        None,  # type: ignore[arg-type]
        _StubEntry(_StubCoordinator(product_info, data)),
    )

    assert diagnostics["entry"]["host"] == REDACTED
    # Other entry fields are passed through.
    assert diagnostics["entry"]["port"] == 80
    assert diagnostics["entry"]["ssl"] is False


async def test_diagnostics_redacts_serial_in_product_info() -> None:
    """Product-info serial number is redacted but model is not."""
    product_info = make_product_info(serial_number="SN-SECRET-1234")
    data = make_printer_data()

    diagnostics = await async_get_config_entry_diagnostics(
        None,  # type: ignore[arg-type]
        _StubEntry(_StubCoordinator(product_info, data)),
    )

    assert diagnostics["product_info"]["serial_number"] == REDACTED
    # Make and model are not identifiers; they are preserved so the
    # diagnostic file remains useful for triage.
    assert diagnostics["product_info"]["make_and_model"] == product_info.make_and_model


async def test_diagnostics_redacts_user_id_in_jobs() -> None:
    """Per-job user_id fields are redacted while other job fields remain."""
    product_info = make_product_info()
    data = PrinterData(
        status="ready",
        jobs=[
            JobEntry(
                application_id="AcmePrint",
                user_id="jane",
                name="Quarterly report",
                monochrome_impressions=10,
                color_impressions=0,
                total_impressions=10,
            ),
        ],
        events=[],
    )

    diagnostics = await async_get_config_entry_diagnostics(
        None,  # type: ignore[arg-type]
        _StubEntry(_StubCoordinator(product_info, data)),
    )

    job = diagnostics["data"]["jobs"][0]
    assert job["user_id"] == REDACTED
    # Other job fields are preserved.
    assert job["application_id"] == "AcmePrint"
    assert job["name"] == "Quarterly report"


async def test_diagnostics_datetimes_serialized_as_strings() -> None:
    """``as_diagnostics`` flattens datetimes to ISO strings (HA requires JSON)."""
    product_info = make_product_info(
        firmware_date="2025-04-01",
    )
    data = PrinterData(
        status="ready",
        consumables={
            "K": Consumable(
                label_code="K",
                installed_at=datetime(2025, 1, 2, tzinfo=UTC),
            ),
        },
    )

    diagnostics = await async_get_config_entry_diagnostics(
        None,  # type: ignore[arg-type]
        _StubEntry(_StubCoordinator(product_info, data)),
    )

    cartridge = diagnostics["data"]["consumables"]["K"]
    assert cartridge["installed_at"] == "2025-01-02T00:00:00+00:00"


@pytest.mark.parametrize(
    "serial_value",
    [None, ""],
)
async def test_diagnostics_handles_missing_or_empty_serial(serial_value) -> None:
    """An empty serial number still produces a valid diagnostic payload."""
    product_info = make_product_info(serial_number=serial_value)
    data = make_printer_data()

    diagnostics = await async_get_config_entry_diagnostics(
        None,  # type: ignore[arg-type]
        _StubEntry(_StubCoordinator(product_info, data)),
    )

    # ``async_redact_data`` replaces any matching field with ``**REDACTED**``
    # when the value is truthy; a None stays None and an empty string is
    # preserved (the helper skips empty strings).
    assert diagnostics["product_info"]["serial_number"] in (None, "", REDACTED)
