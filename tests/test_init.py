"""Setup, entities, failure handling, unload."""

from __future__ import annotations

from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.spyderweb.const import DOMAIN, rawstatus_issue_id

from .conftest import URL, mock_rawstatus

DISABLED_501 = {"status": 501, "text": "Handler did not handle the request"}


async def _setup(hass: HomeAssistant, entry) -> None:
    hass.config.units = US_CUSTOMARY_SYSTEM  # show native °F so assertions match the device
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities(hass: HomeAssistant, aioclient_mock, payload, entry) -> None:
    mock_rawstatus(aioclient_mock, payload)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    temp = hass.states.get("sensor.herpstat_lamp_temperature")
    assert temp.state == "72.0"
    assert temp.attributes["unit_of_measurement"] == "°F"
    assert temp.attributes["state_class"] == "measurement"  # -> recorder long-term statistics
    assert hass.states.get("sensor.herpstat_lamp_setpoint").state == "90.0"
    assert hass.states.get("sensor.herpstat_lamp_power").state == "29"
    assert hass.states.get("sensor.herpstat_heat_temperature").state == "72.9"
    assert hass.states.get("sensor.herpstat_heat_high_alarm").state == "90.0"
    assert hass.states.get("sensor.herpstat_heat_mode").state == "Heat(Dimming)"
    assert hass.states.get("sensor.herpstat_safety_relay").state == "OFF (Normal Operation)"
    assert hass.states.get("binary_sensor.herpstat_safety_relay_tripped").state == "off"
    problem = hass.states.get("binary_sensor.herpstat_lamp_problem")
    assert problem.state == "off"
    assert problem.attributes["error_description"] == "No Errors"

    # No RH probe: humidity entities are not created.
    assert hass.states.get("sensor.herpstat_lamp_humidity") is None
    # 2 system + 9 enabled per output; 1 relay + 3 per output. No internal temp on fw 5.2.
    assert len(hass.states.async_entity_ids("sensor")) == 20
    assert len(hass.states.async_entity_ids("binary_sensor")) == 7
    assert hass.states.get("sensor.herpstat_internal_temperature") is None

    ramping = hass.states.get("binary_sensor.herpstat_lamp_ramping")
    assert ramping.state == "off"
    assert ramping.attributes["status"] == "Not In Session"
    assert ramping.attributes["device_class"] == "running"
    assert hass.states.get("binary_sensor.herpstat_lamp_alarms_enabled").state == "off"
    assert hass.states.get("binary_sensor.herpstat_heat_alarms_enabled").state == "on"

    # Rarely used entities exist but are disabled by default.
    registry = er.async_get(hass)
    for object_id in ("lamp_error", "lamp_end_of_ramp_setpoint", "heat_error"):
        reg_entry = registry.async_get(f"sensor.herpstat_{object_id}")
        assert reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_humidity_entities_when_probe_present(
    hass: HomeAssistant, aioclient_mock, payload, entry
) -> None:
    payload["output2"].update(probereadingRH=55.0, probereadingRHMAX=60.0, probereadingRHMIN=40.0)
    mock_rawstatus(aioclient_mock, payload)
    await _setup(hass, entry)
    assert hass.states.get("sensor.herpstat_heat_humidity").state == "55.0"
    assert hass.states.get("sensor.herpstat_lamp_humidity") is None
    reg_entry = er.async_get(hass).async_get("sensor.herpstat_heat_humidity_max")
    assert reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_poll_failure_marks_unavailable_then_recovers(
    hass: HomeAssistant, aioclient_mock, payload, entry
) -> None:
    mock_rawstatus(aioclient_mock, payload)
    await _setup(hass, entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, exc=aiohttp.ClientError())
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.herpstat_lamp_temperature").state == STATE_UNAVAILABLE
    error = entry.runtime_data.last_exception
    assert error.translation_key == "cannot_connect"
    assert str(error).startswith(f"Could not reach the Herpstat at {entry.data['host']}: ")

    aioclient_mock.clear_requests()
    payload["output1"]["probereadingTEMP"] = 95.5
    mock_rawstatus(aioclient_mock, payload)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=62))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.herpstat_lamp_temperature").state == "95.5"


async def test_first_refresh_failure_retries(hass: HomeAssistant, aioclient_mock, entry) -> None:
    aioclient_mock.get(URL, **DISABLED_501)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert ir.async_get(hass).async_get_issue(DOMAIN, rawstatus_issue_id(entry.entry_id))


async def test_repair_issue_when_rawstatus_disabled_later(
    hass: HomeAssistant, aioclient_mock, payload, entry
) -> None:
    mock_rawstatus(aioclient_mock, payload)
    await _setup(hass, entry)
    issues = ir.async_get(hass)
    issue_id = rawstatus_issue_id(entry.entry_id)
    assert issues.async_get_issue(DOMAIN, issue_id) is None

    aioclient_mock.clear_requests()  # e.g. a firmware update reset the device's settings
    aioclient_mock.get(URL, **DISABLED_501)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    issue = issues.async_get_issue(DOMAIN, issue_id)
    assert issue.translation_key == "rawstatus_disabled"
    assert issue.severity is ir.IssueSeverity.ERROR
    assert entry.runtime_data.last_exception.translation_key == "rawstatus_disabled"

    aioclient_mock.clear_requests()  # user re-enables it: issue clears on the next poll
    mock_rawstatus(aioclient_mock, payload)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=62))
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, issue_id) is None


async def test_removing_entry_clears_issue(hass: HomeAssistant, aioclient_mock, entry) -> None:
    aioclient_mock.get(URL, **DISABLED_501)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, rawstatus_issue_id(entry.entry_id)) is None


async def test_unload(hass: HomeAssistant, aioclient_mock, payload, entry) -> None:
    mock_rawstatus(aioclient_mock, payload)
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_poll_invalid_response(hass: HomeAssistant, aioclient_mock, payload, entry) -> None:
    mock_rawstatus(aioclient_mock, payload)
    await _setup(hass, entry)

    aioclient_mock.clear_requests()  # something else answered on that IP
    aioclient_mock.get(URL, text="<html>not a herpstat</html>")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.herpstat_lamp_temperature").state == STATE_UNAVAILABLE
    assert entry.runtime_data.last_exception.translation_key == "invalid_response"


async def test_ramping_and_internal_temperature(hass: HomeAssistant, aioclient_mock, payload, entry) -> None:
    payload["output1"]["ramping"] = "In Session"
    payload["system"].update(internaltemp=78.5, internaltempmax=80.1)
    mock_rawstatus(aioclient_mock, payload)
    await _setup(hass, entry)
    assert hass.states.get("binary_sensor.herpstat_lamp_ramping").state == "on"
    internal = hass.states.get("sensor.herpstat_internal_temperature")
    assert internal.state == "78.5"
    assert internal.attributes["unit_of_measurement"] == "°F"
    assert hass.states.get("sensor.herpstat_internal_temperature_max").state == "80.1"
