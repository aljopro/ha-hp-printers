"""Checks on the translation files that CI would otherwise only catch remotely.

Home Assistant matches translations to strings.json by key, not by content.
A missing key silently falls back to the English string, and a key that no
longer exists is dead weight nobody notices -- neither raises anything, so
hassfest is the only thing that would catch it, and it runs after a push.
Placeholders are the same trap: a dropped {device} renders a sentence with a
literal brace in it rather than failing.

The CJK check is the copy-paste guard. Every string in this integration is
prose -- no brand names, no code, no serial formats -- so a translated value
with no CJK in it is an untranslated leftover rather than a deliberate
exception. The one thing that is not prose is a value made entirely of
placeholders, which has no language to it in the first place.

Device names are the other half of this file's job. A sub-device is named by
a translation_key rather than by a string the integration assembles, which is
what lets "Black Cartridge" become "黑色墨盒" -- the two halves reorder, and
neither is left in English. The price is that a key the translation files do
not declare is not a missing string but a device whose *name* is the key, so
the expected key set is derived from const.py rather than trusted.
"""

import importlib.util
import json
from pathlib import Path
import re
import types

import pytest

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "hp_printers"
STRINGS = COMPONENT / "strings.json"
TRANSLATIONS = COMPONENT / "translations"
CONST = COMPONENT / "const.py"
SENSOR = COMPONENT / "sensor.py"

# Every other language is discovered from the directory rather than listed, so
# a translation added later is checked without this file being edited.
TRANSLATED = sorted(p for p in TRANSLATIONS.glob("*.json") if p.stem != "en")

PLACEHOLDER = re.compile(r"\{(\w+)\}")
CJK = re.compile(r"[一-鿿]")


def _flatten(tree: dict, prefix: str = "") -> dict[str, str]:
    """Return leaf strings keyed by their dotted path."""
    flat: dict[str, str] = {}
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


def _load(path: Path) -> dict[str, str]:
    """Return one translation file as a flat mapping."""
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


