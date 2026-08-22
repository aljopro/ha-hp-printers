"""Tests for the LEDM parser and diagnostic conversion helpers."""

from datetime import datetime
from typing import Any

from defusedxml import ElementTree as DefusedET

from custom_components.hp_printers.api import (
    LEDMClient,
    _percent,
    _sentinel,
    _strip_namespaces,
    as_diagnostics,
)


def _xml(value: str) -> Any:
    """Parse a test XML document using the same namespace normalization as the client."""
    return _strip_namespaces(DefusedET.fromstring(value))


def test_percent_discards_unknown_and_out_of_range_values() -> None:
    """Unknown and out-of-range percentages are omitted."""
    assert _percent(None) is None
    assert _percent(-1) is None
    assert _percent(101) is None
    assert _percent(42) == 42


def test_sentinel_discards_hp_unknown_wear_value() -> None:
    """HP's 127 wear-counter sentinel is omitted."""
    assert _sentinel(None) is None
    assert _sentinel(127) is None
    assert _sentinel(80) == 80


def test_parse_subunit_scopes_repeated_counter_names() -> None:
    """Counters are read from the requested subunit only."""
    client = LEDMClient.__new__(LEDMClient)
    usage = _xml(
        """
        <ProductUsageDyn>
          <PrinterSubunit>
            <TotalImpressions>100</TotalImpressions>
            <DuplexSheets>20</DuplexSheets>
          </PrinterSubunit>
          <ScannerEngineSubunit>
            <TotalImpressions>30</TotalImpressions>
            <DuplexSheets>4</DuplexSheets>
          </ScannerEngineSubunit>
        </ProductUsageDyn>
        """
    )

    printer = client._parse_subunit(usage, "PrinterSubunit")  # noqa: SLF001
    scanner = client._parse_subunit(usage, "ScannerEngineSubunit")  # noqa: SLF001

    assert printer.total_impressions == 100
    assert printer.duplex_sheets == 20
    assert scanner.total_impressions == 30
    assert scanner.duplex_sheets == 4


def test_parse_consumables_keeps_installed_data_separate_from_previous() -> None:
    """Installed and removed cartridge fields do not overwrite each other."""
    client = LEDMClient.__new__(LEDMClient)
    config = _xml(
        """
        <ConsumableConfigDyn>
          <ConsumableInfo>
            <ConsumableLabelCode>K</ConsumableLabelCode>
            <SerialNumber>installed-serial</SerialNumber>
            <ConsumableTypeEnum>toner</ConsumableTypeEnum>
            <Installation><Date>2025-01-02</Date></Installation>
            <PreviousCartridgeData>
              <SerialNumber>removed-serial</SerialNumber>
              <DrumLife>80</DrumLife>
            </PreviousCartridgeData>
          </ConsumableInfo>
        </ConsumableConfigDyn>
        """
    )
    usage = _xml(
        """
        <ProductUsageDyn>
          <ConsumableSubunit>
            <Consumable>
              <MarkerColor>Black</MarkerColor>
              <EstimatedPagesRemaining>900</EstimatedPagesRemaining>
            </Consumable>
          </ConsumableSubunit>
        </ProductUsageDyn>
        """
    )

    consumable = client._parse_consumables(config, usage)["K"]  # noqa: SLF001

    assert consumable.serial_number == "installed-serial"
    assert consumable.pages_remaining == 900
    assert consumable.installed_at == datetime(2025, 1, 2)
    assert consumable.previous_serial_number == "removed-serial"
    assert consumable.previous_drum_life == 80


def test_as_diagnostics_converts_datetimes_and_nested_dataclasses() -> None:
    """Diagnostic conversion produces JSON-compatible datetime strings."""
    value = as_diagnostics({"when": datetime(2025, 1, 2, 3, 4, 5)})

    assert value == {"when": "2025-01-02T03:04:05"}
