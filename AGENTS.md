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
- `strings.json` supplies config-flow and entity names; update it when adding or renaming user-visible entities.
- `quality_scale.yaml` tracks which HA quality-scale rules the integration currently meets; update it when adding or removing coverage.

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
