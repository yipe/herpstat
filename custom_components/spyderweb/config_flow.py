"""Config flow: manual setup, DHCP/zeroconf discovery, reconfigure; options: temperature unit."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import (
    SpyderWebConnectionError,
    SpyderWebInvalidResponse,
    SpyderWebRawStatusDisabled,
    Status,
    fetch_status,
)
from .const import CONF_TEMPERATURE_UNIT, DOMAIN

UNITS = vol.In([UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS])
HOST_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})
UNIT_SCHEMA = vol.Schema({vol.Required(CONF_TEMPERATURE_UNIT, default=UnitOfTemperature.FAHRENHEIT): UNITS})


def normalize_host(raw: str) -> str:
    """Accept pasted URLs: 'http://192.168.1.5/RAWSTATUS' -> '192.168.1.5'."""
    host = re.sub(r"^[a-z]+://", "", raw.strip(), flags=re.IGNORECASE)
    return host.split("/", 1)[0]


class SpyderWebConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    _discovered_host: str
    _discovered_name: str
    _rawstatus_off: bool

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
                await self.async_set_unique_id(format_mac(status.system.mac), raise_on_progress=False)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=status.system.nickname or "Herpstat",
                    data={CONF_HOST: host},
                    options={CONF_TEMPERATURE_UNIT: user_input[CONF_TEMPERATURE_UNIT]},
                )
        schema = HOST_SCHEMA.extend(UNIT_SCHEMA.schema)
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

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Found by DHCP: hostname Herpstat<model>-<MAC>, or a known MAC that got a new address."""
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        status, errors = await self._async_probe(discovery_info.ip)
        if errors and errors["base"] != "rawstatus_disabled":
            return self.async_abort(reason=errors["base"])
        if status is not None and format_mac(status.system.mac) != self.unique_id:
            return self.async_abort(reason="wrong_device")
        # status is None when /RAWSTATUS is off: the confirm form explains how to turn it on.
        return await self._async_step_discovered(discovery_info.ip, status)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """Found by mDNS (Herpstat*._http._tcp). Its MAC is only known once /RAWSTATUS answers."""
        host = discovery_info.host
        status, errors = await self._async_probe(host)
        if status is None:
            # Units with /RAWSTATUS off are still found by DHCP, which knows their MAC.
            return self.async_abort(reason=errors["base"])
        await self.async_set_unique_id(format_mac(status.system.mac))
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        return await self._async_step_discovered(host, status)

    async def _async_step_discovered(self, host: str, status: Status | None) -> ConfigFlowResult:
        self._discovered_host = host
        self._discovered_name = (status.system.nickname if status else None) or "Herpstat"
        self._rawstatus_off = status is None
        self.context["title_placeholders"] = {"name": self._discovered_name, "host": host}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            status, errors = await self._async_probe(self._discovered_host)
            if status is not None:
                if format_mac(status.system.mac) != self.unique_id:
                    return self.async_abort(reason="wrong_device")
                return self.async_create_entry(
                    title=status.system.nickname or "Herpstat",
                    data={CONF_HOST: self._discovered_host},
                    options={CONF_TEMPERATURE_UNIT: user_input[CONF_TEMPERATURE_UNIT]},
                )
        elif self._rawstatus_off:
            errors = {"base": "rawstatus_disabled"}  # say how to fix it before the first submit
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=UNIT_SCHEMA,
            description_placeholders={"name": self._discovered_name, "host": self._discovered_host},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SpyderWebOptionsFlow:
        return SpyderWebOptionsFlow()


class SpyderWebOptionsFlow(OptionsFlowWithReload):
    """Reloads the entry when options change (no update listener: HA 2026.12 rejects mixing them)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        unit = self.config_entry.options.get(CONF_TEMPERATURE_UNIT, UnitOfTemperature.FAHRENHEIT)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_TEMPERATURE_UNIT, default=unit): UNITS}),
        )
