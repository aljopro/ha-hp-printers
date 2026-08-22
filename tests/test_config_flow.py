"""Tests for config-flow input normalization."""

from homeassistant.const import CONF_PORT, CONF_SSL

from custom_components.hp_printers.config_flow import SECTION_ADVANCED, _flatten


def test_flatten_defaults_to_http_port() -> None:
    """Missing advanced values use the plain HTTP defaults."""
    assert _flatten({SECTION_ADVANCED: {}}) == {
        CONF_PORT: 80,
        CONF_SSL: False,
    }


def test_flatten_https_follows_default_port_to_443() -> None:
    """Enabling HTTPS changes the untouched default port to 443."""
    assert _flatten({SECTION_ADVANCED: {CONF_SSL: True, CONF_PORT: 80}}) == {
        CONF_PORT: 443,
        CONF_SSL: True,
    }


def test_flatten_preserves_explicit_https_port_and_other_fields() -> None:
    """Explicit ports and ordinary config-flow fields are preserved."""
    assert _flatten(
        {
            "host": "printer.local",
            "name": "Office printer",
            SECTION_ADVANCED: {CONF_SSL: True, CONF_PORT: 8443},
        }
    ) == {
        "host": "printer.local",
        "name": "Office printer",
        CONF_PORT: 8443,
        CONF_SSL: True,
    }


def test_flatten_plain_http_follows_default_port_back_to_80() -> None:
    """Turning HTTPS off returns the untouched HTTPS default port to 80."""
    assert _flatten({SECTION_ADVANCED: {CONF_SSL: False, CONF_PORT: 443}}) == {
        CONF_PORT: 80,
        CONF_SSL: False,
    }