def _const() -> types.ModuleType:
    """Import const.py on its own, without the rest of the integration.

    const.py is the one module here with no Home Assistant import, which is
    what lets this file name the device keys without standing up the HA test
    harness. The whole point of the check below is that the key space is
    derivable, so it has to be derived from the code that builds it.
    """
    spec = importlib.util.spec_from_file_location("hp_printers_const", CONST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expected_device_keys() -> set[str]:
    """Every device name the integration can ask for, derived from const.py."""
    const = _const()
    nouns = set(const.CONSUMABLE_NOUNS.values()) | {const.DEFAULT_CONSUMABLE_NOUN}
    keys = set(const.SUBUNIT_KEYS.values())
    keys |= {
        const.consumable_device_key(noun, color)
        for noun in nouns
        for color in const.KNOWN_COLORS
    }
    # The fallback a colour this integration has never seen resolves to.
    keys.add(const.consumable_device_key("Cartridge", "chartreuse"))
    return keys


def test_english_is_the_source_of_truth() -> None:
    """strings.json and en.json are the same document.

    strings.json is what Home Assistant reads, and en.json is what hassfest
    compares every other language against. They are maintained as one change,
    so a commit that edits only one of them is a bug rather than a choice.
    """
    assert _load(TRANSLATIONS / "en.json") == _load(STRINGS)


@pytest.mark.parametrize("path", TRANSLATED, ids=lambda p: p.stem)
def test_translation_covers_every_key(path: Path) -> None:
    """A translation has exactly the keys of strings.json -- no more, no less.

    A missing key is the invisible one: Home Assistant shows the English
    string and no error, so the gap only surfaces as a complaint from someone
    reading the UI in a language they did not choose.
    """
    english = set(_load(STRINGS))
    translated = set(_load(path))

    assert not translated - english, (
        f"keys not in strings.json: {sorted(translated - english)}"
    )
    assert not english - translated, (
        f"untranslated keys: {sorted(english - translated)}"
    )


@pytest.mark.parametrize("path", TRANSLATED, ids=lambda p: p.stem)
def test_translation_keeps_every_placeholder(path: Path) -> None:
    """Each string keeps the placeholders its English original has.

    Home Assistant substitutes these; a missing or renamed one is rendered
    into the sentence verbatim, so a translation that drops {device} shows
    the user a literal brace instead of a printer name.
    """
    english = _load(STRINGS)
    translated = _load(path)

    mismatched = {
        key: (set(PLACEHOLDER.findall(english[key])), set(PLACEHOLDER.findall(value)))
        for key, value in translated.items()
        if set(PLACEHOLDER.findall(english[key])) != set(PLACEHOLDER.findall(value))
    }

    assert not mismatched, f"placeholder mismatch (english, translated): {mismatched}"


def _is_prose(value: str) -> bool:
    """True when a value has words of its own, not just placeholders.

    Two kinds of value are deliberately skipped. One made entirely of
    placeholders -- "{device_name} {label}" is identical in every language
    because there is nothing in it to translate. The other contains no
    letters at all: a unit of "%" is a symbol, and demanding Chinese
    characters of it would be demanding a translation that cannot exist.
    Treating "no prose" as "nothing to check" is a rule rather than a
    hand-maintained list of exceptions, so it cannot rot.
    """
    stripped = PLACEHOLDER.sub("", value).strip()
    return any(char.isalpha() for char in stripped)


@pytest.mark.parametrize("path", TRANSLATED, ids=lambda p: p.stem)
def test_translation_is_not_left_in_english(path: Path) -> None:
    """Every value that has words of its own is actually translated.

    Copy-paste leaves a value equal to the English source, which passes the
    key and placeholder checks above and still renders as English. Every
    string here is prose rather than a name, a code or a format, so a
    translated value with no CJK in it is always a mistake.
    """
    untranslated = {
        key: value
        for key, value in _load(path).items()
        if _is_prose(value) and not CJK.search(value)
    }

    assert not untranslated, f"left in English: {untranslated}"


def test_device_names_cover_every_combination_the_code_can_ask_for() -> None:
    """The device block has a name for every key const.py can produce.

    A device name is looked up by translation_key, and Home Assistant has no
    way to report a miss at runtime -- an unrecognised key silently becomes
    the device's *name*, so the user sees "consumable_drum_black" where the
    printer should be. Deriving the expected set from the same constants the
    runtime uses is what makes a new colour or supply type a test failure
    rather than a cosmetic bug report.
    """
    expected = _expected_device_keys()
    declared = set(json.loads(STRINGS.read_text(encoding="utf-8"))["device"])

    assert declared == expected, (
        f"missing: {sorted(expected - declared)}; stale: {sorted(declared - expected)}"
    )


def test_no_unit_is_defined_in_code() -> None:
    """sensor.py must not set native_unit_of_measurement on any description.

    A translated unit is ignored while the description still defines one, so
    leaving it behind is what produced Chinese entity names rendering
    "13,141 pages". The unit and the translation are two halves of one
    change: this test holds the code half, test_translation_declares_a_unit
    holds the JSON half.
    """
    source = SENSOR.read_text(encoding="utf-8")
    offenders = [
        f"line {no}: {line.strip()}"
        for no, line in enumerate(source.splitlines(), 1)
        if "native_unit_of_measurement" in line
    ]

    assert not offenders, f"units belong in the translations, not in code: {offenders}"


def test_translation_declares_a_unit_for_every_counter() -> None:
    """Every entity that used to carry a unit in code still carries one.

    The counterpart to the test above, and the exact set rather than a
    naming heuristic -- ``network_errors`` is a bare count, ``network_link_mode``
    is a string and ``printer_manufactured_at`` is a date, so a prefix rule
    would demand units of all three. A new counter added to sensor.py has to
    be added here too, which is the point: it forces a decision about the
    unit instead of rendering a bare number in every language.
    """
    page_counters = {
        "printer_total_pages", "printer_mono_pages", "printer_color_pages",
        "printer_simplex_sheets", "printer_duplex_sheets", "printer_jams",
        "printer_mispicks", "scanner_images", "scanner_adf_images",
        "scanner_flatbed_images", "scanner_duplex_sheets", "scan_job_pages",
        "scan_job_adf_pages", "scan_job_flatbed_pages", "scan_job_duplex_sheets",
        "scanner_jams", "scanner_mispicks", "copy_total_pages", "copy_mono_pages",
        "copy_color_pages", "copy_adf_pages", "copy_flatbed_pages",
        "genuine_color_pages", "genuine_mono_pages", "last_event_page",
        "cartridge_pages_remaining", "cartridge_pages_printed",
    }
    packet_counters = {
        "network_bad_packets", "network_framing_errors",
        "network_transmit_collisions", "network_late_collisions",
        "network_unsendable_packets", "network_packets_received",
        "network_packets_transmitted",
    }
    percent_sensors = {
        "cartridge_level", "cartridge_raw_level", "cartridge_low_threshold",
    }
    expected = page_counters | packet_counters | percent_sensors

    entity = json.loads(STRINGS.read_text(encoding="utf-8"))["entity"]["sensor"]
    with_unit = {key for key, entry in entity.items() if "unit_of_measurement" in entry}

    assert with_unit == expected, (
        f"missing a unit: {sorted(expected - with_unit)}; "
        f"unit that should not be there: {sorted(with_unit - expected)}"
    )
