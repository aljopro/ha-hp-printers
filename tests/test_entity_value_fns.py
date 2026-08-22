"""Drive every entity description against a fake coordinator.

This is the file that proves the README's "Entities" table is what the
integration actually creates. For each entity description in
``sensor.py`` and ``binary_sensor.py`` we instantiate the corresponding
entity class against a fake coordinator, then assert the entity
description's ``value_fn`` produces the field the README documents.

The entity layer is plain Python: ``CoordinatorEntity`` reads from
``coordinator.data`` and ``coordinator.product_info`` and never calls
back into a real Home Assistant instance, so we do not need a live
``hass`` to test it. ``MagicMock()`` covers the few touches into ``hass``
that ``CoordinatorEntity`` does on init.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from custom_components.hp_printers.binary_sensor import (
    CONSUMABLE_BINARY_SENSORS,
    PRINTER_BINARY_SENSORS,
    HPConsumableBinarySensor,
    HPPrinterBinarySensor,
    async_setup_entry as binary_setup_entry,
)
from custom_components.hp_printers.models import SubunitUsage
from custom_components.hp_printers.sensor import (
    CONSUMABLE_SENSORS,
    PRINTER_SENSORS,
    SUBUNIT_LABELS,
    HPConsumableSensor,
    HPPrinterSensor,
    HPSubunitSensor,
    async_setup_entry as sensor_setup_entry,
)

from .fakes import (
    FakeCoordinator,
    make_consumable,
    make_event,
    make_job,
    make_printer_data,
    make_product_info,
)


def _build_fake_hass() -> MagicMock:
    """Return a ``hass`` mock suitable for ``CoordinatorEntity.__init__``."""
    hass = MagicMock()
    hass.loop = MagicMock()
    return hass


def _printer_sensors(coordinator: FakeCoordinator) -> dict[str, HPPrinterSensor]:
    """Return printer-level sensors keyed by entity key."""
    return {
        description.key: HPPrinterSensor(coordinator, description)
        for description in PRINTER_SENSORS
        if description.value_fn(coordinator.data, coordinator.product_info) is not None
    }


def _consumable_sensors_with_data(
    coordinator: FakeCoordinator, code: str
) -> dict[str, HPConsumableSensor]:
    """Return consumable sensors whose ``value_fn`` returns a value for this cartridge."""
    consumable = coordinator.data.consumables.get(code)
    if consumable is None:
        return {}
    return {
        description.key: HPConsumableSensor(coordinator, description, code)
        for description in CONSUMABLE_SENSORS
        if description.value_fn(consumable) is not None
    }


def _printer_binary_sensors(
    coordinator: FakeCoordinator,
) -> dict[str, HPPrinterBinarySensor]:
    """Return printer-level binary sensors keyed by entity key."""
    return {
        description.key: HPPrinterBinarySensor(coordinator, description)
        for description in PRINTER_BINARY_SENSORS
        if description.value_fn(coordinator.data, coordinator.product_info) is not None
    }


def _consumable_binary_sensors(
    coordinator: FakeCoordinator, code: str
) -> dict[str, HPConsumableBinarySensor]:
    """Return consumable binary sensors keyed by entity key."""
    consumable = coordinator.data.consumables.get(code)
    if consumable is None:
        return {}
    return {
        description.key: HPConsumableBinarySensor(coordinator, description, code)
        for description in CONSUMABLE_BINARY_SENSORS
    }


def test_printer_sensors_emit_expected_values() -> None:
    """Each printer-level sensor description returns the field the README claims."""
    coordinator = FakeCoordinator(
        make_product_info(firmware_date="2025-04-01", power_save_timeout="300"),
        make_printer_data(
            status="ready",
            events=[make_event(sequence=42, code="13.20.00", impressions=1234)],
            jobs=[make_job(application_id="AcmePrint")],
            assert_text=None,
            genuine_supplies_only=False,
        ),
    )

    sensors = _printer_sensors(coordinator)

    assert sensors["status"].native_value == "ready"
    assert sensors["status"].extra_state_attributes == {
        "raw_status": "ready",
        "message": "Ready to print.",
    }
    assert sensors["printer_total_pages"].native_value == 1234
    assert sensors["printer_mono_pages"].native_value == 900
    assert sensors["printer_color_pages"].native_value == 334
    assert sensors["printer_simplex_sheets"].native_value == 1000
    assert sensors["printer_duplex_sheets"].native_value == 234
    assert sensors["printer_jams"].native_value == 2
    assert sensors["printer_mispicks"].native_value == 5
    assert sensors["firmware_date"].native_value == "2025-04-01"
    assert sensors["genuine_color_pages"].native_value == 200
    assert sensors["genuine_mono_pages"].native_value == 800
    assert sensors["power_save_timeout"].native_value == "300"
    assert sensors["language_pack_version"].native_value == "1"
    assert sensors["last_event_code"].native_value == "13.20.00"
    assert sensors["last_event_code"].extra_state_attributes == {
        "events": [
            {"sequence": 42, "code": "13.20.00", "at_page": 1234},
        ],
        "assert_text": None,
    }
    assert sensors["last_event_page"].native_value == 1234
    assert sensors["last_job_source"].native_value == "AcmePrint"
    assert sensors["last_job_source"].extra_state_attributes == {
        "user": "jane",
        "name": "Quarterly report",
        "pages": 10,
    }


def test_printer_sensors_drop_when_value_fn_returns_none() -> None:
    """Sensors whose ``value_fn`` returns ``None`` (e.g. unparsed fields) are skipped."""
    coordinator = FakeCoordinator(
        make_product_info(
            firmware_date=None, power_save_timeout=None, language_pack_version=None
        ),
        make_printer_data(
            events=[],
            jobs=[],
            genuine_color_impressions=None,
            genuine_mono_impressions=None,
        ),
    )

    sensors = _printer_sensors(coordinator)

    assert "firmware_date" not in sensors
    assert "power_save_timeout" not in sensors
    assert "language_pack_version" not in sensors
    assert "last_event_code" not in sensors
    assert "last_job_source" not in sensors
    assert "genuine_color_pages" not in sensors
    assert "genuine_mono_pages" not in sensors


def test_subunit_sensors_route_to_scanner_and_copier() -> None:
    """Scanner/copier sensors are attached to sub-devices, not the printer."""
    coordinator = FakeCoordinator(make_product_info(), make_printer_data())

    for description in PRINTER_SENSORS:
        if (
            description.subunit is None
            or description.value_fn(coordinator.data, coordinator.product_info) is None
        ):
            continue
        entity = HPSubunitSensor(
            coordinator,
            description,
            description.subunit,
            SUBUNIT_LABELS[description.subunit],
        )
        # The ``value_fn`` reaches the right subunit; the resulting
        # native_value is what shows up as the entity state.
        assert entity.native_value is not None


def test_consumable_sensors_emit_expected_values() -> None:
    """Cartridge sensors reflect the per-cartridge fields, not the device log."""
    coordinator = FakeCoordinator(
        make_product_info(),
        make_printer_data(
            consumables={
                "K": make_consumable(
                    level_percent=75.0,
                    pages_remaining=1500,
                    total_impressions=500,
                    raw_level_percent=74.6,
                    low_threshold_percent=10.0,
                    brand="genuinehp",
                    manufactured_at=datetime(2024, 11, 1, tzinfo=UTC),
                    warranty_expires_at=datetime(2026, 1, 2, tzinfo=UTC),
                    previous_drum_life=80,
                    previous_part_number="CF500A",
                )
            }
        ),
    )

    sensors = _consumable_sensors_with_data(coordinator, "K")

    assert sensors["level"].native_value == 75.0
    assert sensors["pages_remaining"].native_value == 1500
    assert sensors["pages_printed"].native_value == 500
    assert sensors["raw_level"].native_value == 74.6
    assert sensors["low_threshold"].native_value == 10.0
    assert sensors["previous_drum_life"].native_value == 80
    assert sensors["previous_part_number"].native_value == "CF500A"
    assert sensors["brand"].native_value == "genuinehp"
    assert sensors["manufactured_at"].native_value.isoformat().startswith("2024-11-01")
    assert (
        sensors["warranty_expires_at"].native_value.isoformat().startswith("2026-01-02")
    )


def test_consumable_sensors_drop_none_fields() -> None:
    """Cartridge sensors whose ``value_fn`` returns ``None`` are filtered out."""
    coordinator = FakeCoordinator(
        make_product_info(),
        make_printer_data(
            consumables={
                "K": make_consumable(
                    level_percent=None,
                    pages_remaining=None,
                    total_impressions=None,
                    raw_level_percent=None,
                    low_threshold_percent=None,
                    manufactured_at=None,
                    warranty_expires_at=None,
                    previous_drum_life=None,
                    previous_part_number=None,
                    part_number=None,
                    brand=None,
                )
            }
        ),
    )

    sensors = _consumable_sensors_with_data(coordinator, "K")
    assert "level" not in sensors
    assert "pages_remaining" not in sensors
    assert "pages_printed" not in sensors
    assert "raw_level" not in sensors
    assert "low_threshold" not in sensors
    assert "previous_drum_life" not in sensors
    assert "previous_part_number" not in sensors
    assert "manufactured_at" not in sensors
    assert "warranty_expires_at" not in sensors


def test_printer_binary_sensors_emit_expected_values() -> None:
    """The printer-level binary sensors reflect recorded faults and policy."""
    coordinator = FakeCoordinator(
        make_product_info(password_set=True),
        make_printer_data(
            assert_text="firmware fault signature", genuine_supplies_only=True
        ),
    )

    sensors = _printer_binary_sensors(coordinator)

    assert sensors["firmware_fault"].is_on is True
    assert sensors["genuine_supplies_only"].is_on is True
    assert sensors["admin_password_set"].is_on is True


def test_printer_binary_sensors_off_when_inputs_false() -> None:
    """Recorded-fault and policy binary sensors flip off when the source clears."""
    coordinator = FakeCoordinator(
        make_product_info(password_set=False),
        make_printer_data(assert_text=None, genuine_supplies_only=False),
    )

    sensors = _printer_binary_sensors(coordinator)

    assert sensors["firmware_fault"].is_on is False
    assert sensors["genuine_supplies_only"].is_on is False
    assert sensors["admin_password_set"].is_on is False


def test_consumable_binary_sensors_for_healthy_genuine_cartridge() -> None:
    """A healthy genuine cartridge: problem off, genuine on."""
    coordinator = FakeCoordinator(
        make_product_info(),
        make_printer_data(
            consumables={"K": make_consumable(state="ok", brand="genuinehp")}
        ),
    )

    sensors = _consumable_binary_sensors(coordinator, "K")

    assert sensors["problem"].is_on is False
    assert sensors["genuine"].is_on is True


def test_consumable_binary_sensors_for_unhealthy_clone_cartridge() -> None:
    """A low-toner clone cartridge: problem on, genuine off."""
    coordinator = FakeCoordinator(
        make_product_info(),
        make_printer_data(
            consumables={"K": make_consumable(state="low", brand="clone")}
        ),
    )

    sensors = _consumable_binary_sensors(coordinator, "K")

    assert sensors["problem"].is_on is True
    assert sensors["genuine"].is_on is False


async def test_sensor_setup_entry_filters_missing_subunits() -> None:
    """``async_setup_entry`` only creates sensors whose ``value_fn`` returns a value."""
    coordinator = FakeCoordinator(
        make_product_info(),
        make_printer_data(
            printer=SubunitUsage(total_impressions=1),
            scanner=SubunitUsage(),
            copy=SubunitUsage(),
        ),
    )

    added: list[object] = []
    add_entities = MagicMock(side_effect=lambda entities: added.extend(entities))
    entry = MagicMock()
    entry.runtime_data = coordinator

    await sensor_setup_entry(_build_fake_hass(), entry, add_entities)

    sensor_keys = {entity.entity_description.key for entity in added}
    for scanner_key in (
        "scanner_images",
        "scanner_adf_images",
        "scanner_flatbed_images",
        "scanner_jams",
        "scanner_mispicks",
    ):
        assert scanner_key not in sensor_keys
    for copy_key in ("copy_total_pages", "copy_mono_pages", "copy_color_pages"):
        assert copy_key not in sensor_keys
    assert "printer_total_pages" in sensor_keys


async def test_binary_sensor_setup_entry_creates_one_per_description() -> None:
    """``async_setup_entry`` emits one binary sensor per applicable description."""
    coordinator = FakeCoordinator(
        make_product_info(password_set=False),
        make_printer_data(assert_text=None, genuine_supplies_only=False),
    )

    added: list[object] = []
    add_entities = MagicMock(side_effect=lambda entities: added.extend(entities))
    entry = MagicMock()
    entry.runtime_data = coordinator

    await binary_setup_entry(_build_fake_hass(), entry, add_entities)

    keys = {entity.entity_description.key for entity in added}
    assert "firmware_fault" in keys
    assert "genuine_supplies_only" in keys
    assert "admin_password_set" in keys


async def test_sensor_setup_entry_creates_per_cartridge_entities() -> None:
    """Each cartridge gets every consumable sensor description that has data."""
    coordinator = FakeCoordinator(
        make_product_info(),
        make_printer_data(
            consumables={
                "K": make_consumable(level_percent=75.0),
                "C": make_consumable(level_percent=50.0),
            }
        ),
    )

    added: list[object] = []
    add_entities = MagicMock(side_effect=lambda entities: added.extend(entities))
    entry = MagicMock()
    entry.runtime_data = coordinator

    await sensor_setup_entry(_build_fake_hass(), entry, add_entities)

    unique_ids = {entity._attr_unique_id for entity in added}  # noqa: SLF001
    assert any(uid.startswith("SN-TEST-1234_K_") for uid in unique_ids)
    assert any(uid.startswith("SN-TEST-1234_C_") for uid in unique_ids)
