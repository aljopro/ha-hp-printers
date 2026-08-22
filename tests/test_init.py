"""Bootstrap-level tests: setup, unload, and reload through real hass.

These complement the direct-call unit tests by exercising
``async_setup_entry`` / ``async_unload_entry`` through Home Assistant's
config-entry manager, so platform forwarding, runtime wiring, retry
behavior, and state cleanup are all covered end-to-end.
"""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.hp_printers.api import HPPrinterConnectionError

from . import setup_integration
from .conftest import TEST_SERIAL
from .fakes import make_product_info


async def test_setup_entry_loads_and_forwards_platforms(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
):
    """A healthy entry loads and exposes sensor entities."""
    entry = mock_config_entry
    await setup_integration(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not None

    sensor_states = hass.states.async_entity_ids("sensor")
    binary_sensor_states = hass.states.async_entity_ids("binary_sensor")
    assert sensor_states, "expected sensors after setup"
    assert binary_sensor_states, "expected binary sensors after setup"

    # One entity value flows all the way from the (mocked) parser into the
    # state machine: the printer reports "ready" in the shared fake data.
    assert any(
        state.state == "ready"
        for state in (hass.states.get(eid) for eid in sensor_states)
    )


async def test_unload_entry(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
):
    """Unloading takes the entry's entities unavailable."""
    entry = mock_config_entry
    await setup_integration(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    live = hass.states.async_entity_ids("sensor")
    assert live, "expected sensors before unload"
    assert any(hass.states.get(eid).state != STATE_UNAVAILABLE for eid in live)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED

    # Home Assistant does not drop the states of a registered entity whose
    # entry has unloaded; the registry writes an unavailable state for each
    # instead (see helpers/entity_registry._async_setup_entity_restore).
    # Asserting on that is stricter than asserting absence, because a stale
    # value left behind by a bad unload would fail here.
    for domain in ("sensor", "binary_sensor"):
        entity_ids = hass.states.async_entity_ids(domain)
        assert entity_ids, f"expected {domain} entities to remain registered"
        assert all(
            hass.states.get(eid).state == STATE_UNAVAILABLE for eid in entity_ids
        )


async def test_setup_retries_when_printer_unreachable(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
):
    """A connection failure during validation schedules a retry."""
    mock_ledm_client.async_validate.side_effect = HPPrinterConnectionError("timeout")

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_fails_on_serial_mismatch(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
):
    """An entry repointed at a different printer fails hard."""
    mock_ledm_client.async_validate.return_value = make_product_info(
        serial_number="SN-DIFFERENT"
    )

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_reload_entry(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
):
    """Reloading a loaded entry succeeds and keeps entities present."""
    entry = mock_config_entry
    await setup_integration(hass, entry)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.async_entity_ids("sensor")


async def test_unique_id_is_serial(
    enable_custom_integrations,
    mock_config_entry,
):
    """Entries are keyed by serial number so DHCP changes do not duplicate."""
    assert mock_config_entry.unique_id == TEST_SERIAL


async def test_coordinator_backs_off_while_the_printer_is_unreachable(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
):
    """Repeated failures widen the polling interval; a success restores it."""
    entry = mock_config_entry
    await setup_integration(hass, entry)
    coordinator = entry.runtime_data
    configured = coordinator.update_interval

    mock_ledm_client.async_get_data.side_effect = HPPrinterConnectionError("asleep")

    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    first_failure = coordinator.update_interval
    assert first_failure > configured

    await coordinator.async_refresh()
    assert coordinator.update_interval > first_failure

    # The printer wakes up: the very next success goes back to the interval
    # the user configured, rather than staying backed off.
    mock_ledm_client.async_get_data.side_effect = None
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.update_interval == configured


async def test_entities_go_unavailable_and_recover(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
    caplog,
):
    """Entities follow the coordinator, and each transition is logged once."""
    entry = mock_config_entry
    await setup_integration(hass, entry)
    coordinator = entry.runtime_data

    status = next(
        eid for eid in hass.states.async_entity_ids("sensor") if eid.endswith("_status")
    )
    assert hass.states.get(status).state != STATE_UNAVAILABLE

    mock_ledm_client.async_get_data.side_effect = HPPrinterConnectionError("asleep")
    caplog.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(status).state == STATE_UNAVAILABLE
    # The log has to name the printer: with two entries configured, the
    # domain alone does not say which one stopped answering.
    assert entry.title in caplog.text

    # A second failure must not repeat the message.
    caplog.clear()
    await coordinator.async_refresh()
    assert "Error fetching" not in caplog.text

    mock_ledm_client.async_get_data.side_effect = None
    caplog.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(status).state != STATE_UNAVAILABLE
    assert "recovered" in caplog.text
