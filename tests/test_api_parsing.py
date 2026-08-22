"""End-to-end tests of the LEDM parsing layer against realistic XML.

Where ``test_api.py`` exercises the parser building blocks (sentinels,
percentages, namespace normalization), this module drives the parser
end-to-end with XML shaped the way real printers actually emit it --
including all the small quirks that were discovered while looking at a
live device: nested status messages, the ``1976-01-01`` placeholder
used by devices without a real-time clock, and the ``PreviousCartridgeData``
subtree that shares field names with the installed cartridge.
"""

from datetime import datetime
import ssl
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiohttp import ClientError
from defusedxml import ElementTree as DefusedET
import pytest

from custom_components.hp_printers.api import (
    HPPrinterConnectionError,
    HPPrinterParseError,
    LEDMClient,
    _strip_namespaces,
)
from custom_components.hp_printers.const import (
    ENDPOINT_CONSUMABLE_CONFIG,
    ENDPOINT_PRODUCT_CONFIG,
    ENDPOINT_PRODUCT_LOGS,
    ENDPOINT_PRODUCT_STATUS,
    ENDPOINT_PRODUCT_USAGE,
)


def _xml(value: str) -> Any:
    """Parse XML and strip namespaces, mirroring the live parser."""
    return _strip_namespaces(DefusedET.fromstring(value))


def _new_client() -> LEDMClient:
    """Construct an ``LEDMClient`` without calling its constructor."""
    client = LEDMClient.__new__(LEDMClient)
    client._session = MagicMock()  # noqa: SLF001
    client._host = "printer.local"  # noqa: SLF001
    client._port = 80  # noqa: SLF001
    client._ssl = False  # noqa: SLF001
    client._ssl_context = False  # noqa: SLF001
    return client


async def test_async_get_data_parses_full_response() -> None:
    """A realistic set of responses produces a populated ``PrinterData``."""
    client = _new_client()

    status = _xml(
        """
        <ProductStatusDyn>
          <Status>
            <StatusCategory>Processing</StatusCategory>
            <LocString>Printing page 3.</LocString>
          </Status>
        </ProductStatusDyn>
        """
    )
    usage = _xml(
        """
        <ProductUsageDyn>
          <PrinterSubunit>
            <TotalImpressions>200</TotalImpressions>
            <JamEvents>1</JamEvents>
          </PrinterSubunit>
          <ScannerEngineSubunit>
            <TotalImpressions>10</TotalImpressions>
          </ScannerEngineSubunit>
          <ScanApplicationSubunit>
            <FlatbedImages>7</FlatbedImages>
          </ScanApplicationSubunit>
          <CopyApplicationSubunit>
            <TotalImpressions>5</TotalImpressions>
          </CopyApplicationSubunit>
          <ConsumableSubunit>
            <Consumable>
              <MarkerColor>Black</MarkerColor>
              <EstimatedPagesRemaining>900</EstimatedPagesRemaining>
              <TotalImpressions>100</TotalImpressions>
            </Consumable>
          </ConsumableSubunit>
          <OriginalHPColorImpressions>50</OriginalHPColorImpressions>
          <OriginalHPMonochromeImpressions>100</OriginalHPMonochromeImpressions>
        </ProductUsageDyn>
        """
    )
    consumable = _xml(
        """
        <ConsumableConfigDyn>
          <ConsumableInfo>
            <ConsumableLabelCode>K</ConsumableLabelCode>
            <ConsumableTypeEnum>toner</ConsumableTypeEnum>
            <ConsumablePercentageLevelRemaining>75</ConsumablePercentageLevelRemaining>
            <ConsumableLowThreshold>10</ConsumableLowThreshold>
          </ConsumableInfo>
          <GenuineHPSuppliesOnly>enabled</GenuineHPSuppliesOnly>
        </ConsumableConfigDyn>
        """
    )
    logs = _xml(
        """
        <ProductLogsDyn>
          <EventLog>
            <Event>
              <SequenceNumber>1</SequenceNumber>
              <EventCode>13.10.00</EventCode>
              <TotalImpressions>100</TotalImpressions>
            </Event>
            <Event>
              <SequenceNumber>2</SequenceNumber>
              <EventCode>49.99.00</EventCode>
              <TotalImpressions>123</TotalImpressions>
            </Event>
          </EventLog>
          <JobList>
            <JobEntry>
              <DriverJobApplicationID>AcmePrint</DriverJobApplicationID>
              <TotalImpressions>5</TotalImpressions>
            </JobEntry>
          </JobList>
        </ProductLogsDyn>
        """
    )

    client._fetch = AsyncMock(  # noqa: SLF001
        side_effect=[status, usage, consumable, logs]
    )

    data = await client.async_get_data()

    assert data.status == "processing"
    assert data.status_message == "Printing page 3."
    assert data.printer.total_impressions == 200
    assert data.printer.jam_events == 1
    assert data.scanner.scan_images is None  # field absent in the response
    assert data.scan.flatbed_images == 7
    assert data.copy.total_impressions == 5
    assert data.genuine_color_impressions == 50
    assert data.genuine_mono_impressions == 100
    assert data.genuine_supplies_only is True
    assert data.last_event is not None
    assert data.last_event.code == "49.99.00"
    assert data.last_job is not None
    assert data.last_job.application_id == "AcmePrint"

    cartridge = data.consumables["K"]
    assert cartridge.level_percent == 75.0
    assert cartridge.pages_remaining == 900
    assert cartridge.low_threshold_percent == 10.0


