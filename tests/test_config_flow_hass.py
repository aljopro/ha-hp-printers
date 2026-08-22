"""Config-flow tests driven through Home Assistant's flow manager.

The probe-level tests in ``test_config_flow_probe.py`` call the handler
directly. These drive the same handler through ``hass.config_entries.flow``
so step wiring, schema shape, unique-id handling and entry creation are
exercised the way a user hits them.
"""

from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hp_printers.api import HPPrinterConnectionError
from custom_components.hp_printers.const import CONF_SCAN_INTERVAL_SECONDS, DOMAIN

from . import setup_integration
from .conftest import TEST_HOST, TEST_SERIAL, user_flow_input, zeroconf_info
from .fakes import make_product_info

MODEL = "HP Color LaserJet MFP M182nw"


async def test_user_flow_creates_entry(
    hass: HomeAssistant, enable_custom_integrations, mock_ledm_client
):
    """The user flow probes the printer and creates a loaded entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_flow_input()
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    # No name supplied, so the title falls back to the reported model.
    assert result["title"] == MODEL
    # The advanced section is flattened, and the name is not persisted.
    assert result["data"] == {CONF_HOST: TEST_HOST, CONF_PORT: 80, CONF_SSL: False}
    assert CONF_NAME not in result["data"]

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == TEST_SERIAL
    assert entry.state is ConfigEntryState.LOADED


async def test_user_flow_uses_supplied_name(
    hass: HomeAssistant, enable_custom_integrations, mock_ledm_client
):
    """A supplied name becomes the entry title, which drives entity IDs."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_flow_input(name="LaserJet")
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "LaserJet"


async def test_user_flow_shows_error_when_unreachable(
    hass: HomeAssistant, enable_custom_integrations, mock_ledm_client
):
    """A connection failure redisplays the form with an error, not an abort."""
    mock_ledm_client.async_validate.side_effect = HPPrinterConnectionError("timeout")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_flow_input()
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_serial_aborts_and_updates_host(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
):
    """The same printer at a new address updates the entry instead of duplicating."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_flow_input(host="192.0.2.99")
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert mock_config_entry.data[CONF_HOST] == "192.0.2.99"


async def test_zeroconf_discovery_creates_entry_on_web_port(
    hass: HomeAssistant, enable_custom_integrations, mock_ledm_client
):
    """Discovery confirms, then creates an entry on the web port, not IPP's."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == MODEL
    # The announcement carries port 631 (IPP); LEDM lives on the web server,
    # and the announced hostname is preferred with its trailing dot stripped.
    assert result["data"][CONF_PORT] == 80
    assert result["data"][CONF_HOST] == "HPE45A5B0.local"


async def test_zeroconf_discovery_names_the_printer(
    hass: HomeAssistant, enable_custom_integrations, mock_ledm_client
):
    """The confirm step accepts a name, which becomes the title."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Upstairs Printer"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Upstairs Printer"


async def test_zeroconf_aborts_when_already_configured(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
):
    """A rediscovered printer updates its host rather than adding a second entry."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == "HPE45A5B0.local"


async def test_zeroconf_aborts_when_probe_fails(
    hass: HomeAssistant, enable_custom_integrations, mock_ledm_client
):
    """An unreachable discovery is dropped rather than offered to the user."""
    mock_ledm_client.async_validate.side_effect = HPPrinterConnectionError("asleep")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_options_flow_updates_scan_interval(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
):
    """The options flow saves a new interval and reloads the entry."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL_SECONDS: 120}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_SCAN_INTERVAL_SECONDS] == 120
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_reconfigure_updates_connection_settings(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
):
    """Reconfiguring repoints the entry at a new address for the same printer."""
    await setup_integration(hass, mock_config_entry)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_flow_input(host="printer.local")
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_HOST] == "printer.local"


async def test_reconfigure_refuses_a_different_printer(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_ledm_client,
):
    """Pointing an entry at another printer aborts instead of silently rebinding."""
    await setup_integration(hass, mock_config_entry)
    mock_ledm_client.async_validate.return_value = make_product_info(
        serial_number="SN-OTHER"
    )

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_flow_input(host="192.0.2.50")
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "serial_mismatch"
    assert mock_config_entry.data[CONF_HOST] == TEST_HOST
