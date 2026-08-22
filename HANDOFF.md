# Handoff: bootstrap-level tests via pytest-homeassistant-custom-component

Date: 2026-08-21. Repo: `/Users/jensen/projects/ha-hp-printers` (branch `main`, clean at `c7c19c8`, plus two untracked files described below).

Read `AGENTS.md` first — it is canonical for verification commands, architecture, and test policy. This document covers only the work-in-flight that postdates it.

## Mission

Close the last two coverage holes by testing through a real Home Assistant instance:

- `custom_components/hp_printers/__init__.py` (setup/unload/reload) — was 50%
- config-flow lifecycle via `hass.config_entries.flow.async_init` — was 55%

Everything else (78 tests, parser/entity/coordinator/diagnostics/models/helpers/config-flow-probe layers, capture+anonymize scripts for real-printer fixtures) is committed and green.

## Environment change already made this session

Installed into `.venv`:

```
./.venv/bin/uv pip install --python .venv/bin/python "pytest-homeassistant-custom-component==0.13.356"
```

This is the release that pins `homeassistant==2026.8.2` (exactly our installed HA) and requires Python >=3.14. The previously documented Python 3.14 incompatibility (`recorder.Recorder` NameError under TYPE_CHECKING) is fixed upstream; do not reinstall older versions.

Side effects of that install (all verified working):

- pytest upgraded to 9.0.3, pytest-asyncio to 1.4.0
- The old `pytest>=8.0,<9` pin and the AGENTS.md note about pinning pytest-asyncio `<1.0` are now STALE — see Next Steps item 3
- Existing suite passes unchanged under the new stack: 78 passed in ~0.5s
- `pyproject.toml` `asyncio_mode = "auto"` coexists fine with phacc's plugin
- NOT yet recorded in `requirements_test.txt` or AGENTS.md — you must do that

## Working tree right now (untracked, uncommitted)

### `tests/conftest.py`

Shared fixtures for bootstrap tests. Keep as-is except one fixture (below):

- `mock_config_entry` — `MockConfigEntry(domain=DOMAIN, title="Office printer", unique_id="SN-TEST-1234", data={host: "192.0.2.1", port: 80, ssl: False})`
- `mock_ledm_client` — patches `LEDMClient` with autospec in BOTH namespaces it is bound: `custom_components.hp_printers.LEDMClient` (setup) and `custom_components.hp_printers.config_flow.LEDMClient` (probe). Instance returns `make_product_info()` from `async_validate()` and `make_printer_data()` from `async_get_data()`.
- Helpers `zeroconf_info()` (builds a real `ZeroconfServiceInfo`) and `user_flow_input()` (builds a schema-shaped user-step payload with the nested `advanced_settings` section dict). Both written for the not-yet-added flow-through-hass tests.
- `init_integration` — BROKEN, delete it. See bugs below.

### `tests/test_init.py`

Six tests. Three pass (`test_setup_retries_when_printer_unreachable`, `test_setup_fails_on_serial_mismatch`, `test_unique_id_is_serial`). Three fail with the two bugs explained next.

## The two open bugs — root causes known, fixes prescribed

### Bug 1: `TypeError: 'MockConfigEntry' object can't be awaited` at `await init_integration`

The `init_integration` async fixture's return value IS injected awaited — my test code wrongly wrote `entry = await init_integration`. The value arrives as a plain `MockConfigEntry`.

### Bug 2: `HASocketBlockedError` / "the test opens sockets" during setup

phacc enforces no-network via `pytest_socket`. Root cause: **fixture instantiation order**. In the failing tests the signature declares `init_integration` before `mock_ledm_client`, and nothing ties them by dependency, so `init_integration` runs setup FIRST — against the REAL `LEDMClient` — which attempts a TCP connect to 192.0.2.1 and trips the socket block. (A probe confirmed patching itself works: importlib reuses the patched module object.)

### Prescribed fix (one change solves both)

Delete the `init_integration` fixture and use HA-core's Brother-style pattern instead — a plain helper called from inside the test body, after all fixtures exist:

```python
# conftest.py
async def setup_entry(hass, entry):
    """Add entry to hass and set it up. Call from test body."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
```

Then in each test replace `init_integration` usage with `await setup_entry(hass, mock_config_entry)` and drop `await` (it returns the entry directly). Reference pattern: `/Users/jensen/projects/home-assistant/core/tests/components/brother/conftest.py` + `test_init.py` (their `init_integration` is imported and awaited in-body, never a fixture).

