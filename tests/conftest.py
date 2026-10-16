"""Shared fixtures. tests/fixtures/rawstatus.json is a real capture from the 2-output unit (fw 5.2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from homeassistant.const import CONF_HOST, UnitOfTemperature
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.spyderweb.const import CONF_TEMPERATURE_UNIT, DOMAIN

HOST = "192.168.1.233"
URL = f"http://{HOST}/RAWSTATUS"
FIXTURE = Path(__file__).parent / "fixtures" / "rawstatus.json"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture
def payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


def mock_rawstatus(aioclient_mock: AiohttpClientMocker, payload: dict[str, Any]) -> None:
    # The device serves JSON as text/html.
    aioclient_mock.get(URL, text=json.dumps(payload), headers={"Content-Type": "text/html"})


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="herpstat",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={CONF_HOST: HOST},
        options={CONF_TEMPERATURE_UNIT: UnitOfTemperature.FAHRENHEIT},
    )
