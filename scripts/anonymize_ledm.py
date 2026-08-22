"""Anonymize a directory of captured LEDM XML before it is committed.

The capture script writes raw responses, which contain identifiers that
should not appear in a public repository. This script replaces the values
of well-known identifier tags with stable dummies, while preserving the
field *names* and the rest of the XML structure so the parser tests
exercise the same shapes the device emits.

Usage:
    ./.venv/bin/python scripts/anonymize_ledm.py scripts/captures/192.168.0.64-20260101T120000Z/

The output directory is created next to the input with the suffix
``-anon``. Review the diff before committing; the script logs every
replacement it makes so you can see what changed.
"""

import argparse
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
    # Network/identity
    "HostName": "printer.local",
    "FriendlyName": "printer.local",
    "MACAddress": "00:00:00:00:00:00",
}


# Patterns for free-text identifiers that may appear inside any element.
# The capture is left intact apart from the substitution so structural
# fidelity is preserved.
TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # IPv4 addresses.
    (
        re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
        "192.0.2.1",
    ),
    # IPv6 addresses (with or without zone id).
    (
        re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b"),
        "2001:db8::1",
    ),
    # IPv6 mDNS hostnames (NPI prefix + MAC-derived suffix).
    (
        re.compile(r"\bNPI[A-F0-9]{6,}\.local\.?\b", re.IGNORECASE),
        "printer.local",
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


def anonymize_file(path: Path) -> list[tuple[str, str, str]]:
    """Anonymize one XML file in place and return the list of replacements."""
    raw = path.read_text(encoding="utf-8")
    root = DefusedET.fromstring(raw)
    replacements: list[tuple[str, str, str]] = []
    substituted = _substitute_product_number(root, replacements)
    _walk_and_scrub(root, replacements, substituted)
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
        raw = path.read_text(encoding="utf-8")
        root = DefusedET.fromstring(raw)
        replacements: list[tuple[str, str, str]] = []
        _substitute_product_number(root, replacements)
        _walk_and_scrub(root, replacements)
        target = output / path.name
        target.write_bytes(DefusedET.tostring(root, encoding="utf-8"))
        print(f"{path.name}: {len(replacements)} replacement(s)")  # noqa: T201
        for local, original, replacement in replacements:
            print(f"  {local}: {original!r} -> {replacement!r}")  # noqa: T201

    print(f"\nAnonymized capture written to {output}")  # noqa: T201


if __name__ == "__main__":
    main()
