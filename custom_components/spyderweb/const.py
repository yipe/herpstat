"""Constants for the Herpstat SpyderWeb integration."""

DOMAIN = "spyderweb"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_TEMPERATURE_UNIT = "temperature_unit"

DEFAULT_SCAN_INTERVAL = 30
# Vendor guidance: poll /RAWSTATUS no faster than every 10 s or it blocks the control loop.
MIN_SCAN_INTERVAL = 10
