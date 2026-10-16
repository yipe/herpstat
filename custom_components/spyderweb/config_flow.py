"""Config flow: device address; reconfigure: new address; options: poll interval and unit."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

from .api import (
    SpyderWebConnectionError,
    SpyderWebInvalidResponse,
    SpyderWebRawStatusDisabled,
    Status,
    fetch_status,
)
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TEMPERATURE_UNIT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

UNITS = vol.In([UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS])
HOST_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


def normalize_host(raw: str) -> str:
    """Accept pasted URLs: 'http://192.168.1.5/RAWSTATUS' -> '192.168.1.5'."""
    host = re.sub(r"^[a-z]+://", "", raw.strip(), flags=re.IGNORECASE)
    return host.split("/", 1)[0]


class SpyderWebConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _async_probe(self, host: str) -> tuple[Status | None, dict[str, str]]:
        try:
            status = await fetch_status(async_get_clientsession(self.hass), host)
        except SpyderWebRawStatusDisabled:
            return None, {"base": "rawstatus_disabled"}
        except SpyderWebConnectionError:
            return None, {"base": "cannot_connect"}
        except SpyderWebInvalidResponse:
            return None, {"base": "invalid_response"}
        return status, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            status, errors = await self._async_probe(host)
            if status is not None:
                await self.async_set_unique_id(format_mac(status.system.mac))
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=status.system.nickname or "Herpstat",
                    data={CONF_HOST: host},
                    options={
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_TEMPERATURE_UNIT: user_input[CONF_TEMPERATURE_UNIT],
                    },
                )
        schema = HOST_SCHEMA.extend(
            {vol.Required(CONF_TEMPERATURE_UNIT, default=UnitOfTemperature.FAHRENHEIT): UNITS}
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the address of an existing Herpstat (e.g. after a DHCP change)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            status, errors = await self._async_probe(host)
            if status is not None:
                await self.async_set_unique_id(format_mac(status.system.mac))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_HOST: host})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(HOST_SCHEMA, user_input or entry.data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> SpyderWebOptionsFlow:
        return SpyderWebOptionsFlow()


class SpyderWebOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=3600)),
                    vol.Required(
                        CONF_TEMPERATURE_UNIT,
                        default=options.get(CONF_TEMPERATURE_UNIT, UnitOfTemperature.FAHRENHEIT),
                    ): UNITS,
                }
            ),
        )