async def test_async_get_data_propagates_connection_error() -> None:
    """A connection error becomes ``HPPrinterConnectionError``."""
    client = _new_client()
    client._fetch = AsyncMock(side_effect=HPPrinterConnectionError("timeout"))  # noqa: SLF001

    with pytest.raises(HPPrinterConnectionError):
        await client.async_get_data()


async def test_async_get_product_info_extracts_nested_values() -> None:
    """Nested ``ProductInformation`` values are extracted correctly."""
    client = _new_client()
    client._fetch = AsyncMock(  # noqa: SLF001
        return_value=_xml(
            """
            <ProductConfigDyn>
              <ProductInformation>
                <MakeAndModel>HP Color LaserJet MFP M182nw</MakeAndModel>
                <SerialNumber>SN-1</SerialNumber>
                <Version><Date>2025-04-01T00:00:00</Date></Version>
                <Manufacturer>
                  <Name>HP</Name>
                  <Date>2021-06-15T00:00:00</Date>
                </Manufacturer>
                <PasswordStatus>set</PasswordStatus>
              </ProductInformation>
              <FriendlyName>Office printer</FriendlyName>
              <PowerSaveTimeout>300</PowerSaveTimeout>
            </ProductConfigDyn>
            """
        )
    )

    info = await client.async_get_product_info()

    assert info.make_and_model == "HP Color LaserJet MFP M182nw"
    assert info.serial_number == "SN-1"
    assert info.firmware_date == "2025-04-01T00:00:00"
    # The build date lives beside the firmware Version date; each must be
    # resolved within its own parent rather than by document order.
    assert info.manufactured_at == datetime(2021, 6, 15)
    assert info.password_set is True
    assert info.friendly_name == "Office printer"
    assert info.power_save_timeout == "300"


async def test_async_get_product_info_raises_when_product_information_missing() -> None:
    """A document with no ``ProductInformation`` element raises ``HPPrinterParseError``."""
    client = _new_client()
    client._fetch = AsyncMock(  # noqa: SLF001
        return_value=_xml("<ProductConfigDyn></ProductConfigDyn>")
    )

    with pytest.raises(HPPrinterParseError):
        await client.async_get_product_info()


async def test_async_get_product_info_raises_without_serial() -> None:
    """``async_validate`` rejects a device that reports no serial number."""
    client = _new_client()
    client._fetch = AsyncMock(  # noqa: SLF001
        return_value=_xml(
            """
            <ProductConfigDyn>
              <ProductInformation>
                <MakeAndModel>HP Color LaserJet MFP M182nw</MakeAndModel>
              </ProductInformation>
            </ProductConfigDyn>
            """
        )
    )

    with pytest.raises(HPPrinterParseError):
        await client.async_validate()


