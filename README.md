# HP Printers for Home Assistant

Local integration for HP printers that expose the **LEDM** XML interface from
their embedded web server. Reads the printer over HTTP/HTTPS — no cloud, no
account, no credentials, no writes.

## What you get

The printer itself is one device; each cartridge is a sub-device because
cartridges are independently replaceable and have their own serial numbers.
Depending on what the model reports, the integration exposes:

- **Printer**: status, page counters, jams, mispicks, firmware build date,
  event log, and diagnostic state.
- **Scanner and copier**: their own counters, when those capabilities exist.
- **Cartridges**: level, pages remaining, pages printed, part and serial
  information, dates, genuine/clone status, and problem state.

See [Entities](#entities) for the full list.

## Why this one

I started this integration because I wanted to **name my printer**. The
existing options created entity IDs like
`sensor.hp_color_laserjet_mfp_m182nw_192_168_0_64_status`, and there was no way
to clean them up short of manually renaming every entity in Home Assistant.
Setting a friendly name during setup, and having every entity ID follow that
name, was the original goal.

Once I had the printer responding, I started finding other things that were
missing or wrong in the existing integrations:

- The same `TotalImpressions` counter appearing under both the printer and
  the scanner because no one was parsing them in the right context.
- Cartridges that HP labeled `clone` showing up as the genuine part number
  (the chip lies about itself; the brand field is what tells the truth).
- A firmware crash from six months ago still showing as the device's current
  state, because nothing distinguished the recorded fault from a live one.
- The most recent event code buried in a thirty-page printed report rather
  than surfaced as a sensor.

This integration exists to fix that specific set of annoyances while keeping
the read-only, no-credentials, no-cloud design that the existing options got
right.

## Installation

### HACS

[![Open your Home Assistant instance and show the HP Printers integration in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aljopro&repository=ha-hp-printers&category=integration)

If the button does not work, add the repository manually:

1. Open **HACS** in Home Assistant.
2. Open the three-dot menu and select **Custom repositories**.
3. Enter `https://github.com/aljopro/ha-hp-printers`.
4. Select **Integration** as the repository type and click **Add**.
5. Search HACS for **HP Printers**, open it, and click **Download**.
6. Restart Home Assistant.

**Manually**: copy `custom_components/hp_printers` into your `config/custom_components`
directory and restart.

Then *Settings → Devices & Services → Add Integration → HP Printers*.

## Requirements

- An HP printer with an Embedded Web Server (EWS) that exposes the LEDM XML API.
- Home Assistant **2026.8.2** or newer.

## Configuration

| Field | Notes |
|---|---|
| **Host** | Prefer the printer's mDNS name over its IP — HP sets one from the MAC, such as `NPI2E7F3D.local` (you'll find it on the printer's Network Summary page, or in the TLS certificate's common name). It resolves to a MAC-derived IPv6 address that cannot change on a lease renewal, so no DHCP reservation is needed. An IP works too; entries are keyed on serial number, so an address change will not orphan your entities either way. |
| **Name** | Optional. Drives the device name and every entity ID. Leave blank to use the model name. |
| **Port / HTTPS** | Under *Advanced settings*. Defaults to port 80. Printers serve a self-signed certificate, which is not verified. |

Polling defaults to **60 seconds** and is adjustable under *Configure*. Printers
sleep between jobs and polling wakes them, so slower is gentler on the hardware.
When the printer stops answering — asleep, powered off, or off the network —
the interval doubles per consecutive failure up to ten minutes, and snaps back
to the configured value on the first successful read. Backing off never polls
faster than you asked for: a 30-minute interval stays 30 minutes.

## Devices

The printer is one device; each cartridge is a sub-device linked to it, since
cartridges are independently replaceable and carry their own serial numbers.

Entities whose data a given model does not report are not created at all —
a printer with no document feeder, duplexer or fax simply gets fewer entities
rather than a row of `unknown`.

## Entities

Entities are created only when the printer reports data for them. Diagnostic
and noisy entities are off by default; turn them on per-entity from the
device page.

### Printer

| Entity | Type | Notes |
|---|---|---|
| Status | sensor (enum) | Current state from the printer's `StatusCategory`. Localised in the integration. |
| Pages printed | sensor (total_increasing) | Lifetime page count. |
| Black and white pages | sensor (total_increasing) | Monochrome impressions. |
| Color pages | sensor (total_increasing) | Color impressions. |
| Single-sided sheets | sensor (total_increasing) | Simplex sheets. |
| Double-sided sheets | sensor (total_increasing) | Duplex sheets. |
| Paper jams | sensor (total_increasing) | Cumulative jam events. |
| Mispicks | sensor (total_increasing) | Cumulative mispick events. Watch for an upward trend — a pickup roller is glazing over long before paper starts jamming. |
| Color pages on genuine supplies | sensor (total_increasing) | Color impressions printed with HP-marked cartridges. |
| Black and white pages on genuine supplies | sensor (total_increasing) | Same, monochrome. |
| Firmware date | sensor (diagnostic) | Build date of the installed firmware — the only version marker LEDM exposes. |
| Last event code | sensor (diagnostic) | Most recent fault code (`13.x` paper jams, `49.x` firmware faults, `10.x` supply-memory errors). Full history and any firmware assert text are attached as attributes. |
| Last event at page | sensor (diagnostic) | Page count at which the most recent event occurred. |
| Manufactured | sensor (diagnostic, disabled by default, date) | When the printer was built, from `ProductInformation/Manufacturer`. Many models — including the M182nw — do not report it, and then no entity is created. |
| Power save timeout | sensor (diagnostic, disabled by default) | The sleep delay the printer is configured to use. |
| Language pack version | sensor (diagnostic, disabled by default) | The revision of the language pack. |
| Last job source | sensor (diagnostic, disabled by default) | Application that initiated the most recent print job, with user, name, and page count attached as attributes. |
| Firmware fault recorded | binary_sensor (diagnostic) | `on` when the printer still has assert text from a recorded firmware crash. This is a *recorded* fault, not a live one — to catch new faults, trigger on the last event code changing. |
| Genuine supplies enforced | binary_sensor (diagnostic) | `on` when the printer refuses third-party cartridges. A firmware update can switch this back on and stop a working printer. |
| Admin password set | binary_sensor (diagnostic) | `on` when the EWS admin password is configured. It gates *writes* only — LEDM reads stay open either way, which is why this integration needs no credentials. |

### Scanner

These appear only when the printer has a scanner subunit.

| Entity | Type | Notes |
|---|---|---|
| Pages scanned | sensor (total_increasing) | All scan images. |
| Pages scanned from feeder | sensor (total_increasing) | Pages pulled through the ADF. |
| Pages scanned from glass | sensor (total_increasing) | Pages scanned from the flatbed. |
| Double-sided sheets scanned | sensor (total_increasing) | Duplex sheets pulled through the feeder. Feederless models do not report it. |
| Scan job pages | sensor (total_increasing) | Pages captured by a scan job. The four "scan job" counters come from the scan application, not the scanner engine: the engine counts every pass it makes, so its totals include copies. On an M182nw the engine's 962 flatbed images are 929 scan-job pages plus 35 copies. |
| Scan job pages from feeder | sensor (total_increasing) | Scan-job pages pulled through the ADF. |
| Scan job pages from glass | sensor (total_increasing) | Scan-job pages taken from the flatbed. |
| Double-sided scan job sheets | sensor (total_increasing) | Duplex sheets scanned as part of a scan job. |
| Scanner jams | sensor (total_increasing) | Jam events attributed to the scanner. |
| Scanner mispicks | sensor (total_increasing) | Mispick events attributed to the scanner. |

### Copier

These appear only when the printer has a copy subunit.

| Entity | Type | Notes |
|---|---|---|
| Pages copied | sensor (total_increasing) | All copy impressions. |
| Black and white copies | sensor (total_increasing) | Monochrome copy impressions. |
| Color copies | sensor (total_increasing) | Color copy impressions. |
| Pages copied from feeder | sensor (total_increasing) | Copy impressions sourced from the ADF. |
| Pages copied from glass | sensor (total_increasing) | Copy impressions sourced from the flatbed. |

### Cartridges

Created per cartridge; the cartridge is its own sub-device because each one
has its own serial number and is replaced independently. The cartridge label
("Cartridge black", "Cartridge cyan", …) is generated from the colour and
type the printer reports.

| Entity | Type | Notes |
|---|---|---|
| Level | sensor | Manufacturer-rounded remaining percentage. The cartridge's slot (`station`) and type (`consumable_type`) are attached as attributes — both are fixed for the life of the cartridge, so they are not sensors of their own. |
| Pages remaining | sensor | `EstimatedPagesRemaining` for the installed cartridge. |
| Pages printed | sensor (total_increasing) | Lifetime impressions on the installed cartridge. |
| Brand | sensor (diagnostic) | "genuinehp" or "clone". HP labels third-party cartridges "clone" even when enforcement is off. |
| Part number | sensor (diagnostic, disabled by default) | The HP part number the printer expects. |
| Manufactured | sensor (diagnostic, date) | When the installed cartridge was manufactured. Devices without a real-time clock report `1976-01-01`; the parser discards that. |
| Installed | sensor (diagnostic, date) | When the cartridge was installed. Printers without a real-time clock report `1976-01-01`, which the parser discards, so the entity is absent on those models. |
| Warranty expires | sensor (diagnostic, disabled by default, date) | Cartridge warranty expiration. |
| Level (raw) | sensor (diagnostic, disabled by default) | Unrounded percentage. Useful when the rounded level sits at 1% for weeks. |
| Low threshold | sensor (diagnostic, disabled by default) | The manufacturer's own low threshold, so automations use a real value rather than guessing. |
| Unauthenticated refills | sensor (diagnostic, disabled by default) | Refills the cartridge chip recorded but could not authenticate. Not by itself a fault. |
| Genuine refills | sensor (diagnostic, disabled by default) | Refills the chip recorded as genuine. |
| Previous cartridge developer life | sensor (diagnostic, disabled by default) | Wear counter for the cartridge that was *removed* from this slot, not the one installed. |
| Previous cartridge drum life | sensor (diagnostic, disabled by default) | Drum wear for the removed cartridge. |
| Previous cartridge part number | sensor (diagnostic, disabled by default) | Part number of the removed cartridge. |
| Problem | binary_sensor | `on` when the cartridge state is anything other than the healthy set (`ok`, `newgenuinehp`, `new`, `good`). |
| Genuine | binary_sensor (diagnostic) | Whether the brand is HP or a clone.

## Troubleshooting

If setup cannot connect, confirm that the printer's EWS is reachable from the
Home Assistant host. Open the printer's host and port in a browser first; most
printers use HTTP on port 80. Enable **HTTPS** only when the printer's EWS is
configured for it.

For logs, enable debug logging from the integration device page:

1. Open **Settings → Devices & Services**.
2. Open **HP Printers** and select the printer.
3. Open the three-dot menu and select **Enable debug logging**.
4. Reproduce the problem, then return to the menu and select **Disable debug
   logging**.

When reporting a problem, also download diagnostics from the same menu. The
diagnostic file redacts the printer host and serial identifiers while retaining
the LEDM data needed to investigate unsupported models and missing entities.

## Compatibility

Developed against an **HP Color LaserJet MFP M182nw**. LEDM is widely
implemented across HP's consumer and small-office range, so other models are
likely to work; the integration reads only endpoints it finds and skips what a
device does not report. Reports of other models working (or not) are welcome.

## A note on LEDM

HP publishes no specification for it. The endpoint map here was derived by
reading a live device: `/DevMgmt/DiscoveryTree.xml` enumerates the available
resources, and each is exposed as a paired `<Resource>Cap.xml` — describing
types, access modes and legal values — and `<Resource>Dyn.xml` carrying current
values. The device is, in effect, its own documentation.

All access is read-only (`GET`). This integration never writes to your printer.

## Contributing

Contributions are welcome — this integration exists because the existing
options were not great, and there is plenty left to fix on the devices I
cannot test against.

### Reporting a bug

Please open an issue using the **Bug report** template. To make it actionable
include:

- Your Home Assistant version (Settings → About).
- Your printer model and firmware date (the **Firmware date** sensor).
- The integration's debug log.
- The diagnostics file (Devices & Services → HP Printers → ⋮ → Download
  diagnostics).

Diagnostics intentionally redact the printer host, serial, UUID, and user
identifiers, but keep the LEDM payloads — that is what makes it possible to
investigate unsupported models and missing entities without seeing your
network.

### Proposing a feature

Open an issue using the **Feature request** template. LEDM is undocumented,
so the most useful contributions are *evidence first*: capture the relevant
endpoint response from your printer (a `curl` against the EWS, or a snippet
from the diagnostics file) and describe what you would surface from it. A
feature without the source data usually has to wait for someone with the same
printer to confirm the field.

### Opening a pull request

1. Fork the repository and create a branch from `main`.
2. Make the change. Run the verification commands from `AGENTS.md`:
   - `./.venv/bin/ruff check --config ruff_ha.toml custom_components/hp_printers tests`
   - `./.venv/bin/ruff format --check --config ruff_ha.toml custom_components/hp_printers tests`
   - `./.venv/bin/python -m compileall -q custom_components/hp_printers tests`
   - `./.venv/bin/python -m pytest -q`
3. **Any change that alters functionality must ship with tests.** A bug fix
   gets a regression test, a new entity gets coverage of the parser path and
   the entity description it depends on, and a refactor keeps the existing
   tests green. A PR that changes behaviour without touching `tests/` will
   be asked to add tests before it can merge.
4. Update `custom_components/hp_printers/translations/en.json` and the
   matching `entity:` block in `strings.json` for any new or renamed
   user-visible entity.
5. Use the **Pull request** template; label the PR with `bug`, `enhancement`,
   `documentation`, `breaking`, or `chore` so release-drafter categorises it
   correctly.
6. CI must be green on the PR before review.

## License

MIT

The integration icon is original artwork. `brand-icon-mdi.svg` is an unused
alternative derived from the `printer` glyph in
[Material Design Icons](https://pictogrammers.com/library/mdi/) by the
Pictogrammers group, used under the Apache License 2.0.
