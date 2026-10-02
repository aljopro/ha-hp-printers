"""Constants for the HP Printers integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "hp_printers"

MANUFACTURER: Final = "HP"

# Polling. HP consumer printers sleep aggressively and at least some models
# (e.g. the M182nw) have firmware faults on the sleep/wake path, so we
# deliberately do not poll as fast as the device would allow.
DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=60)
DEFAULT_PORT: Final = 80
DEFAULT_PORT_SSL: Final = 443
DEFAULT_SSL: Final = False

CONF_SCAN_INTERVAL_SECONDS: Final = "scan_interval_seconds"
MIN_SCAN_INTERVAL_SECONDS: Final = 15
MAX_SCAN_INTERVAL_SECONDS: Final = 3600

# LEDM ("Low End Data Model") endpoints. HP does not publish a specification
# for these; the device self-describes via DiscoveryTree.xml plus paired
# <Resource>Cap.xml / <Resource>Dyn.xml documents.
ENDPOINT_DISCOVERY: Final = "/DevMgmt/DiscoveryTree.xml"
ENDPOINT_PRODUCT_CONFIG: Final = "/DevMgmt/ProductConfigDyn.xml"
ENDPOINT_PRODUCT_STATUS: Final = "/DevMgmt/ProductStatusDyn.xml"
ENDPOINT_PRODUCT_USAGE: Final = "/DevMgmt/ProductUsageDyn.xml"
ENDPOINT_CONSUMABLE_CONFIG: Final = "/DevMgmt/ConsumableConfigDyn.xml"
ENDPOINT_PRODUCT_LOGS: Final = "/DevMgmt/ProductLogsDyn.xml"
# Network adaptor configuration and error counters. Not every model
# advertises it, so it is fetched tolerantly: a printer without it still
# updates normally, it just grows no network entities.
ENDPOINT_IO_CONFIG: Final = "/DevMgmt/IOConfigDyn.xml"

# Endpoints fetched once at setup rather than on every poll.
STATIC_ENDPOINTS: Final = (ENDPOINT_PRODUCT_CONFIG,)

# StatusCategory values observed across HP LEDM devices. The device may report
# a value outside this set; entities fall back to the raw string.
STATUS_OPTIONS: Final = [
    "cancelling",
    "closedoorcover",
    "copying",
    "inpowersave",
    "initializing",
    "nomediainstalled",
    "off",
    "outofpaper",
    "papermisfeed",
    "processing",
    "ready",
    "scanning",
    "shuttingdown",
    "trayempty",
    "unknown",
]

# ConsumableLifeState/Brand. "clone" is HP's term for a non-HP cartridge; it is
# reported even when GenuineHPSuppliesOnly enforcement is disabled.
BRAND_GENUINE: Final = "genuinehp"
BRAND_CLONE: Final = "clone"

# Noun used in a consumable's device name, chosen from ConsumableTypeEnum.
# "Cartridge" is a reasonable default for both toner and ink; a printhead is
# the case where it would be plainly wrong. Capability documents are
# device-specific -- a laser declares only "toner" -- so unknown values fall
# back rather than being guessed at.
#
# These are English words, and they are only needed to label a consumable
# whose colour is not one this integration recognises. Every recognised
# noun/colour pair is named by looking up a translation instead -- see
# consumable_device_key.
CONSUMABLE_NOUNS: Final = {
    "printhead": "Printhead",
    "inktank": "Ink Tank",
    "drum": "Drum",
    "maintenancekit": "Maintenance Kit",
}
DEFAULT_CONSUMABLE_NOUN: Final = "Cartridge"

# ConsumableLabelCode -> MarkerColor, as the two documents spell it.
COLOR_NAMES: Final = {
    "K": "black",
    "C": "cyan",
    "M": "magenta",
    "Y": "yellow",
    "CMY": "tricolor",
}
KNOWN_COLORS: Final = frozenset(COLOR_NAMES.values())

# Sub-device name keys, looked up from the ``subunit`` field rather than from
# a label the caller has to remember to pass alongside it.
SUBUNIT_KEYS: Final = {
    "scanner": "subunit_scanner",
    "copy": "subunit_copier",
}


def consumable_device_key(noun: str, color: str | None) -> str:
    """Return the device translation key that names a consumable sub-device.

    The printer reports both halves of the name in English, so a translated
    name has to be a lookup rather than a string assembled at runtime. Every
    known noun/colour pair is its own key under the ``device`` block, which is
    also what lets a translation put the two in its own order: English reads
    "Black Cartridge", Chinese reads "黑色墨盒".

    A colour outside ``KNOWN_COLORS`` is a model this integration has never
    seen, and guessing at a key would render the raw key as the device name.
    Those take the fallback, which interpolates the English label -- the same
    name the integration showed before there were any translations.
    """
    if color not in KNOWN_COLORS:
        return "consumable_other"
    return f"consumable_{'_'.join(noun.strip().lower().split())}_{color}"