async def test_consumable_full_parsing_with_previous_cartridge() -> None:
    """A realistic consumable XML, including PreviousCartridgeData, parses cleanly."""
    client = _new_client()

    config = _xml(
        """
        <ConsumableConfigDyn>
          <ConsumableInfo>
            <ConsumableLabelCode>K</ConsumableLabelCode>
            <SerialNumber>installed</SerialNumber>
            <ConsumableSelectibilityNumber>CF500A</ConsumableSelectibilityNumber>
            <Capacity><MaxCapacity>2200</MaxCapacity></Capacity>
            <Installation><Date>2025-01-02T00:00:00</Date></Installation>
            <Manufacturer><Date>2024-11-01T00:00:00</Date></Manufacturer>
            <Warranty><ExpirationDate>2026-01-02T00:00:00</ExpirationDate></Warranty>
            <ConsumableTypeEnum>toner</ConsumableTypeEnum>
            <ConsumablePercentageLevelRemaining>75</ConsumablePercentageLevelRemaining>
            <ConsumableLowThreshold>10</ConsumableLowThreshold>
            <ConsumableLifeState>
              <Brand>genuinehp</Brand>
              <ConsumableState>ok</ConsumableState>
            </ConsumableLifeState>
            <PreviousCartridgeData>
              <SerialNumber>previous</SerialNumber>
              <DrumLife>80</DrumLife>
              <DeveloperLife>60</DeveloperLife>
              <ProductNumber>CF500A</ProductNumber>
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
              <TotalImpressions>500</TotalImpressions>
              <RefilledCount>
                <CounterfeitRefilledCount>0</CounterfeitRefilledCount>
                <GenuineRefilledCount>0</GenuineRefilledCount>
              </RefilledCount>
              <ConsumableRawPercentageLevelRemaining>74.6</ConsumableRawPercentageLevelRemaining>
            </Consumable>
          </ConsumableSubunit>
        </ProductUsageDyn>
        """
    )

    consumables = client._parse_consumables(config, usage)  # noqa: SLF001
    cartridge = consumables["K"]

    # Installed cartridge fields
    assert cartridge.serial_number == "installed"
    assert cartridge.part_number == "CF500A"
    assert cartridge.max_capacity == 2200
    assert cartridge.consumable_type == "toner"
    assert cartridge.level_percent == 75.0
    assert cartridge.raw_level_percent == 74.6
    assert cartridge.low_threshold_percent == 10.0
    assert cartridge.brand == "genuinehp"
    assert cartridge.state == "ok"
    assert cartridge.is_genuine is True
    assert cartridge.counterfeit_refills == 0
    assert cartridge.genuine_refills == 0

    # Previous cartridge fields
    assert cartridge.previous_serial_number == "previous"
    assert cartridge.previous_drum_life == 80
    assert cartridge.previous_developer_life == 60
    assert cartridge.previous_part_number == "CF500A"


async def test_consumable_date_without_clock_discarded() -> None:
    """Devices without a real-time clock report ``1976-01-01``; the parser discards it."""
    client = _new_client()

    config = _xml(
        """
        <ConsumableConfigDyn>
          <ConsumableInfo>
            <ConsumableLabelCode>K</ConsumableLabelCode>
            <Installation><Date>1976-01-01T00:00:00</Date></Installation>
            <Manufacturer><Date>1976-01-01</Date></Manufacturer>
          </ConsumableInfo>
        </ConsumableConfigDyn>
        """
    )
    usage = _xml("<ProductUsageDyn></ProductUsageDyn>")

    cartridge = client._parse_consumables(config, usage)["K"]  # noqa: SLF001

    assert cartridge.installed_at is None
    assert cartridge.manufactured_at is None


