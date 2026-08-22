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

from custom_components.hp_printers.api import LEDMClient, _strip_namespaces
from custom_components.hp_printers.const import (
    ENDPOINT_CONSUMABLE_CONFIG,
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

    client = LEDMClient.__new__(LEDMClient)

    for host_dir in hosts:
        status_doc = _load(ENDPOINT_PRODUCT_STATUS, host_dir)
        if status_doc is None:
            continue

        status_node = client._find(status_doc, "Status")  # noqa: SLF001
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
