"""Replay real anonymized LEDM captures against the parser.

When ``tests/fixtures/<host>/`` contains XML captured from a real printer
and run through ``scripts/anonymize_ledm.py``, this test loads each
endpoint and asserts the parser produces a sensible ``ProductInfo`` and
``PrinterData``. The fixtures are intentionally optional: a fresh
checkout without them still passes the test, so CI does not fail.

To add a fixture:

    ./.venv/bin/python scripts/capture_ledm.py --host <your-printer>
    ./.venv/bin/python scripts/anonymize_ledm.py scripts/captures/<dir>/
    cp -r scripts/captures/<dir>-anon tests/fixtures/<short-name>/
"""

from pathlib import Path

from defusedxml import ElementTree as DefusedET

from custom_components.hp_printers.api import LEDMClient, _find, _strip_namespaces
from custom_components.hp_printers.const import (
    ENDPOINT_CONSUMABLE_CONFIG,
    ENDPOINT_IO_CONFIG,
    ENDPOINT_PRODUCT_CONFIG,
    ENDPOINT_PRODUCT_LOGS,
    ENDPOINT_PRODUCT_STATUS,
    ENDPOINT_PRODUCT_USAGE,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load(endpoint: str, host_dir: Path) -> object | None:
    """Return the namespace-stripped XML for an endpoint, or ``None``."""
    filename = endpoint.lstrip("/").replace("/", "_")
    path = host_dir / filename
    if not path.exists():
        return None
    return _strip_namespaces(DefusedET.fromstring(path.read_text(encoding="utf-8")))


def _iter_hosts() -> list[Path]:
    """Return each host fixture directory, sorted for stable ordering."""
    if not FIXTURES_DIR.is_dir():
        return []
    return sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir())


def test_fixtures_parse_cleanly() -> None:
    """Every committed fixture parses without raising."""
    hosts = _iter_hosts()
    if not hosts:
        # No fixtures yet; this is informational, not a failure.
        return

    for host_dir in hosts:
        product_info_doc = _load(ENDPOINT_PRODUCT_CONFIG, host_dir)
        if product_info_doc is None:
            continue

        product_info = LEDMClient._parse_product_info(product_info_doc)  # noqa: SLF001

        # The integration refuses to set up without a serial number, so the
        # anonymizer replaces it with a stable dummy. Make sure it really is
        # there -- a missing serial would mean the anonymizer missed something.
        assert product_info.serial_number, (
            f"{host_dir.name}: ProductConfigDyn is missing SerialNumber"
        )
        assert product_info.make_and_model, (
            f"{host_dir.name}: ProductConfigDyn is missing MakeAndModel"
        )


def test_fixtures_consumables_round_trip() -> None:
    """If ConsumableConfigDyn is present, the parser produces a cartridge dict."""
    hosts = _iter_hosts()
    if not hosts:
        return

    client = LEDMClient.__new__(LEDMClient)

    for host_dir in hosts:
        config = _load(ENDPOINT_CONSUMABLE_CONFIG, host_dir)
        usage = _load(ENDPOINT_PRODUCT_USAGE, host_dir)
        if config is None or usage is None:
            continue

        consumables = client._parse_consumables(config, usage)  # noqa: SLF001

        assert consumables, f"{host_dir.name}: parser produced no consumables"

        for code, consumable in consumables.items():
            assert consumable.label_code == code
            # Page counts and brand are the fields most likely to be missed
            # by a future refactor; pin them at minimum.
            assert consumable.state is not None or consumable.brand is not None, (
                f"{host_dir.name}/{code}: cartridge has neither state nor brand"
            )


def test_fixtures_status_extracts_status_category() -> None:
    """ProductStatusDyn parses with a non-empty status string."""
    hosts = _iter_hosts()
    if not hosts:
        return

    for host_dir in hosts:
        status_doc = _load(ENDPOINT_PRODUCT_STATUS, host_dir)
        if status_doc is None:
            continue

        status_node = _find(status_doc, "Status")
        assert status_node is not None, (
            f"{host_dir.name}: ProductStatusDyn is missing Status"
        )


