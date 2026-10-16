# Herpstat SpyderWeb for Home Assistant (local)

Read-only Home Assistant integration for [Spyder Robotics](https://spyderrobotics.com/) **Herpstat SpyderWeb**
reptile thermostats. It polls the thermostat's local `/RAWSTATUS` JSON page over your LAN: no cloud, no login,
and it never changes a setting.

> Unofficial. Not affiliated with or endorsed by Spyder Robotics. "Herpstat" and "SpyderWeb" are their trademarks.

The thermostat keeps regulating on its own. Home Assistant only watches it, so an outage here never affects heating.

## Requirements

- Home Assistant 2025.8 or newer.
- A Herpstat SpyderWeb with **`/RAWSTATUS` enabled**: on the Herpstat's web page go to **Admin**, tick
  **Show Advanced Status Integration Options**, then **Enable /RAWSTATUS Page**, and **Submit**.
  Check it works: `http://<herpstat-ip>/RAWSTATUS` should show JSON.
- A fixed IP for the Herpstat (a DHCP reservation on your router) is recommended.

Tested on a Herpstat 2 SpyderWeb, firmware 5.2. Other output counts (1/2/4/6) and humidity probes are handled
from the payload but not yet tested on real hardware. Reports welcome.

## Install

**HACS:** HACS → ⋮ → Custom repositories → add `https://github.com/yipe/ha-spyderweb`, type *Integration*.
Install **Herpstat SpyderWeb (local)**, then restart Home Assistant.

**Manual:** copy `custom_components/spyderweb` into your `config/custom_components/` folder and restart.

Then: Settings → Devices & services → **Add integration** → *Herpstat SpyderWeb (local)* → enter the IP address
and the temperature unit your Herpstat displays (the device doesn't report it).

## What you get

One device per Herpstat. Entity names use the output nicknames set on the device (e.g. "Lamp", "Heat").

| Per output | Notes |
|---|---|
| Temperature, setpoint, power % | Recorded as long-term statistics (history charts) |
| Humidity | Only if a humidity probe is connected |
| Problem | `on` when the output reports an error code; description in attributes |
| Mode, ramping, max power, alarm thresholds, high/low since reset, end-of-ramp setpoint, error text | Diagnostic |

Per device: **Safety relay tripped** (problem), relay status text, power-reset count.

**Options:** poll interval (default 30 s, minimum 10 s: the vendor warns faster polling of `/RAWSTATUS` can block
the thermostat's other tasks) and temperature unit. **Reconfigure** changes the IP address if it moves.

## Good to know

- While the Herpstat's web configuration page is open, `/RAWSTATUS` keeps returning the
  last values, so readings look frozen until you exit the menu.
- Humidity entities are created when the integration loads; after plugging in a humidity probe, reload the
  integration.
- **Download diagnostics** (device page → ⋮) includes the raw `/RAWSTATUS` payload with MAC and IP redacted:
  please attach it to bug reports.

## Examples

- [`examples/dashboard.yaml`](examples/dashboard.yaml): a sections dashboard (current readings, alerts, 24 h
  charts, trends). Entity IDs assume a device named `herpstat` with outputs `Lamp` and `Heat`; adjust to yours.
- [`examples/packages/herpstat_day_night.yaml`](examples/packages/herpstat_day_night.yaml): template sensors for
  each day's high (8 AM–8 PM), each night's low (8 PM–8 AM) and their 7-day averages.

## Development

```sh
uv sync                      # Python 3.13, pinned to Home Assistant 2025.8.3 test harness
uv run pytest
uv run --with ruff ruff check . && uv run --with ruff ruff format --check .
```

[`docs/API.md`](docs/API.md) documents the device's HTTP interface as reverse-engineered, and
[`tools/herpstat_client.py`](tools/herpstat_client.py) is a stdlib-only read-only client for it (including the
login-protected 5-minute history).

## License

[MIT](LICENSE)
