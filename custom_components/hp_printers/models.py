"""Data models for the HP Printers integration."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ProductInfo:
    """Static device information, read once at setup.

    Sourced from /DevMgmt/ProductConfigDyn.xml.
    """

    make_and_model: str | None = None
    make_and_model_family: str | None = None
    serial_number: str | None = None
    product_number: str | None = None
    sku_identifier: str | None = None
    # When the printer itself was built, from ProductInformation/Manufacturer.
    # Devices without a real-time clock report a placeholder the parser drops.
    manufactured_at: datetime | None = None
    uuid: str | None = None
    service_id: str | None = None
    # Firmware build date. Exposed by the device but not surfaced by any other
    # HA integration; it is the only firmware version marker LEDM offers.
    firmware_date: str | None = None
    language_pack_version: str | None = None
    # Whether the EWS admin password has been set. Note this gates *writes*
    # only -- LEDM reads stay open either way.
    password_set: bool | None = None
    duplex_unit: str | None = None
    friendly_name: str | None = None
    power_save: str | None = None
    power_save_timeout: str | None = None
    shutdown_delay: str | None = None


@dataclass(frozen=True, slots=True)
class Consumable:
    """A single cartridge / consumable."""

    label_code: str
    color_name: str | None = None
    consumable_type: str | None = None
    brand: str | None = None
    state: str | None = None
    level_percent: float | None = None
    pages_remaining: int | None = None
    total_impressions: int | None = None
    station: int | None = None
    serial_number: str | None = None
    part_number: str | None = None
    max_capacity: int | None = None
    installed_at: datetime | None = None
    manufactured_at: datetime | None = None
    warranty_expires_at: datetime | None = None
    counterfeit_refills: int | None = None
    genuine_refills: int | None = None
    family_name: str | None = None
    # Finer-grained than ConsumablePercentageLevelRemaining, which is rounded.
    # The device reports a negative sentinel when it does not know.
    raw_level_percent: float | None = None
    # Wear counters for the cartridge that was REMOVED from this slot, not the
    # one currently installed. ConsumableConfigCap places all three under
    # ConsumableInfo/PreviousCartridgeData. They are declared as plain
    # integers rather than percentages, and use 127 as an unknown sentinel.
    previous_drum_life: int | None = None
    previous_developer_life: int | None = None
    previous_engine_toner_remaining: int | None = None
    previous_part_number: str | None = None
    previous_serial_number: str | None = None
    # The manufacturer's own low threshold, so automations need not guess.
    low_threshold_percent: float | None = None
    measured_state: str | None = None

    @property
    def is_genuine(self) -> bool | None:
        """Return True when the device reports a genuine HP cartridge."""
        if self.brand is None:
            return None
        return self.brand.lower().replace(" ", "") not in ("clone", "unknown")


@dataclass(frozen=True, slots=True)
class SubunitUsage:
    """Counters for one usage subunit (printer, scanner, copy...)."""

    total_impressions: int | None = None
    monochrome_impressions: int | None = None
    color_impressions: int | None = None
    simplex_sheets: int | None = None
    duplex_sheets: int | None = None
    jam_events: int | None = None
    mispick_events: int | None = None
    scan_images: int | None = None
    adf_images: int | None = None
    flatbed_images: int | None = None


@dataclass(frozen=True, slots=True)
class EventLogEntry:
    """One entry from the device event log."""

    sequence: int | None = None
    code: str | None = None
    impressions: int | None = None


@dataclass(frozen=True, slots=True)
class JobEntry:
    """One entry from the device's print job log."""

    application_id: str | None = None
    user_id: str | None = None
    name: str | None = None
    monochrome_impressions: int | None = None
    color_impressions: int | None = None
    total_impressions: int | None = None


@dataclass(frozen=True, slots=True)
class PrinterData:
    """Everything fetched on a single coordinator refresh."""

    status: str | None = None
    status_message: str | None = None
    consumables: dict[str, Consumable] = field(default_factory=dict)
    printer: SubunitUsage = field(default_factory=SubunitUsage)
    scanner: SubunitUsage = field(default_factory=SubunitUsage)
    # ScanApplicationSubunit counts pages captured by a scan job. The scanner
    # engine counts every pass it makes, so it also includes copies: on the
    # M182nw the engine's 962 flatbed images are the scan application's 929
    # plus 35 copies (a few passes predate the copy counter).
    scan: SubunitUsage = field(default_factory=SubunitUsage)
    copy: SubunitUsage = field(default_factory=SubunitUsage)
    events: list[EventLogEntry] = field(default_factory=list)
    jobs: list[JobEntry] = field(default_factory=list)
    genuine_color_impressions: int | None = None
    genuine_mono_impressions: int | None = None
    assert_text: str | None = None
    genuine_supplies_only: bool | None = None

    @property
    def last_job(self) -> JobEntry | None:
        """Return the most recently recorded print job, if any."""
        return self.jobs[0] if self.jobs else None

    @property
    def last_event(self) -> EventLogEntry | None:
        """Return the most recent event log entry, if any."""
        if not self.events:
            return None
        return max(
            self.events,
            key=lambda e: e.sequence if e.sequence is not None else -1,
        )