async def test_parse_logs_extracts_events_jobs_and_assert_text() -> None:
    """``_parse_logs`` builds the three lists with the expected fields."""
    client = _new_client()
    logs = _xml(
        """
        <ProductLogsDyn>
          <EventLog>
            <Event>
              <SequenceNumber>1</SequenceNumber>
              <EventCode>13.10.00</EventCode>
              <TotalImpressions>100</TotalImpressions>
            </Event>
            <Event>
              <SequenceNumber>2</SequenceNumber>
              <EventCode>49.99.00</EventCode>
              <TotalImpressions>123</TotalImpressions>
            </Event>
          </EventLog>
          <JobList>
            <JobEntry>
              <DriverJobApplicationID>AcmePrint</DriverJobApplicationID>
              <DriverJobUserID>jane</DriverJobUserID>
              <DriverJobName>Quarterly report</DriverJobName>
              <TotalImpressions>10</TotalImpressions>
            </JobEntry>
          </JobList>
          <ErrorLog>fault signature</ErrorLog>
        </ProductLogsDyn>
        """
    )

    events, jobs, assert_text = client._parse_logs(logs)  # noqa: SLF001

    # Events come back sorted by sequence number, descending.
    assert [event.code for event in events] == ["49.99.00", "13.10.00"]
    assert jobs[0].application_id == "AcmePrint"
    assert jobs[0].user_id == "jane"
    assert jobs[0].name == "Quarterly report"
    assert assert_text == "fault signature"


async def test_parse_logs_handles_missing_containers() -> None:
    """A document without ``EventLog`` or ``JobList`` returns empty lists."""
    client = _new_client()
    logs = _xml("<ProductLogsDyn></ProductLogsDyn>")

    events, jobs, assert_text = client._parse_logs(logs)  # noqa: SLF001

    assert events == []
    assert jobs == []
    assert assert_text is None


def test_base_url_uses_scheme_and_port() -> None:
    """The base URL reflects the configured scheme and port."""
    http = LEDMClient(MagicMock(), "printer.local", 80, False, False)
    https_default = LEDMClient(MagicMock(), "printer.local", 443, True, False)
    https_custom = LEDMClient(MagicMock(), "printer.local", 8443, True, False)

    assert http.base_url == "http://printer.local:80"
    assert https_default.base_url == "https://printer.local:443"
    assert https_custom.base_url == "https://printer.local:8443"


def test_client_carries_passed_ssl_context() -> None:
    """The constructor stores the SSL context it was given."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client = LEDMClient(MagicMock(), "printer.local", 443, True, context)

    assert client._ssl_context is context  # noqa: SLF001


async def test_fetch_surfaces_client_errors() -> None:
    """Aiohttp errors become ``HPPrinterConnectionError``."""
    client = _new_client()
    client._session.get.side_effect = ClientError("boom")  # noqa: SLF001

    with pytest.raises(HPPrinterConnectionError):
        await client._fetch(ENDPOINT_PRODUCT_CONFIG)  # noqa: SLF001


async def test_fetch_surfaces_timeouts() -> None:
    """Asyncio timeouts become ``HPPrinterConnectionError``."""
    client = _new_client()
    client._session.get.side_effect = TimeoutError()  # noqa: SLF001

    with pytest.raises(HPPrinterConnectionError):
        await client._fetch(ENDPOINT_PRODUCT_CONFIG)  # noqa: SLF001


async def test_fetch_surfaces_invalid_xml() -> None:
    """A non-XML response becomes ``HPPrinterParseError``."""
    response = MagicMock()
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    response.raise_for_status = MagicMock()
    response.text = AsyncMock(return_value="not-xml")

    client = _new_client()
    client._session.get.return_value = response  # noqa: SLF001

    with pytest.raises(HPPrinterParseError):
        await client._fetch(ENDPOINT_PRODUCT_CONFIG)  # noqa: SLF001


def test_endpoints_are_distinct() -> None:
    """Every endpoint URL is unique -- a regression here would silently re-fetch the same data."""
    endpoints = {
        ENDPOINT_PRODUCT_CONFIG,
        ENDPOINT_PRODUCT_STATUS,
        ENDPOINT_PRODUCT_USAGE,
        ENDPOINT_CONSUMABLE_CONFIG,
        ENDPOINT_PRODUCT_LOGS,
    }
    assert len(endpoints) == 5
