"""Binary sensor platform for the HP Printers integration."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HPPrinterConfigEntry
from .entity import HPConsumableEntity, HPPrinterEntity
from .models import Consumable, PrinterData, ProductInfo

PARALLEL_UPDATES = 0

# Cartridge states the device reports as healthy. Anything else -- low,
# veryLow, outOfSupply, unauthorised variants -- is treated as a problem.
HEALTHY_CONSUMABLE_STATES = {"ok", "newgenuinehp", "new", "good"}


@dataclass(frozen=True, kw_only=True)
class HPPrinterBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a printer-level binary sensor."""

    value_fn: Callable[[PrinterData, ProductInfo], bool | None]


@dataclass(frozen=True, kw_only=True)
class HPConsumableBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a cartridge-level binary sensor."""

    value_fn: Callable[[Consumable], bool | None]


PRINTER_BINARY_SENSORS: tuple[HPPrinterBinarySensorDescription, ...] = (
    HPPrinterBinarySensorDescription(
        key="firmware_fault",
        translation_key="firmware_fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        # The device keeps assert text from the last firmware crash until it
        # is cleared, so this reflects a recorded fault rather than a live
        # one. To catch new faults, trigger on the last event code changing.
        value_fn=lambda data, _info: bool(data.assert_text),
    ),
    HPPrinterBinarySensorDescription(
        key="genuine_supplies_only",
        translation_key="genuine_supplies_only",
        entity_category=EntityCategory.DIAGNOSTIC,
        # When enabled, the printer refuses non-HP cartridges. Worth watching:
        # a firmware update can turn it back on and stop a working printer.
        value_fn=lambda data, _info: data.genuine_supplies_only,
    ),
    HPPrinterBinarySensorDescription(
        key="admin_password_set",
        translation_key="admin_password_set",
        entity_category=EntityCategory.DIAGNOSTIC,
        # The embedded web server password gates writes only; LEDM reads stay
        # open regardless, which is why this integration needs no credentials.
        value_fn=lambda _data, info: info.password_set,
    ),
)


CONSUMABLE_BINARY_SENSORS: tuple[HPConsumableBinarySensorDescription, ...] = (
    HPConsumableBinarySensorDescription(
        key="problem",
        translation_key="cartridge_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda c: (
            None
            if c.state is None
            else c.state.strip().lower() not in HEALTHY_CONSUMABLE_STATES
        ),
    ),
    HPConsumableBinarySensorDescription(
        key="genuine",
        translation_key="cartridge_genuine",
        entity_category=EntityCategory.DIAGNOSTIC,
        # HP labels third-party cartridges "clone" even when enforcement is
        # switched off, so this is reported regardless of whether it matters.
        value_fn=lambda c: c.is_genuine,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HPPrinterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors for a printer."""
    coordinator = entry.runtime_data
    data = coordinator.data
    info = coordinator.product_info

    entities: list[BinarySensorEntity] = [
        HPPrinterBinarySensor(coordinator, description)
        for description in PRINTER_BINARY_SENSORS
        if description.value_fn(data, info) is not None
    ]

    entities.extend(
        HPConsumableBinarySensor(coordinator, description, code)
        for code, consumable in data.consumables.items()
        for description in CONSUMABLE_BINARY_SENSORS
        if description.value_fn(consumable) is not None
    )

    async_add_entities(entities)


class HPPrinterBinarySensor(HPPrinterEntity, BinarySensorEntity):
    """A printer-level binary sensor."""

    entity_description: HPPrinterBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """Return the sensor state."""
        return self.entity_description.value_fn(
            self.coordinator.data, self.coordinator.product_info
        )


class HPConsumableBinarySensor(HPConsumableEntity, BinarySensorEntity):
    """A cartridge-level binary sensor."""

    entity_description: HPConsumableBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """Return the sensor state."""
        if (consumable := self.consumable) is None:
            return None
        return self.entity_description.value_fn(consumable)
