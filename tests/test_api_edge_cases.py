"""Edge branches of the LEDM parser.

Printers return malformed, absent, or sentinel values often enough that the
defensive branches in ``api.py`` matter. These cover the paths a well-formed
document never reaches.
"""

from aiohttp import ClientError
from defusedxml import ElementTree as DefusedET
import pytest

from custom_components.hp_printers.api import (
    HPPrinterConnectionError,
    HPPrinterParseError,
    LEDMClient,
    _date,
    _find,
    _float,
    _int,
    _strip_namespaces,
)
from custom_components.hp_printers.models import SubunitUsage


def _xml(body: str):
    """Parse a namespace-stripped fragment."""
    return _strip_namespaces(DefusedET.fromstring(body))


@pytest.mark.parametrize(
    "text",
    ["not-a-number", "", "12.5.6", "N/A"],
)
def test_int_returns_none_for_non_numeric(text: str) -> None:
    """A non-numeric counter reads as unknown rather than raising."""
    assert _int(_xml(f"<r><Count>{text}</Count></r>"), "Count") is None


@pytest.mark.parametrize("text", ["not-a-number", "", "1,5"])
def test_float_returns_none_for_non_numeric(text: str) -> None:
    """A non-numeric level reads as unknown rather than raising."""
    assert _float(_xml(f"<r><Level>{text}</Level></r>"), "Level") is None


@pytest.mark.parametrize(
    "text",
    ["not-a-date", "2026-13-45", "yesterday", "20260101"],
)
def test_date_returns_none_for_unparseable(text: str) -> None:
    """An unparseable date reads as unknown rather than raising."""
    assert _date(_xml(f"<r><Date>{text}</Date></r>"), "Date") is None


def test_strip_namespaces_rewrites_every_tag() -> None:
    """Namespaced tags are flattened to local names throughout the tree."""
    root = _xml(
        '<dd:Root xmlns:dd="urn:x"><dd:Child><dd:Leaf>v</dd:Leaf></dd:Child></dd:Root>'
    )
    assert root.tag == "Root"
    assert [e.tag for e in root.iter()] == ["Root", "Child", "Leaf"]


def test_find_matches_the_root_itself() -> None:
    """Looking up the root's own name returns the root."""
    root = _xml("<Status><Category>ready</Category></Status>")
    assert _find(root, "Status") is root


def test_client_exposes_configured_host() -> None:
    """The client reports the host it was configured with."""
    client = LEDMClient(session=None, host="printer.local", port=80, use_ssl=False)
    assert client.host == "printer.local"
    assert client.base_url == "http://printer.local:80"


def test_parse_subunit_absent_yields_empty_counters() -> None:
    """A model without a given subunit yields empty counters, not an error."""
    client = LEDMClient(session=None, host="h", port=80, use_ssl=False)
    usage = client._parse_subunit(  # noqa: SLF001
        _xml("<ProductUsageDyn/>"), "ScannerEngineSubunit"
    )
    assert usage == SubunitUsage()


def test_parse_consumables_skips_entries_missing_identifiers() -> None:
    """Cartridge entries without an identifying code are skipped."""
    client = LEDMClient(session=None, host="h", port=80, use_ssl=False)
    # A usage Consumable with no MarkerColor, and a config entry with no
    # ConsumableLabelCode: neither can be keyed, so neither is returned.
    usage = _xml(
        "<ProductUsageDyn><ConsumableSubunit>"
        "<Consumable><TotalImpressions>3</TotalImpressions></Consumable>"
        "</ConsumableSubunit></ProductUsageDyn>"
    )
    config = _xml(
        "<ConsumableConfigDyn><ConsumableInfo>"
        "<ConsumablePercentageLevelRemaining>50</ConsumablePercentageLevelRemaining>"
        "</ConsumableInfo></ConsumableConfigDyn>"
    )
    assert client._parse_consumables(config, usage) == {}  # noqa: SLF001


class _FakeResponse:
    """Minimal aiohttp response supporting the client's usage."""

    def __init__(self, body: str, raise_exc: Exception | None = None) -> None:
        self._body = body
        self._raise = raise_exc

    def raise_for_status(self) -> None:
        if self._raise is not None:
            raise self._raise

    async def text(self) -> str:
        return self._body


class _FakeSession:
    """Session whose ``get`` is an async context manager, as aiohttp's is."""

    def __init__(self, response: _FakeResponse | Exception) -> None:
        self._response = response
        self.last_url: str | None = None

    def get(self, url: str, **_kwargs):
        self.last_url = url
        if isinstance(self._response, Exception):
            raise self._response
        return self

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *_exc) -> bool:
        return False


def _client_with(response) -> LEDMClient:
    return LEDMClient(
        session=_FakeSession(response), host="printer.local", port=80, use_ssl=False
    )


async def test_fetch_returns_namespace_stripped_document() -> None:
    """A successful fetch yields a parsed, namespace-stripped root."""
    client = _client_with(
        _FakeResponse('<dd:Root xmlns:dd="urn:x"><dd:Leaf>ok</dd:Leaf></dd:Root>')
    )
    root = await client._fetch("/DevMgmt/Thing.xml")  # noqa: SLF001

    assert root.tag == "Root"
    assert root.find("Leaf").text == "ok"
    assert client._session.last_url == (  # noqa: SLF001
        "http://printer.local:80/DevMgmt/Thing.xml"
    )


async def test_fetch_wraps_malformed_xml() -> None:
    """Malformed XML surfaces as a parse error, not a raw parser exception."""
    client = _client_with(_FakeResponse("<not-closed>"))
    with pytest.raises(HPPrinterParseError):
        await client._fetch("/DevMgmt/Thing.xml")  # noqa: SLF001


async def test_fetch_wraps_transport_errors() -> None:
    """Transport failures surface as connection errors."""
    client = _client_with(ClientError("boom"))
    with pytest.raises(HPPrinterConnectionError):
        await client._fetch("/DevMgmt/Thing.xml")  # noqa: SLF001


async def test_validate_returns_identity_when_serial_present() -> None:
    """Validation returns the parsed identity for a printer that reports one."""
    body = (
        "<ProductConfigDyn><ProductInformation>"
        "<MakeAndModel>HP Test</MakeAndModel>"
        "<SerialNumber>SN-1</SerialNumber>"
        "</ProductInformation></ProductConfigDyn>"
    )
    info = await _client_with(_FakeResponse(body)).async_validate()
    assert info.serial_number == "SN-1"
    assert info.make_and_model == "HP Test"


async def test_validate_rejects_a_device_without_a_serial() -> None:
    """A device that reports no serial cannot key an entry, so it is rejected."""
    body = "<ProductConfigDyn><ProductInformation/></ProductConfigDyn>"
    with pytest.raises(HPPrinterParseError):
        await _client_with(_FakeResponse(body)).async_validate()
