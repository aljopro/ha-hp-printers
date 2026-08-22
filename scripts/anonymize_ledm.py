"""Anonymize a directory of captured LEDM XML before it is committed.

The capture script writes raw responses, which contain identifiers that
should not appear in a public repository. This script replaces the values
of well-known identifier tags with stable dummies, while preserving the
field *names* and the rest of the XML structure so the parser tests
exercise the same shapes the device emits.

Usage:
    ./.venv/bin/python scripts/anonymize_ledm.py scripts/captures/192.168.0.64-20260101T120000Z/

The output directory is created next to the input with the suffix
``-anon``. The script prints every replacement it makes.

What it removes
---------------

- Device identity: serial number, UUID, ServiceID, SKU, friendly name.
- Cartridge identity: per-cartridge serial numbers.
- Network identity: every spelling of the hostname, the MAC in both
  ``HardwareAddress`` and the Bonjour service name, IPv4 and IPv6
  addresses (validated as addresses, so an enum such as ``100TX_FULL``
  survives), and the domain name.
- ``ProductNumber`` becomes the captured ``MakeAndModel``, so the fixture
  still says what device it came from without carrying the SKU.

What it deliberately keeps
--------------------------

Counters, dates, states, capabilities, and the netmask. A fixture is
worthless if the values are scrubbed too, and none of these identify
anyone.

**This is a best-effort filter over tag names we have seen.** It cannot
know about a field on a model nobody has captured yet. Read the output
diff before committing, and if a new endpoint is added to
``capture_ledm.py``, go through its identity fields, add them to
``IDENTIFIER_TAGS``, and cover them in ``tests/test_anonymize.py`` --
the network fields were added exactly that way.
"""

import argparse
from collections.abc import Callable
import ipaddress
from pathlib import Path
import re

from defusedxml import ElementTree as DefusedET

# Tags whose text content is an identifier and must be replaced. The keys are
# element local names; values are replacement strings or callables.
IDENTIFIER_TAGS: dict[str, str | None] = {
    # Device identifiers
    "SerialNumber": "SN-ANON-0000",
    "UUID": "00000000-0000-0000-0000-000000000000",
    "ServiceID": "00000000-0000-0000-0000-000000000000",
    "ProductNumber": None,  # replaced with the captured MakeAndModel
    "SKUIdentifier": "SKU-ANON-0000",
    # Per-cartridge identifiers
    "SupplySerialNumber": "SUPPLY-ANON-0000",
    "ConsumableSerialNumber": "CTR-ANON-0000",
    "ConsumableUniqueID": "UID-ANON-0000",
    # Network/identity. IOConfigDyn names the host four different ways and
    # carries the MAC twice -- once as HardwareAddress and once embedded in
    # the Bonjour service name -- so each spelling is listed explicitly.
    "HostName": "printer.local",
    "FriendlyName": "printer.local",
    "MACAddress": "00:00:00:00:00:00",
    "Hostname": "printer",
    "CurrentHostname": "printer",
    "DefaultHostname": "printer",
    "PreferredHostname": "printer",
    "BOOTP_DHCPv4SuppliedHostname": "printer",
    "HardwareAddress": "000000000000",
    "ApplicationServiceName": "HP printer (000000)",
    "DomainName": "local",
    "BOOTP_DHCPv4SuppliedDomainName": "local",
    "WINSServerName": "NOT_SET",
    # Not an identifier, but the IPv4 text pattern below would otherwise
    # rewrite a netmask into an address, which reads as a parser bug.
    "SubnetMask": "255.255.255.0",
}


def _ipv6_placeholder(match: re.Match[str]) -> str:
    """Replace a match only when it really is an IPv6 address."""
    try:
        ipaddress.IPv6Address(match.group(0))
    except ValueError:
        return match.group(0)
    return "2001:db8::1"


# Patterns for free-text identifiers that may appear inside any element.
# The capture is left intact apart from the substitution so structural
# fidelity is preserved.
TEXT_PATTERNS: tuple[
    tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]], ...
] = (
    # IPv4 addresses.
    (
        re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
        "192.0.2.1",
    ),
    # IPv6 addresses, including the compressed "::" forms a printer reports
    # for its link-local and ULA addresses. The candidate is validated rather
    # than trusted to the regex, so a value that merely looks address-shaped
    # (a time, an enum such as 100TX_FULL) is left alone.
    (
        re.compile(
            r"(?<![0-9A-Za-z:.])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}"
            r"(?![0-9A-Za-z:.])"
        ),
        _ipv6_placeholder,
    ),
    # IPv6 mDNS hostnames (NPI prefix + MAC-derived suffix).
    (
        re.compile(r"\bNPI[A-F0-9]{6,}\.local\.?\b", re.IGNORECASE),
        "printer.local",
    ),
    # The same name without the domain, as IOConfigDyn reports it.
    (
        re.compile(r"\bNPI[A-F0-9]{6,}\b", re.IGNORECASE),
        "printer",
    ),
)


