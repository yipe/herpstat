"""Setup, entities, failure handling, unload."""

from __future__ import annotations

from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import URL, mock_rawstatus


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
    # 2 system + 12 per output; 1 relay + 1 per output.
    assert len(hass.states.async_entity_ids("sensor")) == 26
    assert len(hass.states.async_entity_ids("binary_sensor")) == 3


async def test_humidity_entities_when_probe_present(
    hass: HomeAssistant, aioclient_mock, payload, entry
) -> None:
    payload["output2"].update(probereadingRH=55.0, probereadingRHMAX=60.0, probereadingRHMIN=40.0)
    mock_rawstatus(aioclient_mock, payload)
    await _setup(hass, entry)
    assert hass.states.get("sensor.herpstat_heat_humidity").state == "55.0"
    assert hass.states.get("sensor.herpstat_lamp_humidity") is None


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

    aioclient_mock.clear_requests()
    payload["output1"]["probereadingTEMP"] = 95.5
    mock_rawstatus(aioclient_mock, payload)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=62))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.herpstat_lamp_temperature").state == "95.5"


async def test_first_refresh_failure_retries(hass: HomeAssistant, aioclient_mock, entry) -> None:
    aioclient_mock.get(URL, status=501, text="Handler did not handle the request")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(hass: HomeAssistant, aioclient_mock, payload, entry) -> None:
    mock_rawstatus(aioclient_mock, payload)
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
