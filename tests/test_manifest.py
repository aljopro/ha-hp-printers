"""Checks on manifest.json that CI would otherwise only catch remotely.

hassfest validates the manifest, but it runs as a separate GitHub Action
against a container, so a mistake here is discovered after a push rather
than before a commit. These are the rules that have actually bitten this
repository.
"""

import json
from pathlib import Path
import re

MANIFEST = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "hp_printers"
    / "manifest.json"
)

# Home Assistant's calendar versioning: YEAR.MONTH.RELEASE, with the month
# not zero-padded and RELEASE counting from 0 within the month.
CALENDAR_VERSION = re.compile(r"^\d{4}\.(?:[1-9]|1[0-2])\.\d+$")


def _manifest() -> dict:
    """Return the parsed manifest."""
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_version_follows_home_assistant_calendar_versioning() -> None:
    """The version is YEAR.MONTH.RELEASE, as Home Assistant itself uses.

    The release workflow computes this from the date and the number of
    releases already cut this month. A hand-edit that breaks the scheme
    would make the next computed version collide or go backwards.
    """
    version = _manifest()["version"]
    assert CALENDAR_VERSION.match(version), (
        f"{version!r} is not YEAR.MONTH.RELEASE (e.g. 2026.8.0)"
    )


def test_keys_are_ordered_the_way_hassfest_demands() -> None:
    """domain, then name, then everything else alphabetically.

    hassfest enforces this, and it failed CI once for exactly this reason.
    Ordering is invisible to Python, so only a test catches it locally.
    """
    keys = list(_manifest())

    assert keys[:2] == ["domain", "name"]
    assert keys[2:] == sorted(keys[2:])


def test_domain_matches_the_directory() -> None:
    """A manifest domain that disagrees with its folder does not load."""
    assert _manifest()["domain"] == MANIFEST.parent.name
