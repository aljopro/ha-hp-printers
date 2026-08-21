"""Client for HP's LEDM ("Low End Data Model") XML interface.

HP does not publish a specification for LEDM. The endpoint map used here was
derived by reading a live device: /DevMgmt/DiscoveryTree.xml enumerates the
available resources, and each resource is exposed as a paired
<Resource>Cap.xml (capabilities, types, access modes) and <Resource>Dyn.xml
(current values). Everything below targets the Dyn documents.
"""

import asyncio
from datetime import datetime
import logging
import ssl
from typing import Any
from xml.etree.ElementTree import Element

from aiohttp import ClientError, ClientSession, ClientTimeout
from defusedxml import ElementTree as DefusedET

from .const import (
    COLOR_NAMES,
    ENDPOINT_CONSUMABLE_CONFIG,
    ENDPOINT_PRODUCT_CONFIG,
    ENDPOINT_PRODUCT_LOGS,
    ENDPOINT_PRODUCT_STATUS,
    ENDPOINT_PRODUCT_USAGE,
)
from .models import (
    Consumable,
    EventLogEntry,
    JobEntry,
    PrinterData,
    ProductInfo,
    SubunitUsage,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = ClientTimeout(total=20)


class HPPrinterError(Exception):
    """Base error for this integration."""


class HPPrinterConnectionError(HPPrinterError):
    """Raised when the printer cannot be reached."""


class HPPrinterParseError(HPPrinterError):
    """Raised when a response is not the LEDM document we expected."""


def _localname(tag: str) -> str:
    """Strip the XML namespace from a tag."""
    return tag.rpartition("}")[2]


def _strip_namespaces(element: Element) -> Element:
    """Rewrite every tag in the tree to its local name.

    HP's documents use a different namespace prefix per schema, which makes
    ordinary ElementTree paths unreadable. Since local names are unique enough
    within a document, flattening is both safe and far easier to follow.
    """
    for node in element.iter():
        node.tag = _localname(node.tag)
    return element


def _find(root: Element, name: str) -> Element | None:
    """Return the first descendant with the given local name."""
    if _localname(root.tag) == name:
        return root
    return root.find(f".//{name}")


def _text(root: Element | None, *names: str) -> str | None:
    """Walk down by local name and return the leaf text.

    Each name is resolved as a descendant of the previous match, so
    _text(info, "Version", "Date") will not accidentally match the Date
    belonging to a sibling element such as LanguagePackVersion.
    """
    node = root
    for name in names:
        if node is None:
            return None
        node = _find(node, name)
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def _int(root: Element | None, *names: str) -> int | None:
    """Return an int, or None when absent or non-numeric."""
    raw = _text(root, *names)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _float(root: Element | None, *names: str) -> float | None:
    """Return a float, or None when absent or non-numeric."""
    raw = _text(root, *names)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _date(root: Element | None, *names: str) -> datetime | None:
    """Return a date, discarding HP's unset-clock placeholder.

    Devices without a real-time clock (non-fax models such as the M182nw)
    report 1976-01-01 rather than omitting the field.
    """
    raw = _text(root, *names)
    if raw is None:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw[: len(fmt) + 2].rstrip("Z"), fmt)
        except ValueError:
            continue
        if parsed.year <= 1976:
            return None
        return parsed
    return None


def _enabled(value: str | None) -> bool | None:
    """Interpret HP's enabled/disabled and set/notSet string flags."""
    if value is None:
        return None
    return value.strip().lower() in ("enabled", "true", "set", "yes", "on")


