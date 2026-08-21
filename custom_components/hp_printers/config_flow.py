"""Config flow for the HP Printers integration."""

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SSL
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .api import HPPrinterConnectionError, HPPrinterError, LEDMClient
from .const import (
    CONF_SCAN_INTERVAL_SECONDS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSL,
    DOMAIN,
    MAX_SCAN_INTERVAL_SECONDS,
    MIN_SCAN_INTERVAL_SECONDS,
)
from .coordinator import HPPrinterConfigEntry

SECTION_ADVANCED = "advanced_settings"

# Name and host are the only things most people need. Port and TLS are real
# but rarely changed, so they live behind a collapsed section.
_ADVANCED = section(
    vol.Schema(
        {
            vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
                NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_SSL, default=DEFAULT_SSL): BooleanSelector(),
        }
    ),
    {"collapsed": True},
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Optional(CONF_NAME): TextSelector(),
        vol.Required(SECTION_ADVANCED): _ADVANCED,
    }
)


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """Merge the advanced section into flat entry data."""
    data = {k: v for k, v in user_input.items() if k != SECTION_ADVANCED}
    advanced = user_input.get(SECTION_ADVANCED, {})
    data[CONF_PORT] = int(advanced.get(CONF_PORT, DEFAULT_PORT))
    data[CONF_SSL] = bool(advanced.get(CONF_SSL, DEFAULT_SSL))
    return data


class HPPrintersConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HP Printers."""

    VERSION = 1

    async def _async_probe(
        self, data: dict[str, Any]
    ) -> tuple[dict[str, str], str | None, str | None]:
        """Try to talk to the printer. Returns (errors, serial, model)."""
        client = LEDMClient(
            async_get_clientsession(self.hass, verify_ssl=False),
            data[CONF_HOST],
            data[CONF_PORT],
            data[CONF_SSL],
        )
        try:
            info = await client.async_validate()
        except HPPrinterConnectionError:
            return {"base": "cannot_connect"}, None, None
        except HPPrinterError:
            return {"base": "not_ledm"}, None, None
        return {}, info.serial_number, info.make_and_model

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            data = _flatten(user_input)
            errors, serial, model = await self._async_probe(data)

            if not errors and serial:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: data[CONF_HOST]}
                )
                title = (data.get(CONF_NAME) or model or "HP Printer").strip()
                data.pop(CONF_NAME, None)
                return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            data = _flatten(user_input)
            errors, serial, _model = await self._async_probe(data)

            if not errors and serial:
                # Refuse to silently repoint an entry at a different printer.
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_mismatch(reason="serial_mismatch")
                data.pop(CONF_NAME, None)
                return self.async_update_reload_and_abort(entry, data_updates=data)

        suggested = {
            CONF_HOST: entry.data[CONF_HOST],
            SECTION_ADVANCED: {
                CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
                CONF_SSL: entry.data.get(CONF_SSL, DEFAULT_SSL),
            },
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): TextSelector(),
                        vol.Required(SECTION_ADVANCED): _ADVANCED,
                    }
                ),
                user_input or suggested,
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: HPPrinterConfigEntry,
    ) -> "HPPrintersOptionsFlow":
        """Return the options flow."""
        return HPPrintersOptionsFlow()


class HPPrintersOptionsFlow(OptionsFlowWithReload):
    """Handle HP Printers options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the polling interval."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL_SECONDS: int(
                        user_input[CONF_SCAN_INTERVAL_SECONDS]
                    )
                }
            )

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_SECONDS, int(DEFAULT_SCAN_INTERVAL.total_seconds())
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL_SECONDS, default=current
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL_SECONDS,
                            max=MAX_SCAN_INTERVAL_SECONDS,
                            step=5,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
