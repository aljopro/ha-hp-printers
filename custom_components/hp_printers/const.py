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
CONSUMABLE_NOUNS: Final = {
    "printhead": "Printhead",
    "inktank": "Ink Tank",
    "drum": "Drum",
    "maintenancekit": "Maintenance Kit",
}
DEFAULT_CONSUMABLE_NOUN: Final = "Cartridge"

COLOR_NAMES: Final = {
    "K": "black",
    "C": "cyan",
    "M": "magenta",
    "Y": "yellow",
    "CMY": "tricolor",
}