class LEDMClient:
    """Read-only client for a printer's LEDM endpoints."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        port: int,
        use_ssl: bool,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        """Initialize the client.

        Printers serve a self-signed certificate and, at least on the models
        seen so far, only offer legacy static-RSA cipher suites such as
        AES128-GCM-SHA256. Python's default cipher list drops those, so a
        plain no-verify context is not enough -- the handshake fails before
        certificate checking is ever reached. Callers should pass a context
        built from a permissive cipher list.
        """
        self._session = session
        self._host = host
        self._port = port
        self._ssl = use_ssl
        self._ssl_context: ssl.SSLContext | bool = ssl_context or False

    @property
    def host(self) -> str:
        """Return the configured host."""
        return self._host

    @property
    def base_url(self) -> str:
        """Return the printer's base URL."""
        scheme = "https" if self._ssl else "http"
        return f"{scheme}://{self._host}:{self._port}"

    async def _fetch(self, endpoint: str) -> Element:
        """GET one LEDM document and return its namespace-stripped root."""
        url = f"{self.base_url}{endpoint}"
        try:
            async with self._session.get(
                url, timeout=REQUEST_TIMEOUT, ssl=self._ssl_context
            ) as response:
                response.raise_for_status()
                body = await response.text()
        except TimeoutError as err:
            raise HPPrinterConnectionError(f"Timeout fetching {endpoint}") from err
        except ClientError as err:
            raise HPPrinterConnectionError(f"Error fetching {endpoint}: {err}") from err

        try:
            root = DefusedET.fromstring(body)
        # defusedxml raises several distinct exception types.
        except Exception as err:
            raise HPPrinterParseError(f"Invalid XML from {endpoint}: {err}") from err

        return _strip_namespaces(root)

    async def async_get_product_info(self) -> ProductInfo:
        """Read static device information."""
        root = await self._fetch(ENDPOINT_PRODUCT_CONFIG)
        info = _find(root, "ProductInformation")
        if info is None:
            raise HPPrinterParseError("ProductConfigDyn missing ProductInformation")

        return ProductInfo(
            make_and_model=_text(info, "MakeAndModel"),
            make_and_model_family=_text(info, "MakeAndModelFamily"),
            serial_number=_text(info, "SerialNumber"),
            product_number=_text(info, "ProductNumber"),
            sku_identifier=_text(info, "SKUIdentifier"),
            uuid=_text(info, "UUID"),
            service_id=_text(info, "ServiceID"),
            firmware_date=_text(info, "Version", "Date"),
            language_pack_version=_text(info, "LanguagePackVersion", "Revision"),
            password_set=_enabled(_text(info, "PasswordStatus")),
            duplex_unit=_text(info, "DuplexUnit"),
        )

    async def async_get_data(self) -> PrinterData:
        """Fetch everything that changes, concurrently."""
        status_doc, usage_doc, consumable_doc, logs_doc = await asyncio.gather(
            self._fetch(ENDPOINT_PRODUCT_STATUS),
            self._fetch(ENDPOINT_PRODUCT_USAGE),
            self._fetch(ENDPOINT_CONSUMABLE_CONFIG),
            self._fetch(ENDPOINT_PRODUCT_LOGS),
        )

        status_node = _find(status_doc, "Status")
        loc = status_node.find("LocString") if status_node is not None else None

        consumables = self._parse_consumables(consumable_doc, usage_doc)
        events, jobs, assert_text = self._parse_logs(logs_doc)

        raw_status = _text(status_node, "StatusCategory")

        return PrinterData(
            status=raw_status.lower() if raw_status else None,
            status_message=loc.text.strip() if loc is not None and loc.text else None,
            consumables=consumables,
            printer=self._parse_subunit(usage_doc, "PrinterSubunit"),
            scanner=self._parse_subunit(usage_doc, "ScannerEngineSubunit"),
            copy=self._parse_subunit(usage_doc, "CopyApplicationSubunit"),
            events=events,
            jobs=jobs,
            assert_text=assert_text,
            genuine_supplies_only=_enabled(
                _text(consumable_doc, "GenuineHPSuppliesOnly")
            ),
        )

    def _parse_subunit(self, usage_doc: Element, subunit: str) -> SubunitUsage:
        """Parse one usage subunit.

        Counter names repeat across subunits, so the search is scoped to the
        subunit element rather than the whole document.
        """
        node = _find(usage_doc, subunit)
        if node is None:
            return SubunitUsage()
        return SubunitUsage(
            total_impressions=_int(node, "TotalImpressions"),
            monochrome_impressions=_int(node, "MonochromeImpressions"),
            color_impressions=_int(node, "ColorImpressions"),
            simplex_sheets=_int(node, "SimplexSheets"),
            duplex_sheets=_int(node, "DuplexSheets"),
            jam_events=_int(node, "JamEvents"),
            mispick_events=_int(node, "MispickEvents"),
            scan_images=_int(node, "ScanImages"),
            adf_images=_int(node, "AdfImages"),
            flatbed_images=_int(node, "FlatbedImages"),
        )

    def _parse_consumables(
        self, consumable_doc: Element, usage_doc: Element
    ) -> dict[str, Consumable]:
        """Merge cartridge config with per-cartridge usage counters.

        ConsumableConfigDyn keys cartridges by ConsumableLabelCode (K/C/M/Y);
        ProductUsageDyn keys the same cartridges by MarkerColor. They are
        joined here so a cartridge is one object rather than two.
        """
        usage_by_code: dict[str, Element] = {}
        subunit = _find(usage_doc, "ConsumableSubunit")
        if subunit is not None:
            for node in subunit.iter("Consumable"):
                marker = _text(node, "MarkerColor")
                if marker is None:
                    continue
                code = next(
                    (c for c, name in COLOR_NAMES.items() if name == marker.lower()),
                    marker[:1].upper(),
                )
                usage_by_code[code] = node

        result: dict[str, Consumable] = {}
        for node in consumable_doc.iter("ConsumableInfo"):
            code = _text(node, "ConsumableLabelCode")
            if code is None:
                continue
            usage = usage_by_code.get(code)
            life = _find(node, "ConsumableLifeState")
            result[code] = Consumable(
                label_code=code,
                color_name=COLOR_NAMES.get(code),
                consumable_type=_text(node, "ConsumableTypeEnum"),
                brand=_text(life, "Brand") if life is not None else None,
                state=_text(life, "ConsumableState") if life is not None else None,
                level_percent=_float(node, "ConsumablePercentageLevelRemaining"),
                pages_remaining=_int(usage, "EstimatedPagesRemaining"),
                total_impressions=_int(usage, "TotalImpressions"),
                station=_int(node, "ConsumableStation"),
                serial_number=_text(node, "SerialNumber"),
                part_number=_text(node, "ConsumableSelectibilityNumber"),
                max_capacity=_int(node, "Capacity", "MaxCapacity"),
                installed_at=_date(node, "Installation", "Date"),
                manufactured_at=_date(node, "Manufacturer", "Date"),
                warranty_expires_at=_date(node, "Warranty", "ExpirationDate"),
                counterfeit_refills=_int(
                    usage, "RefilledCount", "CounterfeitRefilledCount"
                ),
                genuine_refills=_int(usage, "RefilledCount", "GenuineRefilledCount"),
            )
        return result

    def _parse_logs(
        self, logs_doc: Element
    ) -> tuple[list[EventLogEntry], list[JobEntry], str | None]:
        """Parse the device event log and print job log.

        This is the diagnostic record HP's own tooling exposes only through a
        printed report; no other Home Assistant integration surfaces it. Codes
        are dotted families -- 13.x paper jams, 49.x firmware faults, 10.x
        supply-memory errors -- and the accompanying ErrorLog carries assert
        text when firmware has crashed.

        Both logs contain TotalImpressions, so each is parsed strictly within
        its own container to avoid cross-contamination.
        """
        events: list[EventLogEntry] = []
        event_log = _find(logs_doc, "EventLog")
        if event_log is not None:
            events.extend(
                EventLogEntry(
                    sequence=_int(node, "SequenceNumber"),
                    code=_text(node, "EventCode"),
                    impressions=_int(node, "TotalImpressions"),
                )
                for node in event_log.iter("Event")
            )
        events.sort(
            key=lambda e: e.sequence if e.sequence is not None else -1, reverse=True
        )

        jobs: list[JobEntry] = []
        job_list = _find(logs_doc, "JobList")
        if job_list is not None:
            jobs.extend(
                JobEntry(
                    application_id=_text(node, "DriverJobApplicationID"),
                    user_id=_text(node, "DriverJobUserID"),
                    name=_text(node, "DriverJobName"),
                    monochrome_impressions=_int(node, "MonochromeImpressions"),
                    color_impressions=_int(node, "ColorImpressions"),
                    total_impressions=_int(node, "TotalImpressions"),
                )
                for node in job_list.iter("JobEntry")
            )

        assert_text = _text(logs_doc, "ErrorLog")
        return events, jobs, assert_text

    async def async_validate(self) -> ProductInfo:
        """Confirm the host speaks LEDM and return its identity."""
        info = await self.async_get_product_info()
        if not info.serial_number:
            raise HPPrinterParseError("Device did not report a serial number")
        return info


def as_diagnostics(data: Any) -> Any:
    """Best-effort conversion of dataclasses to plain types for diagnostics."""
    if hasattr(data, "__dataclass_fields__"):
        return {
            name: as_diagnostics(getattr(data, name))
            for name in data.__dataclass_fields__
        }
    if isinstance(data, dict):
        return {key: as_diagnostics(value) for key, value in data.items()}
    if isinstance(data, list):
        return [as_diagnostics(item) for item in data]
    if isinstance(data, datetime):
        return data.isoformat()
    return data
