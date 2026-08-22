"""Tests for the config-flow probe and reauth flows.

The probe is what turns a user's host/port/ssl inputs into either a
config entry or one of two error reasons. Reauth simply aborts with a
guidance message, since this integration reads without credentials.

These tests exercise the flow directly rather than going through
``hass.config_entries.flow.async_init``, which requires a live Home
Assistant bootstrap. The probe only depends on ``self.hass`` to
construct an ``LEDMClient``, so we patch both ``async_get_clientsession``
and ``LEDMClient``.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_PORT, CONF_SSL
import pytest

from custom_components.hp_printers.api import HPPrinterConnectionError, HPPrinterError
from custom_components.hp_printers.config_flow import HPPrintersConfigFlow


def _build_flow() -> HPPrintersConfigFlow:
    """Construct a config flow instance wired to a stubbed ``hass``."""
    flow = HPPrintersConfigFlow()
    flow.hass = MagicMock()
    return flow


def _stub_validate(serial: str | None, model: str | None) -> MagicMock:
    """Return a stub client whose ``async_validate`` returns the given identity."""
    product_info = MagicMock()
    product_info.serial_number = serial
    product_info.make_and_model = model

    client = MagicMock()
    client.async_validate = AsyncMock(return_value=product_info)
    return client


def _stub_validate_raises(exc: Exception) -> MagicMock:
    """Return a stub client whose ``async_validate`` raises ``exc``."""
    client = MagicMock()
    client.async_validate = AsyncMock(side_effect=exc)
    return client


def _patch_probe(client: MagicMock):
    """Patch ``async_get_clientsession`` and ``LEDMClient`` for a probe test."""
    return (
        patch(
            "custom_components.hp_printers.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.hp_printers.config_flow.LEDMClient",
            return_value=client,
        ),
    )


async def test_probe_returns_serial_and_model_on_success() -> None:
    """A successful probe returns the printer's serial and model."""
    flow = _build_flow()
    client = _stub_validate("SN-1234", "HP Color LaserJet MFP M182nw")

    patch_session, patch_client = _patch_probe(client)
    with patch_session, patch_client:
        errors, serial, model = await flow._async_probe(  # noqa: SLF001
            {"host": "printer.local", CONF_PORT: 80, CONF_SSL: False}
        )

    assert errors == {}
    assert serial == "SN-1234"
    assert model == "HP Color LaserJet MFP M182nw"


async def test_probe_reports_cannot_connect_on_timeout() -> None:
    """A connection error maps to the ``cannot_connect`` reason."""
    flow = _build_flow()
    client = _stub_validate_raises(HPPrinterConnectionError("timeout"))

    patch_session, patch_client = _patch_probe(client)
    with patch_session, patch_client:
        errors, serial, model = await flow._async_probe(  # noqa: SLF001
            {"host": "printer.local", CONF_PORT: 80, CONF_SSL: False}
        )

    assert errors == {"base": "cannot_connect"}
    assert serial is None
    assert model is None


async def test_probe_reports_not_ledm_on_unexpected_response() -> None:
    """Any other ``HPPrinterError`` maps to the ``not_ledm`` reason."""
    flow = _build_flow()
    client = _stub_validate_raises(HPPrinterError("not LEDM"))

    patch_session, patch_client = _patch_probe(client)
    with patch_session, patch_client:
        errors, serial, model = await flow._async_probe(  # noqa: SLF001
            {"host": "printer.local", CONF_PORT: 80, CONF_SSL: False}
        )

    assert errors == {"base": "not_ledm"}
    assert serial is None
    assert model is None


async def test_probe_uses_https_port_when_ssl_enabled() -> None:
    """The probe uses the port from the user input, not the default."""
    flow = _build_flow()
    client = _stub_validate("SN-1234", "M182nw")

    patch_session, patch_client = _patch_probe(client)
    with patch_session, patch_client as client_ctor:
        await flow._async_probe(  # noqa: SLF001
            {"host": "printer.local", CONF_PORT: 8443, CONF_SSL: True}
        )

    # Verify the client was constructed with the user's port and ssl flag.
    assert client_ctor.call_args.args[2] == 8443
    assert client_ctor.call_args.args[3] is True


async def test_reauth_step_aborts_with_guidance() -> None:
    """The reauth flow aborts with the documented reason (no credentials)."""
    flow = _build_flow()

    result = await flow.async_step_reauth({})  # type: ignore[func-returns-value]

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_to_resolve"


@pytest.mark.parametrize(
    ("exc", "expected_reason"),
    [
        (HPPrinterConnectionError("timeout"), "cannot_connect"),
        (HPPrinterError("bad"), "not_ledm"),
    ],
)
async def test_probe_translates_exceptions_to_error_keys(
    exc: Exception, expected_reason: str
) -> None:
    """``HPPrinterError`` (and subclasses) map to error keys."""
    flow = _build_flow()
    client = _stub_validate_raises(exc)

    patch_session, patch_client = _patch_probe(client)
    with patch_session, patch_client:
        errors, _, _ = await flow._async_probe(  # noqa: SLF001
            {"host": "printer.local", CONF_PORT: 80, CONF_SSL: False}
        )

    assert errors == {"base": expected_reason}


async def test_probe_passes_hostname_to_client() -> None:
    """The probe passes the configured hostname to ``LEDMClient``."""
    flow = _build_flow()
    client = _stub_validate("SN-1", "M182nw")

    patch_session, patch_client = _patch_probe(client)
    with patch_session, patch_client as client_ctor:
        await flow._async_probe(  # noqa: SLF001
            {"host": "office-printer.local", CONF_PORT: 80, CONF_SSL: False}
        )

    # The constructor is called with positional arguments: session, host, port, ssl.
    assert client_ctor.call_args.args[1] == "office-printer.local"
