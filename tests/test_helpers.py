"""Tests for small support helpers."""

import ssl

from custom_components.hp_printers.helpers import printer_ssl_context


def test_printer_ssl_context_returns_sslcontext() -> None:
    """``printer_ssl_context`` returns a real ``ssl.SSLContext`` with a usable cipher list."""
    context = printer_ssl_context()

    assert isinstance(context, ssl.SSLContext)
    # The point of the helper is to enable legacy ciphers that the default
    # HA list excludes. We just check the context can be inspected without
    # error and has the expected minimum protocol version.
    assert context.minimum_version <= ssl.TLSVersion.TLSv1_2
