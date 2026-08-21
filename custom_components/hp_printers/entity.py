"""Base entities for the HP Printers integration."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HPPrinterDataUpdateCoordinator
from .models import Consumable


class HPPrinterEntity(CoordinatorEntity[HPPrinterDataUpdateCoordinator]):
    """An entity belonging to the printer itself."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HPPrinterDataUpdateCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description

        info = coordinator.product_info
        serial = info.serial_number or coordinator.config_entry.entry_id

        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            configuration_url=coordinator.client.base_url,
            manufacturer=MANUFACTURER,
            model=info.make_and_model,
            model_id=info.product_number,
            serial_number=info.serial_number,
            name=coordinator.config_entry.title,
            # The firmware build date is the only version marker LEDM exposes.
            sw_version=info.firmware_date,
        )


class HPSubunitEntity(CoordinatorEntity[HPPrinterDataUpdateCoordinator]):
    """An entity belonging to one functional unit of a multifunction device.

    A scanner and a copier are distinct units of an MFP with their own
    counters, so they are modelled as sub-devices of the printer. Printing
    counters stay on the printer itself, since those are its primary metrics.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HPPrinterDataUpdateCoordinator,
        description: EntityDescription,
        subunit: str,
        subunit_label: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description

        info = coordinator.product_info
        printer_serial = info.serial_number or coordinator.config_entry.entry_id

        self._attr_unique_id = f"{printer_serial}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{printer_serial}_{subunit}")},
            via_device=(DOMAIN, printer_serial),
            manufacturer=MANUFACTURER,
            model=info.make_and_model,
            name=f"{coordinator.config_entry.title} {subunit_label}",
        )


class HPConsumableEntity(CoordinatorEntity[HPPrinterDataUpdateCoordinator]):
    """An entity belonging to a single cartridge.

    Cartridges are modelled as sub-devices because they are independently
    replaceable units with their own serial numbers, and grouping their
    entities keeps a four-colour printer legible in the UI.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HPPrinterDataUpdateCoordinator,
        description: EntityDescription,
        label_code: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        self.label_code = label_code

        info = coordinator.product_info
        printer_serial = info.serial_number or coordinator.config_entry.entry_id
        consumable = self.consumable

        colour = (consumable.color_name if consumable else None) or label_code
        pretty = colour.replace("_", " ").title()

        self._attr_unique_id = f"{printer_serial}_{label_code}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{printer_serial}_{label_code}")},
            via_device=(DOMAIN, printer_serial),
            manufacturer=(consumable.brand if consumable else None) or MANUFACTURER,
            model=consumable.part_number if consumable else None,
            serial_number=consumable.serial_number if consumable else None,
            name=f"{coordinator.config_entry.title} {pretty} Cartridge",
        )

    @property
    def consumable(self) -> Consumable | None:
        """Return this entity's cartridge, if the printer still reports it."""
        return self.coordinator.data.consumables.get(self.label_code)

    @property
    def available(self) -> bool:
        """Return True when the cartridge is present in the latest poll."""
        return super().available and self.consumable is not None
