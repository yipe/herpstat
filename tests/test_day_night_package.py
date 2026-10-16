"""Run packages/herpstat_day_night.yaml in a real HA and simulate two days and a night."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import async_fire_time_changed

PACKAGE = Path(__file__).parents[1] / "examples" / "packages" / "herpstat_day_night.yaml"
LAMP = "sensor.herpstat_lamp_temperature"
HEATER = "sensor.herpstat_heat_temperature"


async def _at(hass: HomeAssistant, freezer, when: datetime, **readings: float | str) -> None:
    freezer.move_to(when)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    for key, entity_id in (("lamp", LAMP), ("heater", HEATER)):
        if key in readings:
            hass.states.async_set(entity_id, readings[key], {"unit_of_measurement": "°F"})
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, object_id: str) -> str:
    return hass.states.get(f"sensor.herpstat_{object_id}").state


# The package's 08:00/20:00 time triggers stay scheduled after the test; that is expected.
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_day_highs_night_lows_and_averages(hass: HomeAssistant, freezer, caplog) -> None:
    hass.config.units = US_CUSTOMARY_SYSTEM  # matches the real HA (°F)
    tz = dt_util.get_time_zone(hass.config.time_zone)

    def t(day: int, hh: int, mm: int = 0) -> datetime:
        return datetime(2026, 10, day, hh, mm, tzinfo=tz)

    freezer.move_to(t(15, 7))
    hass.states.async_set(LAMP, 72.0, {"unit_of_measurement": "°F"})
    hass.states.async_set(HEATER, 70.0, {"unit_of_measurement": "°F"})
    config = yaml.safe_load(PACKAGE.read_text())
    assert await async_setup_component(hass, "template", {"template": config["template"]})
    await hass.async_block_till_done()

    # ---- Day 1 (08:00-20:00)
    await _at(hass, freezer, t(15, 8))  # day_start resets to current readings
    assert _state(hass, "lamp_day_high_running") == "72.0"
    assert _state(hass, "heater_day_high_running") == "70.0"
    await _at(hass, freezer, t(15, 9), lamp=104.0, heater=74.0)
    await _at(hass, freezer, t(15, 12), lamp=106.5, heater=76.0)
    await _at(hass, freezer, t(15, 15), lamp=103.0, heater=75.0)
    assert _state(hass, "lamp_day_high_running") == "106.5"
    assert _state(hass, "heater_day_high_running") == "76.0"
    # Night window is untouched during the day.
    assert _state(hass, "lamp_night_low_running") == "unknown"

    await _at(hass, freezer, t(15, 20))  # finalize day 1, start night 1
    assert _state(hass, "lamp_day_high") == "106.5"
    assert _state(hass, "heater_day_high") == "76.0"
    assert _state(hass, "lamp_day_high_7_day_average") == "106.5"
    assert _state(hass, "lamp_night_low_running") == "103.0"
    assert _state(hass, "heater_night_low_running") == "75.0"

    # ---- Night 1 (20:00-08:00, crosses midnight)
    await _at(hass, freezer, t(15, 22), lamp=75.0, heater=71.0)
    await _at(hass, freezer, t(16, 3), lamp=68.0, heater=69.5)
    await _at(hass, freezer, t(16, 7), lamp=70.0, heater=70.0)
    # Day running max ignores night readings.
    assert _state(hass, "lamp_day_high_running") == "106.5"

    await _at(hass, freezer, t(16, 8))  # finalize night 1, start day 2
    assert _state(hass, "lamp_night_low") == "68.0"
    assert _state(hass, "heater_night_low") == "69.5"
    assert _state(hass, "heater_night_low_7_day_average") == "69.5"
    assert _state(hass, "lamp_day_high_running") == "70.0"

    # ---- Day 2, with a dropout: unavailable readings must not reset or poison the max.
    await _at(hass, freezer, t(16, 12), lamp=103.5, heater=77.0)
    await _at(hass, freezer, t(16, 13), lamp="unavailable", heater="unavailable")
    assert _state(hass, "lamp_day_high_running") == "103.5"
    await _at(hass, freezer, t(16, 20))
    assert _state(hass, "lamp_day_high") == "103.5"
    assert _state(hass, "lamp_day_high_7_day_average") == "105.0"  # (106.5 + 103.5) / 2
    assert _state(hass, "heater_day_high_7_day_average") == "76.5"  # (76 + 77) / 2
    avg = hass.states.get("sensor.herpstat_lamp_day_high_7_day_average")
    assert avg.attributes["values"] == [106.5, 103.5]
    assert avg.attributes["state_class"] == "measurement"

    assert "Error" not in caplog.text, caplog.text


# The package's 08:00/20:00 time triggers stay scheduled after the test; that is expected.
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_average_keeps_only_last_seven(hass: HomeAssistant, freezer) -> None:
    hass.config.units = US_CUSTOMARY_SYSTEM  # matches the real HA (°F)
    tz = dt_util.get_time_zone(hass.config.time_zone)
    freezer.move_to(datetime(2026, 10, 1, 7, tzinfo=tz))
    hass.states.async_set(LAMP, 100.0, {"unit_of_measurement": "°F"})
    hass.states.async_set(HEATER, 70.0, {"unit_of_measurement": "°F"})
    config = yaml.safe_load(PACKAGE.read_text())
    assert await async_setup_component(hass, "template", {"template": config["template"]})
    await hass.async_block_till_done()

    for day in range(1, 10):  # nine days, highs 101..109
        await _at(hass, freezer, datetime(2026, 10, day, 8, tzinfo=tz))
        await _at(hass, freezer, datetime(2026, 10, day, 12, tzinfo=tz), lamp=100.0 + day)
        await _at(hass, freezer, datetime(2026, 10, day, 20, tzinfo=tz), lamp=95.0)

    avg = hass.states.get("sensor.herpstat_lamp_day_high_7_day_average")
    assert avg.attributes["values"] == [103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
    assert avg.state == "106.0"
