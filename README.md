# HP Printers for Home Assistant

A local-polling Home Assistant integration for HP printers that speak **LEDM**
(HP's "Low End Data Model" XML interface, served by the printer's embedded web
server). No cloud, no account, no credentials.

## Why another HP integration

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

**HACS** → three-dot menu → *Custom repositories* → add
`https://github.com/aljopro/ha-hp-printers` as an **Integration**, then install
and restart Home Assistant.

**Manually**: copy `custom_components/hp_printers` into your `config/custom_components`
directory and restart.

Then *Settings → Devices & Services → Add Integration → HP Printers*.

## Configuration

| Field | Notes |
|---|---|
| **Host** | The printer's address. A DHCP reservation is good practice, though entries are keyed on serial number so an address change will not orphan your entities. |
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

## Compatibility

Developed against an **HP Color LaserJet MFP M182nw**. LEDM is widely
implemented across HP's consumer and small-office range, so other models are
likely to work; the integration reads only endpoints it finds and skips what a
device does not report. Reports of other models working (or not) are welcome.

Requires Home Assistant **2026.8.2** or newer.

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