def test_fixtures_logs_returns_event_and_job_lists() -> None:
    """ProductLogsDyn parses into lists, even if the printer has no events."""
    hosts = _iter_hosts()
    if not hosts:
        return

    client = LEDMClient.__new__(LEDMClient)

    for host_dir in hosts:
        logs_doc = _load(ENDPOINT_PRODUCT_LOGS, host_dir)
        if logs_doc is None:
            continue

        events, jobs, assert_text = client._parse_logs(logs_doc)  # noqa: SLF001

        # ``events`` and ``jobs`` may be empty, but they must be lists --
        # a None would mean the parser missed a container.
        assert isinstance(events, list)
        assert isinstance(jobs, list)
        # ``assert_text`` is allowed to be None.
        assert assert_text is None or isinstance(assert_text, str)


def test_m182nw_fixture_pins_known_values() -> None:
    """The committed M182nw capture parses to the values that device reports.

    The generic tests above accept any fixture; this one pins the one we
    actually have, so a parser regression shows up as a concrete diff rather
    than a vaguer "still a list" assertion. Everything here was read off the
    real printer.
    """
    host_dir = FIXTURES_DIR / "m182nw"
    if not host_dir.is_dir():
        return

    client = LEDMClient.__new__(LEDMClient)
    info = LEDMClient._parse_product_info(  # noqa: SLF001
        _load(ENDPOINT_PRODUCT_CONFIG, host_dir)
    )

    assert info.make_and_model == "HP Color LaserJet MFP M182nw"
    assert info.firmware_date == "2023-12-06"
    # This model does not report ProductInformation/Manufacturer at all, so
    # the printer build date stays None and no entity is created for it.
    assert info.manufactured_at is None

    consumables = client._parse_consumables(  # noqa: SLF001
        _load(ENDPOINT_CONSUMABLE_CONFIG, host_dir),
        _load(ENDPOINT_PRODUCT_USAGE, host_dir),
    )

    assert sorted(consumables) == ["C", "K", "M", "Y"]
    # Station is the physical slot; the black cartridge is slot 0 here.
    assert {code: c.station for code, c in consumables.items()} == {
        "K": 0,
        "Y": 1,
        "M": 2,
        "C": 3,
    }
    assert all(c.consumable_type == "toner" for c in consumables.values())
    # The device has no real-time clock, so every Installation/Date is the
    # 1976 placeholder and the installed-date sensor is never created.
    assert all(c.installed_at is None for c in consumables.values())
    # Nor does it report refill counters.
    assert all(c.counterfeit_refills is None for c in consumables.values())

    usage = _load(ENDPOINT_PRODUCT_USAGE, host_dir)
    scanner = client._parse_subunit(usage, "ScannerEngineSubunit")  # noqa: SLF001
    copier = client._parse_subunit(usage, "CopyApplicationSubunit")  # noqa: SLF001

    scan_app = client._parse_subunit(usage, "ScanApplicationSubunit")  # noqa: SLF001

    # The engine counts every pass, including copies; the scan application
    # counts only scan jobs. Keeping them apart is the whole point of
    # parsing each subunit in its own scope.
    assert scanner.flatbed_images == 962
    assert scan_app.flatbed_images == 929
    # No ADF on this model: no feeder or duplex counters on either subunit.
    assert scanner.duplex_sheets is None
    assert copier.adf_images is None
    assert copier.flatbed_images is None
    assert copier.total_impressions == 35

    network = client._parse_network(_load(ENDPOINT_IO_CONFIG, host_dir))  # noqa: SLF001

    # Despite the "nw" in M182nw, this one is on the wire.
    assert network.port_type == "ethernet"
    assert network.link_mode == "100TX_FULL"
    assert network.status == "ready"
    # A clean link: every error counter reports, and all of them are zero.
    assert network.total_errors == 0
    assert all(value == 0 for value in network.error_counts.values())
    assert network.packets_received > 0
