"""Tests for ``Consumable`` and ``PrinterData`` properties."""

import pytest

from custom_components.hp_printers.models import (
    Consumable,
    EventLogEntry,
    JobEntry,
    NetworkHealth,
    PrinterData,
)


def test_consumable_is_genuine_true_for_hp_brand() -> None:
    """An HP-branded cartridge reports ``is_genuine=True``."""
    cartridge = Consumable(label_code="K", brand="genuinehp")

    assert cartridge.is_genuine is True


def test_consumable_is_genuine_false_for_clone() -> None:
    """A clone-branded cartridge reports ``is_genuine=False``."""
    cartridge = Consumable(label_code="K", brand="clone")

    assert cartridge.is_genuine is False


def test_consumable_is_genuine_false_for_unknown() -> None:
    """``unknown`` is also treated as not genuine."""
    cartridge = Consumable(label_code="K", brand="unknown")

    assert cartridge.is_genuine is False


def test_consumable_is_genuine_none_when_brand_absent() -> None:
    """Without a brand the property is ``None`` -- not a boolean guess."""
    cartridge = Consumable(label_code="K")

    assert cartridge.is_genuine is None


def test_consumable_is_genuine_strips_whitespace_and_case() -> None:
    """The brand comparison is whitespace-insensitive and case-insensitive."""
    cartridge = Consumable(label_code="K", brand="  GenuineHP ")

    assert cartridge.is_genuine is True


def test_printer_data_last_event_returns_highest_sequence() -> None:
    """``last_event`` is the entry with the highest sequence number."""
    data = PrinterData(
        events=[
            EventLogEntry(sequence=1, code="13.10.00", impressions=100),
            EventLogEntry(sequence=42, code="13.20.00", impressions=1234),
            EventLogEntry(sequence=10, code="49.99.00", impressions=200),
        ],
    )

    assert data.last_event is not None
    assert data.last_event.code == "13.20.00"


def test_printer_data_last_event_handles_unsorted_with_none_sequence() -> None:
    """An entry with ``sequence=None`` sorts below any numbered entry."""
    data = PrinterData(
        events=[
            EventLogEntry(sequence=None, code="00.00.01", impressions=0),
            EventLogEntry(sequence=5, code="13.20.00", impressions=1234),
        ],
    )

    assert data.last_event is not None
    assert data.last_event.code == "13.20.00"


def test_printer_data_last_event_none_when_no_events() -> None:
    """``last_event`` is ``None`` when the printer has no event log."""
    data = PrinterData()

    assert data.last_event is None


def test_printer_data_last_job_returns_first_entry() -> None:
    """``last_job`` is the most recent entry -- the list is already in reverse order."""
    data = PrinterData(
        jobs=[
            JobEntry(application_id="Newest", total_impressions=5),
            JobEntry(application_id="Older", total_impressions=10),
        ],
    )

    assert data.last_job is not None
    assert data.last_job.application_id == "Newest"


def test_printer_data_last_job_none_when_no_jobs() -> None:
    """``last_job`` is ``None`` when the printer has no job log."""
    data = PrinterData()

    assert data.last_job is None


@pytest.mark.parametrize(
    "brand",
    ["GENUINEHP", "genuinehp", "GenuineHP", "  genuinehp  "],
)
def test_consumable_is_genuine_recognizes_brand_variants(brand: str) -> None:
    """Whitespace, casing, and padding are normalized."""
    cartridge = Consumable(label_code="K", brand=brand)

    assert cartridge.is_genuine is True


def test_network_health_totals_only_what_the_device_reports() -> None:
    """Error counters add up, and stay unknown when nothing reports them."""
    health = NetworkHealth(
        bad_packets_received=2,
        framing_errors=1,
        transmit_collisions=None,
    )

    assert health.total_errors == 3
    assert health.error_counts["transmit_collisions"] is None
    # A device that reports no counters must not read as a healthy zero.
    assert NetworkHealth().total_errors is None
    # A device that reports them as zero must.
    assert NetworkHealth(bad_packets_received=0).total_errors == 0
