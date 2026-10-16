"""DHCP and zeroconf discovery.

Names come from a real unit: its router lists it as "Herpstat2-<MAC>" and it advertises
"Herpstat._http._tcp.local." over mDNS.
"""

from __future__ import annotations

import json
from ipaddress import ip_address

import aiohttp
from homeassistant.components.dhcp import WatcherBase, async_index_integration_matchers
from homeassistant.components.dhcp.models import DHCPData
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.loader import async_get_dhcp, async_get_zeroconf

from custom_components.spyderweb.const import CONF_TEMPERATURE_UNIT, DOMAIN

from .conftest import HOST, URL, mock_rawstatus

MAC = "aa:bb:cc:dd:ee:ff"
HOSTNAME = "Herpstat2-AA-BB-CC-DD-EE-FF"
NEW_HOST = "192.168.1.77"
NEW_URL = f"http://{NEW_HOST}/RAWSTATUS"
UNIT = {CONF_TEMPERATURE_UNIT: UnitOfTemperature.FAHRENHEIT}
DISABLED_501 = {"status": 501, "text": "Handler did not handle the request"}


def _dhcp(ip: str = HOST, mac: str = MAC) -> DhcpServiceInfo:
    return DhcpServiceInfo(ip=ip, hostname=HOSTNAME.lower(), macaddress=mac.replace(":", ""))


def _zeroconf(ip: str = HOST) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(ip),
        ip_addresses=[ip_address(ip)],
        port=80,
        hostname="Herpstat.local.",
        type="_http._tcp.local.",
        name="Herpstat._http._tcp.local.",
        properties={},
    )


async def _discover(hass: HomeAssistant, source: str, info):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": source}, data=info)


async def _watcher(hass: HomeAssistant) -> WatcherBase:
    """HA's real DHCP matching, fed with the matchers from every integration's manifest."""
    matchers = async_index_integration_matchers(await async_get_dhcp(hass))
    return WatcherBase(hass, DHCPData(integration_matchers=matchers))


# --- Manifest matchers, through Home Assistant's own matching code


async def test_dhcp_hostname_match_starts_discovery(hass: HomeAssistant, aioclient_mock, payload) -> None:
    mock_rawstatus(aioclient_mock, payload)
    (await _watcher(hass)).async_process_client(HOST, HOSTNAME, MAC.replace(":", ""))
    await hass.async_block_till_done(wait_background_tasks=True)  # discovery flows run as background tasks

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_DHCP
    assert flows[0]["step_id"] == "discovery_confirm"
    assert flows[0]["context"]["title_placeholders"] == {"name": "herpstat", "host": HOST}


async def test_dhcp_ignores_other_esp32_devices(hass: HomeAssistant) -> None:
    (await _watcher(hass)).async_process_client("192.168.1.50", "esp32-a1b2c3", "aabbccdd0000")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_dhcp_known_device_gets_new_ip_whatever_its_hostname(
    hass: HomeAssistant, aioclient_mock, payload, entry
) -> None:
    mock_rawstatus(aioclient_mock, payload)
    aioclient_mock.get(NEW_URL, text=json.dumps(payload))  # used by the reload after the update
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # registered_devices: matched by the device's MAC even with an unrelated hostname.
    (await _watcher(hass)).async_process_client(NEW_HOST, "unrelated-name", MAC.replace(":", ""))
    await hass.async_block_till_done(wait_background_tasks=True)  # discovery flows run as background tasks
    assert entry.data[CONF_HOST] == NEW_HOST
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_zeroconf_manifest_matches_real_instance_name(hass: HomeAssistant) -> None:
    matchers = (await async_get_zeroconf(hass))["_http._tcp.local."]
    ours = [m for m in matchers if m["domain"] == DOMAIN]
    assert ours == [{"domain": DOMAIN, "name": "herpstat*"}]
    from fnmatch import fnmatch

    # HA lowercases the instance name before matching.
    assert fnmatch("Herpstat._http._tcp.local.".lower(), ours[0]["name"])


# --- DHCP flow


