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

## Supported devices

Herpstat **SpyderWeb** models (1, 2, 4 and 6 outputs) on firmware that has the `/RAWSTATUS` page (2.7 or later;
2.8+ also reports alarm thresholds). Tested on a Herpstat 2 SpyderWeb, firmware 5.2. Other output counts and
humidity probes are handled from the payload but not yet tested on real hardware: reports welcome.
Herpstats without Wi-Fi (non-SpyderWeb) can't be supported.

## What you get

One device per Herpstat. Entity names use the output nicknames set on the device (e.g. "Lamp temperature").

| Per output | Notes |
|---|---|
| Temperature, setpoint, power % | Recorded as long-term statistics (history charts) |
| Humidity | Only if a humidity probe is connected |
| Problem | `on` when the output reports an error code; code and description in attributes |
| Mode, ramping, max power, alarm thresholds, high/low since reset | Diagnostic |
| End-of-ramp setpoint, error text, humidity max/min | Diagnostic, **disabled by default** (enable in the entity settings) |

Per device: **Safety relay tripped** (problem), relay status text, power-reset count.

**Options:** temperature unit. **Reconfigure** (device page → ⋮) changes the IP address if it moves.

## How data is updated

Home Assistant reads `/RAWSTATUS` every **30 seconds**: one small HTTP request per Herpstat. The vendor warns that
polling faster than every 10 seconds can block the thermostat's other tasks, so the interval isn't a setting.
If you need a different interval, [turn off polling for the entry and drive updates from an automation](https://www.home-assistant.io/common-tasks/general/#defining-a-custom-polling-interval),
but stay at 10 seconds or slower.

If the Herpstat can't be reached, its entities become *unavailable* and recover on the next successful update.

## Use cases

- See enclosure temperatures and heater/lamp power from anywhere, with history.
- Get a notification when a probe fails, the safety relay trips, or the thermostat drops off the network.
- Check that a day/night schedule really turns the basking lamp off at night.

## Automation examples

Notify on any problem, or when the Herpstat has been unreachable for 10 minutes:

```yaml
automation:
  - alias: Herpstat problem
    triggers:
      - trigger: state
        entity_id:
          - binary_sensor.herpstat_safety_relay_tripped
          - binary_sensor.herpstat_lamp_problem
          - binary_sensor.herpstat_heat_problem
        to: "on"
      - trigger: state
        entity_id: sensor.herpstat_lamp_temperature
        to: unavailable
        for: "00:10:00"
    actions:
      - action: notify.notify
        data:
          title: Herpstat
          message: "{{ trigger.to_state.name }}: {{ trigger.to_state.state }}"
```

Warn if the basking lamp is still powered at night, whether it never turned off when night began or came back on
later (adjust the times to your schedule; here night starts at 20:00):

```yaml
  - alias: Basking lamp on at night
    triggers:
      - trigger: time  # still on 15 minutes after night began
        at: "20:15:00"
      - trigger: numeric_state  # came back on during the night
        entity_id: sensor.herpstat_lamp_power
        above: 0
        for: "00:15:00"
    conditions:
      - condition: numeric_state
        entity_id: sensor.herpstat_lamp_power
        above: 0
      - condition: time
        after: "20:15:00"
        before: "07:45:00"
    actions:
      - action: notify.notify
        data:
          message: "Basking lamp still at {{ states('sensor.herpstat_lamp_power') }}% power."
```

Entity IDs depend on your device and output nicknames; check yours under Settings → Entities.

## Known limitations

- **Read-only.** Setpoints, schedules and modes are changed on the Herpstat itself.
- **No discovery.** The device's network name is its user-set nickname and its MAC prefix is shared by many
  ESP32 devices, so it is added by IP address.
- **Temperature unit is not reported** by the device; pick it during setup (changeable in the options).
- While the Herpstat's web configuration page is open, `/RAWSTATUS` keeps returning the last values, so readings
  look frozen until you leave it.
- Humidity entities are created when the integration loads; after plugging in a humidity probe, reload the
  integration.
- Only the live status is read; the device's own 5-minute chart history isn't imported.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Repair: "Herpstat /RAWSTATUS is turned off" (often after a firmware update resets settings) | Re-enable it on the Herpstat (see [Requirements](#requirements)); the repair clears itself on the next update |
| Entities unavailable, "Could not reach the Herpstat" | Open `http://<ip>/RAWSTATUS` in a browser. If the IP changed, use **Reconfigure**; give it a DHCP reservation |
| Readings stopped changing | Close the Herpstat's web configuration page |
| Temperatures off by a °F/°C conversion | Integration options → temperature unit must match the Herpstat's display |

For bug reports, attach **Download diagnostics** (device page → ⋮): it contains the raw `/RAWSTATUS` payload with
MAC and IP redacted.

## Removal

1. Settings → Devices & services → **Herpstat SpyderWeb (local)** → ⋮ → **Delete**.
2. Uninstall it in HACS (or delete `config/custom_components/spyderweb`), then restart Home Assistant.
3. Optionally untick **Enable /RAWSTATUS Page** in the Herpstat's Admin page.

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