def _local_name(tag: str) -> str:
    """Return the local name of an XML tag (strip the namespace)."""
    return tag.rpartition("}")[2]


def _identifier_value(local: str, configured: str | None) -> str | None:
    """Resolve the configured value or fall back to a stable placeholder."""
    if configured:
        return configured
    return f"ANON-{local.upper()}-0000"


def _walk_and_scrub(
    element: object,
    replacements: list[tuple[str, str, str]],
    skip: set[int] | None = None,
) -> None:
    """Recursively replace text in identifier tags and free-text patterns.

    ``skip`` holds elements another pass has already rewritten, so their new
    value is not itself treated as an identifier and overwritten again.
    """
    skip = skip or set()
    for child in getattr(element, "iter", list)():
        local = _local_name(child.tag)  # type: ignore[attr-defined]
        if id(child) in skip:
            continue
        if local in IDENTIFIER_TAGS and child.text:
            original = child.text.strip()
            if original:
                replacement = _identifier_value(local, IDENTIFIER_TAGS[local])
                if replacement and replacement != original:
                    replacements.append((local, original, replacement))
                if replacement:
                    child.text = replacement
                # The value was replaced wholesale; running the free-text
                # patterns over the replacement would rewrite it again --
                # a netmask placeholder into an IP, for instance.
                continue
        # Also scrub text content of any other element for IP / hostname patterns.
        if child.text:
            scrubbed = child.text
            for pattern, replacement in TEXT_PATTERNS:
                scrubbed = pattern.sub(replacement, scrubbed)
            if scrubbed != child.text:
                replacements.append(
                    ("#text", child.text.strip()[:64], scrubbed.strip()[:64])
                )
            child.text = scrubbed


def _substitute_product_number(
    root: object, replacements: list[tuple[str, str, str]]
) -> set[int]:
    """Replace ``ProductNumber`` with the captured ``MakeAndModel``.

    Keeps the model name recognizable in the fixture while the SKU stays
    out of the public repository. Returns the elements it rewrote so the
    identifier pass leaves them alone.
    """
    substituted: set[int] = set()
    model = None
    product_number = None

    for child in root.iter():  # type: ignore[attr-defined]
        local = _local_name(child.tag)
        if local == "MakeAndModel" and child.text:
            model = child.text.strip()
        if local == "ProductNumber" and child.text:
            product_number = child.text

    if model and product_number and model != product_number:
        for child in root.iter():  # type: ignore[attr-defined]
            if _local_name(child.tag) == "ProductNumber":
                child.text = model
                substituted.add(id(child))
                replacements.append(("ProductNumber", product_number, model))

    return substituted


def anonymize_file(
    path: Path, target: Path | None = None
) -> list[tuple[str, str, str]]:
    """Anonymize one XML file and return the replacements it made.

    Writes the result to ``target`` when given. This is the single entry
    point: ``main`` must not reimplement the pipeline, because a second copy
    is a second thing to keep in step -- which is exactly how the
    ProductNumber substitution came to be undone again after being fixed.
    """
    raw = path.read_text(encoding="utf-8")
    root = DefusedET.fromstring(raw)
    replacements: list[tuple[str, str, str]] = []
    substituted = _substitute_product_number(root, replacements)
    _walk_and_scrub(root, replacements, substituted)
    if target is not None:
        target.write_bytes(DefusedET.tostring(root, encoding="utf-8"))
    return replacements


def main() -> None:
    """Anonymize every XML file in the directory and write to a sibling ``-anon`` directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        help="Directory produced by capture_ledm.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (defaults to <input>-anon)",
    )
    args = parser.parse_args()

    if not args.input.is_dir():
        raise SystemExit(f"{args.input} is not a directory")

    output = args.output or args.input.with_name(args.input.name + "-anon")
    output.mkdir(parents=True, exist_ok=True)

    for path in sorted(args.input.glob("*.xml")):
        replacements = anonymize_file(path, output / path.name)
        print(f"{path.name}: {len(replacements)} replacement(s)")  # noqa: T201
        for local, original, replacement in replacements:
            print(f"  {local}: {original!r} -> {replacement!r}")  # noqa: T201

    print(f"\nAnonymized capture written to {output}")  # noqa: T201


if __name__ == "__main__":
    main()
