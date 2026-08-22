"""Shared fixtures for bootstrap-level tests.

These fixtures stand up a real ``HomeAssistant`` via
``pytest-homeassistant-custom-component`` so the integration's setup,
unload, and config-flow paths are exercised through Home Assistant's own
config-entry manager rather than by calling functions directly.

``LEDMClient`` is patched in both namespaces that bind it --
``custom_components.hp_printers`` (setup) and
``custom_components.hp_printers.config_flow`` (probing) -- with an
autospec, so a future signature change to the client fails loudly here.
"""

from collections.abc import Generator
from ipaddress import IPv4Address
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hp_printers.const import DOMAIN

from .fakes import make_printer_data, make_product_info

TEST_HOST = "192.0.2.1"
TEST_SERIAL = "SN-TEST-1234"


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry keyed to the fixture printer's serial."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Office printer",
        unique_id=TEST_SERIAL,
        data={CONF_HOST: TEST_HOST, CONF_PORT: 80, CONF_SSL: False},
    )


@pytest.fixture
def mock_ledm_client() -> Generator[AsyncMock]:
    """Patch ``LEDMClient`` everywhere the integration binds it."""
    product_info = make_product_info()
    printer_data = make_printer_data()

    with (
        patch("custom_components.hp_printers.LEDMClient", autospec=True) as mock_class,
        patch(
            "custom_components.hp_printers.config_flow.LEDMClient",
            new=mock_class,
        ),
    ):
        client = mock_class.return_value
        client.async_validate.return_value = product_info
        client.async_get_product_info.return_value = product_info
        client.async_get_data.return_value = printer_data
        # base_url reaches DeviceInfo(configuration_url=...), which rejects
        # anything that is not a real URL -- an autospec MagicMock included.
        client.base_url = f"http://{TEST_HOST}"
        client.host = TEST_HOST
        yield client


def zeroconf_info(
    hostname: str = "HPE45A5B0.local.",
    host: str = "192.0.2.2",
) -> ZeroconfServiceInfo:
    """Build a ``ZeroconfServiceInfo`` shaped like HP IPP advertisements."""
    address = IPv4Address(host)
    return ZeroconfServiceInfo(
        ip_address=address,
        ip_addresses=[address],
        port=631,
        hostname=hostname,
        type="_ipp._tcp.local.",
        name="HP Printer 1234._ipp._tcp.local.",
        properties={"rp": "ipp/print"},
    )


def user_flow_input(
    host: str = TEST_HOST,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a valid ``user`` step payload (schema-shaped, section nested)."""
    advanced: dict[str, Any] = {CONF_PORT: 80, CONF_SSL: False}
    if "port" in overrides:
        advanced[CONF_PORT] = overrides.pop("port")
    if "ssl" in overrides:
        advanced[CONF_SSL] = overrides.pop("ssl")

    payload: dict[str, Any] = {CONF_HOST: host}
    if "name" in overrides:
        payload["name"] = overrides.pop("name")
    payload.update(overrides)
    payload["advanced_settings"] = advanced
    return payload
