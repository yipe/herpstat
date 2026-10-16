"""Single poller shared by all entities of one Herpstat."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    SpyderWebConnectionError,
    SpyderWebInvalidResponse,
    SpyderWebRawStatusDisabled,
    Status,
    fetch_status,
)
from .const import DOMAIN, UPDATE_INTERVAL, rawstatus_issue_id

_LOGGER = logging.getLogger(__name__)

type SpyderWebConfigEntry = ConfigEntry[SpyderWebCoordinator]


class SpyderWebCoordinator(DataUpdateCoordinator[Status]):
    config_entry: SpyderWebConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SpyderWebConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.host: str = entry.data[CONF_HOST]
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> Status:
        issue_id = rawstatus_issue_id(self.config_entry.entry_id)
        placeholders = {"host": self.host}
        try:
            status = await fetch_status(self._session, self.host)
        except SpyderWebRawStatusDisabled as err:
            # Vendor firmware updates reset all settings, which turns /RAWSTATUS off again.
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="rawstatus_disabled",
                translation_placeholders=placeholders,
            )
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rawstatus_disabled",
                translation_placeholders=placeholders,
            ) from err
        except SpyderWebConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={**placeholders, "error": str(err)},
            ) from err
        except SpyderWebInvalidResponse as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="invalid_response",
                translation_placeholders={**placeholders, "error": str(err)},
            ) from err
        ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        return status
