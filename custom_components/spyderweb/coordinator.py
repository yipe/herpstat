"""Single poller shared by all entities of one Herpstat."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SpyderWebError, Status, fetch_status
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, MIN_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type SpyderWebConfigEntry = ConfigEntry[SpyderWebCoordinator]


class SpyderWebCoordinator(DataUpdateCoordinator[Status]):
    config_entry: SpyderWebConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SpyderWebConfigEntry) -> None:
        seconds = max(MIN_SCAN_INTERVAL, entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=seconds),
        )
        self.host: str = entry.data[CONF_HOST]
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> Status:
        try:
            return await fetch_status(self._session, self.host)
        except SpyderWebError as err:
            raise UpdateFailed(str(err)) from err
