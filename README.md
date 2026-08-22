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

See [Devices](#devices) for the full list.

## Why this one

Because the interesting data was going unused. Alongside the usual toner levels
and page counts, this exposes:

| Entity | What it tells you |
|---|---|
| **Last event code** | The printer's own fault log — `13.x` paper jams, `49.x` firmware faults, `10.x` supply-memory errors. The full history and any firmware assert text ride along as attributes. |
| **Firmware fault recorded** | Whether the printer has stored a firmware crash. |
| **Firmware date** | The build date of the installed firmware — the only version marker LEDM offers. |
| **Genuine supplies enforced** | Whether the printer will refuse third-party cartridges. Worth watching: a firmware update can switch this back on and stop a working printer. |
| **Genuine** *(per cartridge)* | Whether HP considers each cartridge genuine or a `clone`. |
| **Admin password set** | Whether the embedded web server password is configured. It gates *writes* only — reads stay open, which is why this integration needs no credentials. |
| **Mispicks / jams** | Not an alert so much as a trend. A mispick count that starts climbing is a pickup roller glazing over, weeks before it starts eating paper. |

You also get to **name the printer during setup**, and entity IDs follow that
name — `sensor.laserjet_status`, not `sensor.hp_color_laserjet_mfp_m182nw_192_168_0_64_status`.

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

## Devices

The printer is one device; each cartridge is a sub-device linked to it, since
cartridges are independently replaceable and carry their own serial numbers.

Entities whose data a given model does not report are not created at all —
a printer with no document feeder, duplexer or fax simply gets fewer entities
rather than a row of `unknown`.

Depending on the model, entities cover:

- Printer status, page counters, jams, mispicks, firmware information, event
  history, and diagnostic state.
- Scanner and copier counters, when those capabilities are present.
- Per-cartridge level, pages remaining, pages printed, part information, dates,
  genuine/clone status, and problem state.

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

## License

MIT

The integration icon is original artwork. `brand-icon-mdi.svg` is an unused
alternative derived from the `printer` glyph in
[Material Design Icons](https://pictogrammers.com/library/mdi/) by the
Pictogrammers group, used under the Apache License 2.0.
