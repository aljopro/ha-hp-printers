"""Shared helpers for the HP Printers integration."""

import ssl

from homeassistant.util.ssl import SSLCipherList, client_context_no_verify


def printer_ssl_context() -> ssl.SSLContext:
    """Return an SSL context suitable for a printer's embedded web server.

    Printers present a self-signed certificate and negotiate legacy cipher
    suites that Home Assistant's default list excludes, so verification is
    disabled and the broader intermediate cipher list is used. The contexts
    behind this helper are created once at import time, so calling it from
    the event loop does not block.
    """
    return client_context_no_verify(SSLCipherList.INTERMEDIATE)
