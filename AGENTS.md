# Agent Instructions

## Scope

- This repository is a standalone Home Assistant custom integration; the runtime entrypoint is `custom_components/hp_printers/__init__.py`.
- There is no runtime package manifest or lockfile; use the checked-in `.venv` for local verification.
- GitHub Actions are the canonical CI gate: `.github/workflows/ci.yaml` mirrors the commands below on every push and pull request, and `hassfest` validates the manifest and brand assets.

## Verification

- Install test tooling with `./.venv/bin/uv pip install --python .venv/bin/python -r requirements_test.txt` when needed.
- Run `./.venv/bin/python -m pytest -q` for the unit suite.
- Run `./.venv/bin/ruff check --config ruff_ha.toml custom_components/hp_printers tests`.
- Run `./.venv/bin/ruff format --check --config ruff_ha.toml custom_components/hp_printers tests`.
- Run `./.venv/bin/python -m compileall -q custom_components/hp_printers tests` for a syntax-only check.
- Ruff is configured for Home Assistant conventions in `ruff_ha.toml`; do not substitute an ambient Ruff/Python version when the repository venv is available.
- `pytest-asyncio` is pinned to `>=0.24,<1.0` for compatibility with the bundled Home Assistant test tooling; using a newer version will break imports inside HA's recorder fixtures.

## Test Policy

- **Any change that alters functionality must ship with tests.** A bug fix
  needs a regression test for the case it fixes; a new entity needs coverage
  of the parser path and the entity description that exposes it; a refactor
  must keep the existing suite green.
- The unit suite in `tests/` covers LEDM parsing in `api.py` and the
  config-flow normalization in `config_flow.py`. New behaviour should land
  in those modules (or a new sibling) and a matching test should appear
  alongside it.
- Do not delete a test to make a change pass. If a test is wrong, fix the
  test and explain why in the commit message.

## Architecture

- `api.py` is a read-only LEDM client; it fetches XML from the printer's `/DevMgmt/*` endpoints and maps it into immutable dataclasses in `models.py`.
- `coordinator.py` polls dynamic data; the default interval is 60 seconds and the static product configuration is refreshed every six hours.
- `sensor.py` and `binary_sensor.py` contain the actual entity descriptions. Parsing a field in `api.py` or `models.py` does not expose it in Home Assistant until an entity description is added there.
- `config_flow.py` validates the printer before creating an entry, supports mDNS discovery via IPP/IPPS advertisements, and keys entries by printer serial number so DHCP address changes do not duplicate devices.
- `coordinator.py` exposes `async_fetch_update` so the polling logic can be unit-tested without standing up a Home Assistant instance.
- `strings.json` supplies config-flow and entity names; update it when adding or renaming user-visible entities.
- `quality_scale.yaml` tracks which HA quality-scale rules the integration currently meets; update it when adding or removing coverage.

## Test Layers

The unit suite is built from plain Python doubles in `tests/fakes.py`
plus `MagicMock` for any HA layer we can't avoid, so most tests run in
milliseconds. Use the right layer for the change:

- **Parser behavior** (`tests/test_api.py`, `tests/test_api_parsing.py`,
  `tests/test_api_fixtures.py`): pure XML parsing, no event loop.
- **Models** (`tests/test_models.py`): dataclass invariants.
- **Entity layer** (`tests/test_entity_value_fns.py`): instantiate each
  description against a `FakeCoordinator` and assert
  `native_value` / `is_on` / `extra_state_attributes` matches the README.
- **Coordinator** (`tests/test_coordinator.py`): exercises
  `async_fetch_update` directly.
- **Diagnostics** (`tests/test_diagnostics.py`): the redaction pipeline.
- **Config flow** (`tests/test_config_flow_probe.py`): probe, reauth, and
  reconfigure.
- **Real captures** (`tests/test_api_fixtures.py`): when
  `tests/fixtures/<host>/` is present, the fixture tests replay real XML.
  Tests skip gracefully when no fixture exists.

## Capturing fixtures from a real printer

Real LEDM payloads are the highest-value test input because they capture
quirks no XML hand-rolled in a test file will reproduce. To add a
fixture:

1. Run `./.venv/bin/python scripts/capture_ledm.py --host <printer-host>`
   from a machine on the same network. The script writes raw XML into
   `scripts/captures/<host>-<timestamp>/`.
2. Run `./.venv/bin/python scripts/anonymize_ledm.py scripts/captures/<dir>/`.
   The anonymizer replaces `SerialNumber`, `UUID`, `ServiceID`, hostnames,
   IPs, and cartridge serial numbers with stable dummies and swaps
   `ProductNumber` for the captured `MakeAndModel`. Review the diff.
3. Copy the `<dir>-anon` directory into `tests/fixtures/<short-name>/`
   and commit. The fixture tests will pick it up automatically.
4. The capture is read-only -- every request is a `GET`.

## Device/API Traps

- The integration never writes to the printer. Preserve read-only `GET` behavior.
- HP LEDM is self-describing but undocumented; only create entities for values the device actually reports, otherwise the setup omits them.
- Printer HTTPS commonly uses a self-signed certificate and legacy static-RSA ciphers; use the existing `printer_ssl_context()` path rather than replacing it with default TLS settings.
- The zeroconf-announced IPP port is not the LEDM web-server port; discovery deliberately uses the printer hostname with the configured HTTP/HTTPS web port.
- Product and consumable fields can contain sentinel or historical values. Preserve the filtering and naming semantics in `api.py` and `models.py`, especially `PreviousCartridgeData`, which describes the cartridge removed from a slot rather than the installed cartridge.
- Diagnostics are intentionally redacted in `diagnostics.py`; do not expose host, serial, UUID, or user identifiers in new diagnostic output.

## Releases

- Cut a release by pushing a `vX.Y.Z` tag that matches `manifest.json` `version`; the HACS action (`.github/workflows/hacs.yaml`) drafts the release and `release-drafter.yaml` keeps the changelog current as PRs land.
- Label PRs so release-drafter categorizes them correctly: `breaking`, `enhancement`, `bug`, `documentation`, or `chore`.
