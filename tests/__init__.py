"""Tests for the HP Printers integration."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add a config entry to hass and set it up.

    Deliberately a plain helper rather than a fixture. As a fixture it would
    be ordered against the mocks by the test signature, and a test that
    listed it before the client patch would run setup against the real
    client and open a socket. Called from the test body, every mock is
    already in place. This mirrors homeassistant/tests/components/brother.
    """
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
