"""Diagnostics redact identifying fields but keep the raw payload otherwise intact."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.spyderweb.diagnostics import async_get_config_entry_diagnostics

from .conftest import mock_rawstatus


async def test_diagnostics_redacts_identifiers(hass: HomeAssistant, aioclient_mock, payload, entry) -> None:
    mock_rawstatus(aioclient_mock, payload)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["data"] == {"host": "**REDACTED**"}
    assert diag["last_update_success"] is True
    system = diag["rawstatus"]["system"]
    assert system["mac"] == "**REDACTED**"
    assert system["ip"] == "**REDACTED**"
    assert system["nickname"] == "herpstat"
    assert diag["rawstatus"]["output1"]["probereadingTEMP"] == 72.0
    # Redaction must not mutate the live coordinator data.
    assert entry.runtime_data.data.raw["system"]["mac"] == "AA:BB:CC:DD:EE:FF"
