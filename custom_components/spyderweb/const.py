"""Constants for the Herpstat SpyderWeb integration."""

from datetime import timedelta

DOMAIN = "spyderweb"

CONF_TEMPERATURE_UNIT = "temperature_unit"

# Vendor guidance: poll /RAWSTATUS no faster than every 10 s or it blocks the thermostat's control loop.
UPDATE_INTERVAL = timedelta(seconds=30)


def rawstatus_issue_id(entry_id: str) -> str:
    return f"rawstatus_disabled_{entry_id}"