async def test_dhcp_new_device_creates_entry(hass: HomeAssistant, aioclient_mock, payload) -> None:
    mock_rawstatus(aioclient_mock, payload)
    result = await _discover(hass, SOURCE_DHCP, _dhcp())
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["errors"] == {}
    assert result["description_placeholders"] == {"name": "herpstat", "host": HOST}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], UNIT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "herpstat"
    assert result["data"] == {CONF_HOST: HOST}
    assert result["options"] == UNIT
    assert result["result"].unique_id == MAC


async def test_dhcp_rawstatus_off_explains_then_recovers(
    hass: HomeAssistant, aioclient_mock, payload
) -> None:
    aioclient_mock.get(URL, **DISABLED_501)
    result = await _discover(hass, SOURCE_DHCP, _dhcp())
    assert result["step_id"] == "discovery_confirm"
    assert result["errors"] == {"base": "rawstatus_disabled"}
    assert result["description_placeholders"] == {"name": "Herpstat", "host": HOST}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], UNIT)
    assert result["errors"] == {"base": "rawstatus_disabled"}  # still off

    aioclient_mock.clear_requests()  # user turns /RAWSTATUS on
    mock_rawstatus(aioclient_mock, payload)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], UNIT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == MAC


async def test_dhcp_unreachable_aborts(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL, exc=aiohttp.ClientError())
    result = await _discover(hass, SOURCE_DHCP, _dhcp())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_dhcp_mac_mismatch_aborts(hass: HomeAssistant, aioclient_mock, payload) -> None:
    mock_rawstatus(aioclient_mock, payload)
    result = await _discover(hass, SOURCE_DHCP, _dhcp(mac="11:22:33:44:55:66"))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"


async def test_confirm_detects_device_swap(hass: HomeAssistant, aioclient_mock, payload) -> None:
    aioclient_mock.get(URL, **DISABLED_501)
    result = await _discover(hass, SOURCE_DHCP, _dhcp())
    aioclient_mock.clear_requests()  # a different unit now answers on that IP
    payload["system"]["mac"] = "11:22:33:44:55:66"
    mock_rawstatus(aioclient_mock, payload)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], UNIT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"


async def test_dhcp_known_device_updates_host(hass: HomeAssistant, entry) -> None:
    entry.add_to_hass(hass)
    result = await _discover(hass, SOURCE_DHCP, _dhcp(ip=NEW_HOST))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == NEW_HOST


# --- Zeroconf flow


async def test_zeroconf_new_device_creates_entry(hass: HomeAssistant, aioclient_mock, payload) -> None:
    mock_rawstatus(aioclient_mock, payload)
    result = await _discover(hass, SOURCE_ZEROCONF, _zeroconf())
    assert result["step_id"] == "discovery_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], UNIT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == MAC


async def test_zeroconf_known_device_updates_host(
    hass: HomeAssistant, aioclient_mock, payload, entry
) -> None:
    entry.add_to_hass(hass)
    aioclient_mock.get(NEW_URL, text=json.dumps(payload))
    result = await _discover(hass, SOURCE_ZEROCONF, _zeroconf(ip=NEW_HOST))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == NEW_HOST


async def test_zeroconf_rawstatus_off_leaves_it_to_dhcp(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL, **DISABLED_501)
    result = await _discover(hass, SOURCE_ZEROCONF, _zeroconf())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "rawstatus_disabled"


# --- Interplay


async def test_same_device_from_both_sources_shows_once(hass: HomeAssistant, aioclient_mock, payload) -> None:
    mock_rawstatus(aioclient_mock, payload)
    first = await _discover(hass, SOURCE_DHCP, _dhcp())
    assert first["type"] is FlowResultType.FORM
    second = await _discover(hass, SOURCE_ZEROCONF, _zeroconf())
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_in_progress"


async def test_manual_setup_wins_over_pending_discovery(hass: HomeAssistant, aioclient_mock, payload) -> None:
    mock_rawstatus(aioclient_mock, payload)
    await _discover(hass, SOURCE_DHCP, _dhcp())

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST, **UNIT})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []  # discovery card gone
