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
- The test stack is a single pin: `pytest-homeassistant-custom-component==0.13.356`, which transitively fixes `homeassistant==2026.8.2`, `pytest==9.0.3` and `pytest-asyncio==1.4.0`. Do not pin pytest or pytest-asyncio separately in `requirements_test.txt`; a separate pin conflicts with what this package requires and breaks CI while local runs stay green.
- The suite requires Python 3.14, which that package's Home Assistant pin also requires.
- `ruff_ha.toml` is extracted from Home Assistant core but **diverges deliberately in one place**: `known-first-party` is `["custom_components", "tests", "scripts"]`, not `["homeassistant"]`. Core builds the `homeassistant` package; here it is a dependency. Left as core had it, isort groups `custom_components` with third-party imports and CI fails on ordering. Re-apply this if the file is ever re-extracted.
- `.pre-commit-config.yaml` runs the same lint, format, test and JSON-parse checks against this venv. Install with `./.venv/bin/uv pip install --python .venv/bin/python pre-commit && ./.venv/bin/pre-commit install`. The hooks are `repo: local` on purpose: the upstream Ruff mirror pins its own Ruff version, which would disagree with the one CI uses.
- Lint and format **`scripts` as well as `custom_components/hp_printers` and `tests`** — CI does, and a check that omits a directory hides real errors in it.

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
- Coverage is currently 99%, with every module at or above 97%, and
  `quality_scale.yaml` claims `test-coverage` and
  `config-flow-test-coverage` on that basis. Keep it there: if a change
  drops a module below 95%, either add the tests or downgrade the claim.
  Measure with
  `./.venv/bin/python -m pytest -q --cov=custom_components/hp_printers --cov-report=term-missing`.

## Architecture

- `api.py` is a read-only LEDM client; it fetches XML from the printer's `/DevMgmt/*` endpoints and maps it into immutable dataclasses in `models.py`.
- `coordinator.py` polls dynamic data; the default interval is 60 seconds and the static product configuration is refreshed every six hours.
- `sensor.py` and `binary_sensor.py` contain the actual entity descriptions. Parsing a field in `api.py` or `models.py` does not expose it in Home Assistant until an entity description is added there.
- `config_flow.py` validates the printer before creating an entry, supports mDNS discovery via IPP/IPPS advertisements, and keys entries by printer serial number so DHCP address changes do not duplicate devices.
- `coordinator.py` backs off on consecutive failures: `backoff_interval()` is a pure function so it is testable without hass, and `_apply_backoff` is the only place `update_interval` is mutated. The configured interval is a floor -- backoff must never make polling faster than the user asked for.
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
- **Config flow, unit** (`tests/test_config_flow_probe.py`,
  `tests/test_config_flow.py`): the probe helper, reauth, and `_flatten`
  normalization, called directly.
- **Parser edge cases** (`tests/test_api_edge_cases.py`): malformed and
  absent values, and the HTTP boundary in `_fetch` with a fake session.
- **Bootstrap, through hass** (`tests/test_init.py`,
  `tests/test_config_flow_hass.py`): setup, unload, reload, and every flow
  step driven through Home Assistant's own managers. These use
  `pytest-homeassistant-custom-component`, which blocks all sockets, so
  every network path must be mocked.
- **Real captures** (`tests/test_api_fixtures.py`): when
  `tests/fixtures/<host>/` is present, the fixture tests replay real XML.
  Tests skip gracefully when no fixture exists.

## Test fixtures and ordering

- `tests/__init__.py` exposes `setup_integration(hass, entry)` as a plain
  helper, called from the test body. It is deliberately **not** a fixture:
  as a fixture it is ordered against the mocks by the test signature, and a
  test listing it before the client patch runs setup against the real client
  and trips the socket block. This mirrors
  `homeassistant/tests/components/brother`.
- Patch `LEDMClient` in **both** binding namespaces:
  `custom_components.hp_printers.LEDMClient` and
  `custom_components.hp_printers.config_flow.LEDMClient`.
- Any test loading the integration through hass needs
  `enable_custom_integrations`.
- The mocked client must supply a real string for `base_url`; it reaches
  `DeviceInfo(configuration_url=...)`, which rejects a `MagicMock`.
- Unloading an entry does **not** remove its states. The entity registry
  writes an `unavailable` state for each registered entity instead, so
  assert on `STATE_UNAVAILABLE` rather than on absence.

- A real capture from an HP Color LaserJet MFP M182nw lives in
  `tests/fixtures/m182nw/`. `tests/test_api_fixtures.py` pins its known
  values, which is also the record of what that model does **not** report:
  no `ProductInformation/Manufacturer`, no refill counters, no ADF or
  duplex counters, and an `Installation/Date` of `1976-01-01` because the
  device has no real-time clock.
- `scripts/captures/` is git-ignored: raw captures contain the real serial
  number. Only the reviewed, anonymized copy under `tests/fixtures/`
  belongs in the repository.

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
