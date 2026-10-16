"""Parser and HTTP error mapping."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.spyderweb.api import (
    SpyderWebConnectionError,
    SpyderWebInvalidResponse,
    SpyderWebRawStatusDisabled,
    fetch_status,
    parse_status,
)

from .conftest import HOST, URL, mock_rawstatus


def test_parse_real_payload(payload) -> None:
    status = parse_status(payload)
    assert status.system.mac == "AA:BB:CC:DD:EE:FF"
    assert status.system.firmware == "5.2"
    assert status.system.power_resets == 1
    assert not status.system.safety_relay_tripped
    assert list(status.outputs) == [1, 2]
    lamp, heat = status.outputs[1], status.outputs[2]
    assert (lamp.nickname, lamp.temperature, lamp.setpoint, lamp.power) == ("Lamp", 72.0, 90.0, 29)
    assert lamp.mode == "Heat(Dimming)"
    assert lamp.alarm_enabled is False
    assert heat.alarm_enabled is True
    assert (heat.high_alarm, heat.low_alarm) == (90.0, 65.0)
    assert not lamp.has_humidity
    assert not lamp.has_error


@pytest.mark.parametrize(
    ("text", "tripped"),
    [("OFF (Normal Operation)", False), ("off", False), ("ON (Shutdown)", True), (None, False)],
)
def test_safety_relay(payload, text, tripped) -> None:
    payload["system"]["safetyrelay"] = text
    assert parse_status(payload).system.safety_relay_tripped is tripped


def test_odd_types_and_extra_outputs(payload) -> None:
    out = payload["output1"]
    out["probereadingTEMP"] = "74.5"
    out["poweroutput"] = "55"
    out["currentsetting"] = ""
    out["probereadingRH"] = 41.0
    out["errorcode"] = 3
    payload["output3"] = dict(payload["output2"], outputnickname="")
    payload["output9"] = "garbage"
    status = parse_status(payload)
    lamp = status.outputs[1]
    assert (lamp.temperature, lamp.power, lamp.setpoint) == (74.5, 55, None)
    assert lamp.has_humidity
    assert lamp.has_error
    assert list(status.outputs) == [1, 2, 3]
    assert status.outputs[3].nickname == "Output 3"


@pytest.mark.parametrize("bad", [None, [], {}, {"system": {}}, {"system": {"mac": ""}}])
def test_invalid_payloads(bad) -> None:
    with pytest.raises(SpyderWebInvalidResponse):
        parse_status(bad)


async def test_fetch_ok(hass: HomeAssistant, aioclient_mock, payload) -> None:
    mock_rawstatus(aioclient_mock, payload)
    status = await fetch_status(async_get_clientsession(hass), HOST)
    assert status.outputs[2].nickname == "Heat"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"status": 501, "text": "Handler did not handle the request"}, SpyderWebRawStatusDisabled),
        ({"status": 500, "text": "boom"}, SpyderWebInvalidResponse),
        ({"text": "<html>login</html>"}, SpyderWebInvalidResponse),
        ({"exc": aiohttp.ClientError()}, SpyderWebConnectionError),
        ({"exc": TimeoutError()}, SpyderWebConnectionError),
    ],
)
async def test_fetch_errors(hass: HomeAssistant, aioclient_mock, kwargs, error) -> None:
    aioclient_mock.get(URL, **kwargs)
    with pytest.raises(error):
        await fetch_status(async_get_clientsession(hass), HOST)