## Next steps, in order

1. Apply the prescribed fix to `tests/conftest.py` / `tests/test_init.py`; get all six green.
2. Add config-flow-through-hass tests (new file, e.g. `tests/test_config_flow_hass.py`). Use existing conftest helpers:
   - User flow e2e: `hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})` → form → `async_configure(flow_id, user_flow_input())` → `FlowResultType.CREATE_ENTRY`, title falls back to model ("HP Color LaserJet MFP M182nw"), data flattened `{host, port: 80, ssl: False}`, unique_id = serial, and entry reaches LOADED.
   - Duplicate serial: second flow with same serial aborts reason `"already_configured"` and updates host on the existing entry.
   - Zeroconf discovery: `async_init(..., context={"source": "zeroconf"}, data=zeroconf_info())` → lands in `zeroconf_confirm` step → submit name → CREATE_ENTRY keyed by serial, announced IPP port deliberately ignored (port stays 80).
   - Options flow e2e: `hass.config_entries.options.async_init(entry.entry_id)` → form → submit `{"scan_interval_seconds": 120}` → CREATE_ENTRY; `OptionsFlowWithReload` auto-reloads, assert options saved and entry still LOADED.
3. Bookkeeping:
   - `requirements_test.txt`: replace contents with `pytest-homeassistant-custom-component==0.13.356` (drop the stale pytest pin; phacc drives pytest/pytest-asyncio).
   - `AGENTS.md`: remove the stale pytest-asyncio `<1.0` note from Verification; document the phacc pin and that the suite now needs Python >=3.14; add the new test layer ("Bootstrap" — `test_init.py`, `test_config_flow_hass.py`) to Test Layers.
4. Re-run all gates (commands below), check coverage delta (`__init__.py` should jump ~50%→~100%; config_flow 55%→80%+).
5. Commit everything together (conftest, test_init, new flow tests, requirements, AGENTS.md). Suggested message: `Add hass-bootstrap tests via pytest-homeassistant-custom-component`.
6. Optional follow-up: capture real-printer fixtures per AGENTS.md workflow (user's printer was offered at `http://192.168.0.64`; scripts are committed; anonymize before committing anything).

## Verification commands

```
./.venv/bin/ruff check --config ruff_ha.toml custom_components/hp_printers tests scripts
./.venv/bin/ruff format --check --config ruff_ha.toml custom_components/hp_printers tests scripts
./.venv/bin/python -m compileall -q custom_components/hp_printers tests scripts
./.venv/bin/python -m pytest -q
```

Focused: `./.venv/bin/python -m pytest tests/test_init.py -q --tb=long`

## Gotchas learned this session (do not rediscover these)

- phacc blocks ALL sockets (`HASocketBlockedError` asserted in teardown at plugins.py:463). Any accidental network access fails loudly — good tripwire, but every path must be mocked.
- Patch targets must be the binding namespaces: `custom_components.hp_printers.LEDMClient` AND `...config_flow.LEDMClient` (both use `from .api import LEDMClient`).
- Request `enable_custom_integrations` in any test that loads the custom component through hass.
- Import `MockConfigEntry` from `pytest_homeassistant_custom_component.common`.
- Never make an async setup-helper a fixture when ordering matters; plain in-body helpers dodge both ordering and await-value pitfalls.
- `ZeroconfServiceInfo` fields (HA 2026.8): `ip_address`, `ip_addresses`, `port`, `hostname`, `type`, `name`, `properties`; `.host` property = `str(ip_address)`. Hostname trailing dot must be stripped by the flow (it does `rstrip(".")`).
- Config-flow user payload nests the section: `{"host": ..., "advanced_settings": {"port": 80, "ssl": False}}`; `_flatten()` merges it, and ticking ssl while port==80 flips port to 443.
- Setup semantics worth asserting: `HPPrinterError` → ConfigEntryNotReady → state SETUP_RETRY; serial != unique_id → ConfigEntryError → SETUP_ERROR; success → LOADED with `entry.runtime_data` set and platforms forwarded.
- fakes factory defaults: serial `SN-TEST-1234`, model "HP Color LaserJet MFP M182nw", status data has `status="ready"` — the end-to-end assertion `any(state.state == "ready" for sensor states)` ties parser→entity→state machine.
