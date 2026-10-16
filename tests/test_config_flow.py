"""Config and options flows."""

from __future__ import annotations

import json

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.spyderweb.config_flow import normalize_host
from custom_components.spyderweb.const import CONF_TEMPERATURE_UNIT, DOMAIN

from .conftest import HOST, URL, mock_rawstatus

USER_INPUT = {CONF_HOST: f" {HOST} ", CONF_TEMPERATURE_UNIT: UnitOfTemperature.FAHRENHEIT}


async def _start(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return result


async def test_user_flow_creates_entry(hass: HomeAssistant, aioclient_mock, payload) -> None:
    mock_rawstatus(aioclient_mock, payload)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "herpstat"
    assert result["data"] == {CONF_HOST: HOST}
    assert result["options"] == {CONF_TEMPERATURE_UNIT: UnitOfTemperature.FAHRENHEIT}
    assert result["result"].unique_id == "aa:bb:cc:dd:ee:ff"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"status": 501, "text": "Handler did not handle the request"}, "rawstatus_disabled"),
        ({"exc": aiohttp.ClientError()}, "cannot_connect"),
        ({"text": "not json"}, "invalid_response"),
    ],
)
async def test_user_flow_errors(hass: HomeAssistant, aioclient_mock, kwargs, error) -> None:
    aioclient_mock.get(URL, **kwargs)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_user_flow_recovers_after_error(hass: HomeAssistant, aioclient_mock, payload) -> None:
    aioclient_mock.get(URL, status=501, text="Handler did not handle the request")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "rawstatus_disabled"}

    aioclient_mock.clear_requests()  # user enables /RAWSTATUS and submits again
    mock_rawstatus(aioclient_mock, payload)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_updates_host(hass: HomeAssistant, aioclient_mock, payload, entry) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, data={CONF_HOST: "10.0.0.9"})
    mock_rawstatus(aioclient_mock, payload)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == HOST


async def test_options_flow_changes_unit(hass: HomeAssistant, aioclient_mock, payload, entry) -> None:
    hass.config.units = US_CUSTOMARY_SYSTEM
    mock_rawstatus(aioclient_mock, payload)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert list(result["data_schema"].schema) == [CONF_TEMPERATURE_UNIT]  # no polling field
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TEMPERATURE_UNIT: UnitOfTemperature.CELSIUS}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_TEMPERATURE_UNIT: UnitOfTemperature.CELSIUS}
    # Reloaded: 72.0 is now read as °C and shown in the system's °F.
    assert hass.states.get("sensor.herpstat_lamp_temperature").state == "161.6"


@pytest.mark.parametrize(
    ("raw", "host"),
    [
        (" 192.168.1.5 ", "192.168.1.5"),
        ("http://192.168.1.5", "192.168.1.5"),
        ("HTTP://192.168.1.5/RAWSTATUS", "192.168.1.5"),
        ("herpstat.local/", "herpstat.local"),
        ("192.168.1.5:80", "192.168.1.5:80"),
    ],
)
def test_normalize_host(raw: str, host: str) -> None:
    assert normalize_host(raw) == host


NEW_HOST = "192.168.1.77"
NEW_URL = f"http://{NEW_HOST}/RAWSTATUS"


async def test_reconfigure_updates_host(hass: HomeAssistant, aioclient_mock, payload, entry) -> None:
    entry.add_to_hass(hass)
    mock_rawstatus(aioclient_mock, payload)  # old host, used by the reload after updating
    aioclient_mock.get(NEW_URL, text=json.dumps(payload))
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: f"http://{NEW_HOST}/"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == NEW_HOST


async def test_reconfigure_rejects_other_device(hass: HomeAssistant, aioclient_mock, payload, entry) -> None:
    entry.add_to_hass(hass)
    payload["system"]["mac"] = "11:22:33:44:55:66"
    aioclient_mock.get(NEW_URL, text=json.dumps(payload))
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: NEW_HOST})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_HOST] == HOST


async def test_reconfigure_unreachable_shows_error(hass: HomeAssistant, aioclient_mock, entry) -> None:
    entry.add_to_hass(hass)
    aioclient_mock.get(NEW_URL, exc=aiohttp.ClientError())
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: NEW_HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data[CONF_HOST] == HOST
