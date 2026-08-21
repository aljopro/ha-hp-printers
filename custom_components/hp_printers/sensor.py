"""Sensor platform for the HP Printers integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import STATUS_OPTIONS
from .coordinator import HPPrinterConfigEntry, HPPrinterDataUpdateCoordinator
from .entity import HPConsumableEntity, HPPrinterEntity
from .models import Consumable, PrinterData, ProductInfo

PARALLEL_UPDATES = 0

PAGES = "pages"


@dataclass(frozen=True, kw_only=True)
class HPPrinterSensorDescription(SensorEntityDescription):
    """Describes a printer-level sensor."""

    value_fn: Callable[[PrinterData, ProductInfo], StateType | date]
    attrs_fn: Callable[[PrinterData], dict[str, Any]] | None = None


@dataclass(frozen=True, kw_only=True)
class HPConsumableSensorDescription(SensorEntityDescription):
    """Describes a cartridge-level sensor."""

    value_fn: Callable[[Consumable], StateType | date]


def _counter(key: str, translation_key: str, getter: Callable[[PrinterData], Any]):
    """Build a monotonic page-counter description."""
    return HPPrinterSensorDescription(
        key=key,
        translation_key=translation_key,
        native_unit_of_measurement=PAGES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data, _info: getter(data),
    )


PRINTER_SENSORS: tuple[HPPrinterSensorDescription, ...] = (
    HPPrinterSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=STATUS_OPTIONS,
        value_fn=lambda data, _info: (
            data.status if data.status in STATUS_OPTIONS else None
        ),
        attrs_fn=lambda data: {"raw_status": data.status, "message": data.status_message},
    ),
    # --- printer counters ---
    _counter("printer_total_pages", "printer_total_pages", lambda d: d.printer.total_impressions),
    _counter("printer_mono_pages", "printer_mono_pages", lambda d: d.printer.monochrome_impressions),
    _counter("printer_color_pages", "printer_color_pages", lambda d: d.printer.color_impressions),
    _counter("printer_simplex_sheets", "printer_simplex_sheets", lambda d: d.printer.simplex_sheets),
    _counter("printer_duplex_sheets", "printer_duplex_sheets", lambda d: d.printer.duplex_sheets),
    _counter("printer_jams", "printer_jams", lambda d: d.printer.jam_events),
    _counter("printer_mispicks", "printer_mispicks", lambda d: d.printer.mispick_events),
    # --- scanner counters ---
    _counter("scanner_images", "scanner_images", lambda d: d.scanner.scan_images),
    _counter("scanner_adf_images", "scanner_adf_images", lambda d: d.scanner.adf_images),
    _counter("scanner_flatbed_images", "scanner_flatbed_images", lambda d: d.scanner.flatbed_images),
    _counter("scanner_jams", "scanner_jams", lambda d: d.scanner.jam_events),
    _counter("scanner_mispicks", "scanner_mispicks", lambda d: d.scanner.mispick_events),
    # --- copy counters ---
    _counter("copy_total_pages", "copy_total_pages", lambda d: d.copy.total_impressions),
    _counter("copy_mono_pages", "copy_mono_pages", lambda d: d.copy.monochrome_impressions),
    _counter("copy_color_pages", "copy_color_pages", lambda d: d.copy.color_impressions),
    # --- diagnostics: firmware and the device event log ---
    HPPrinterSensorDescription(
        key="firmware_date",
        translation_key="firmware_date",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _data, info: info.firmware_date,
    ),
    HPPrinterSensorDescription(
        key="language_pack_version",
        translation_key="language_pack_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda _data, info: info.language_pack_version,
    ),
    HPPrinterSensorDescription(
        key="last_event_code",
        translation_key="last_event_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data, _info: (
            data.last_event.code if data.last_event else None
        ),
        # The whole log is attached so a fault history is one click away.
        # Codes are dotted families: 10.x supply memory, 13.x paper jams,
        # 41.x media mismatch, 49.x firmware faults.
        attrs_fn=lambda data: {
            "events": [
                {
                    "sequence": event.sequence,
                    "code": event.code,
                    "at_page": event.impressions,
                }
                for event in data.events
            ],
            "assert_text": data.assert_text,
        },
    ),
    HPPrinterSensorDescription(
        key="last_event_page",
        translation_key="last_event_page",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PAGES,
        value_fn=lambda data, _info: (
            data.last_event.impressions if data.last_event else None
        ),
    ),
    HPPrinterSensorDescription(
        key="last_job_source",
        translation_key="last_job_source",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data, _info: (
            data.last_job.application_id if data.last_job else None
        ),
        attrs_fn=lambda data: {
            "user": data.last_job.user_id if data.last_job else None,
            "name": data.last_job.name if data.last_job else None,
            "pages": data.last_job.total_impressions if data.last_job else None,
        },
    ),
)


CONSUMABLE_SENSORS: tuple[HPConsumableSensorDescription, ...] = (
    HPConsumableSensorDescription(
        key="level",
        translation_key="cartridge_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.level_percent,
    ),
    HPConsumableSensorDescription(
        key="pages_remaining",
        translation_key="cartridge_pages_remaining",
        native_unit_of_measurement=PAGES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.pages_remaining,
    ),
    HPConsumableSensorDescription(
        key="pages_printed",
        translation_key="cartridge_pages_printed",
        native_unit_of_measurement=PAGES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.total_impressions,
    ),
    HPConsumableSensorDescription(
        key="brand",
        translation_key="cartridge_brand",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.brand,
    ),
    HPConsumableSensorDescription(
        key="part_number",
        translation_key="cartridge_part_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.part_number,
    ),
    HPConsumableSensorDescription(
        key="manufactured_at",
        translation_key="cartridge_manufactured_at",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.manufactured_at.date() if c.manufactured_at else None,
    ),
    HPConsumableSensorDescription(
        key="warranty_expires_at",
        translation_key="cartridge_warranty_expires_at",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: (
            c.warranty_expires_at.date() if c.warranty_expires_at else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HPPrinterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for a printer."""
    coordinator = entry.runtime_data
    data = coordinator.data
    info = coordinator.product_info

    entities: list[SensorEntity] = [
        HPPrinterSensor(coordinator, description)
        for description in PRINTER_SENSORS
        # Not every model populates every subunit -- a printer with no ADF or
        # no fax simply omits those counters. Skip them rather than creating
        # entities that can only ever be unknown.
        if description.value_fn(data, info) is not None
    ]

    entities.extend(
        HPConsumableSensor(coordinator, description, code)
        for code, consumable in data.consumables.items()
        for description in CONSUMABLE_SENSORS
        if description.value_fn(consumable) is not None
    )

    async_add_entities(entities)


class HPPrinterSensor(HPPrinterEntity, SensorEntity):
    """A printer-level sensor."""

    entity_description: HPPrinterSensorDescription

    @property
    def native_value(self) -> StateType | date:
        """Return the sensor value."""
        return self.entity_description.value_fn(
            self.coordinator.data, self.coordinator.product_info
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return supplementary detail, where the sensor defines any."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)


class HPConsumableSensor(HPConsumableEntity, SensorEntity):
    """A cartridge-level sensor."""

    entity_description: HPConsumableSensorDescription

    @property
    def native_value(self) -> StateType | date:
        """Return the sensor value."""
        if (consumable := self.consumable) is None:
            return None
        return self.entity_description.value_fn(consumable)
