<p align="center">
  <img src="https://raw.githubusercontent.com/yipe/herpstat/main/custom_components/spyderweb/brand/icon.png" alt="" width="96">
</p>

# Herpstat SpyderWeb for Home Assistant (local)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Validate](https://github.com/yipe/herpstat/actions/workflows/validate.yml/badge.svg)](https://github.com/yipe/herpstat/actions/workflows/validate.yml)
[![Home Assistant 2025.8+](https://img.shields.io/badge/Home%20Assistant-2025.8%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/yipe/herpstat/blob/main/LICENSE)

Your Herpstat keeps your reptile warm. This integration makes sure you know it's actually doing that.

It brings a [Spyder Robotics](https://spyderrobotics.com/) **Herpstat SpyderWeb** thermostat into Home Assistant, so
you can see every enclosure's temperatures at a glance, keep their history, and get a notification the moment
something goes wrong. It talks to the thermostat directly over your home network. There's no cloud account, no YAML,
and it never changes a setting: the Herpstat keeps running exactly as you configured it.

![Example dashboard showing basking lamp and heater temperatures, power gauges and charts](docs/images/dashboard.png)
<sub>The [example dashboard](examples/dashboard.yaml) on its first day.</sub>

> Unofficial. Not affiliated with or endorsed by Spyder Robotics. "Herpstat" and "SpyderWeb" are their trademarks.

**Contents:** [Why you'd want it](#why-youd-want-it) · [Getting started](#getting-started) ·
[What you'll see](#what-youll-see) · [Automation ideas](#automation-ideas) · [How it works](#how-it-works) ·
[Supported devices](#supported-devices) · [Limitations](#known-limitations) · [Troubleshooting](#troubleshooting) ·
[Removal](#removal) · [Contributing](#contributing)

## Why you'd want it

**Find out about problems before your animal does.** A probe that falls out or fails, a safety relay that cuts
power to every outlet, a thermostat that drops off Wi-Fi: each one becomes a Home Assistant alert you can send to
your phone. Add your own temperature alerts on top if you like.

**Catch the basking lamp that never turns off.** A schedule that looks right on the thermostat can still leave a
lamp burning all night. Home Assistant records the lamp's power, so you can see it, or get a notification when it
happens (there's a ready-made automation below).

**See the whole day, not the last few minutes.** The Herpstat's built-in chart only covers its last 100 readings.
Home Assistant keeps every reading for days and hourly and daily summaries for good, so you can compare day highs
and night lows, see how long the lamp takes to warm up, and tune your setpoints with real numbers.

**Set it up in a minute and forget about it.** Home Assistant finds the thermostat on its own, and follows it when
the router hands it a new IP address. Everything is configured from the UI.

**It can't make things worse.** It only reads. If Home Assistant goes down, your Herpstat carries on heating
exactly as before.

## Getting started

### Before you start

- Home Assistant 2025.8 or newer.
- On the Herpstat, turn on the status page this integration reads. Open the Herpstat's web page, go to **Admin**,
  tick **Show Advanced Status Integration Options**, then **Enable /RAWSTATUS Page**, and click **Submit**.
  To check it worked, open `http://<herpstat-ip>/RAWSTATUS` in a browser: you should see a block of JSON.

### Install

**With HACS** (recommended, so you hear about updates). If you don't have HACS yet, follow its
[setup guide](https://hacs.xyz/docs/use/) first: download it, restart, then add the **HACS** integration and link
it to GitHub.

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=yipe&repository=herpstat&category=integration)

1. Use the button above: it adds this repository to HACS and opens it. Or add it by hand: HACS → ⋮ →
   **Custom repositories** → `https://github.com/yipe/herpstat`, type *Integration*.
2. On the repository page, click **Download**, then restart Home Assistant.

If HACS says *"Repository 'yipe/herpstat' exists in the store"*, it's already added: search for **Herpstat** in
HACS and download it from there.

**Without HACS:** copy `custom_components/spyderweb` into your `config/custom_components/` folder and restart.

### Add your Herpstat

Usually there's nothing to type. Home Assistant finds the Herpstat by itself and shows it under Settings → Devices &
services → **Discovered**. That can take up to an hour, or until the Herpstat reconnects to Wi-Fi; a restart of
Home Assistant often speeds it up. Click **Add** and pick the temperature unit your Herpstat displays.

If it doesn't show up, add it by IP address:

[![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=spyderweb)

or Settings → Devices & services → **Add integration** → *Herpstat SpyderWeb (local)*.

You don't need to give the Herpstat a fixed IP address: when it gets a new one, Home Assistant notices and updates
the integration by itself.

## What you'll see

Each Herpstat becomes one device in Home Assistant. Its entities are named after the output nicknames you set on
the thermostat, so you'll see things like "Lamp temperature" and "Heat power".

**For each output**

- **Temperature, target and power.** The numbers you'll look at most, all kept as long-term history for charts.
- **Humidity**, if a humidity probe is plugged in.
- **Problem**, which turns on when the output reports an error such as a missing probe. The error code and
  description are in its attributes, ready for a notification.
- **Ramping**, on while the thermostat is moving between day and night temperatures.
- **Alarms enabled**, plus the high and low alarm thresholds.
- **Diagnostics:** mode, maximum power, and the high and low temperatures since the last reset. A few rarely used
  ones (end-of-ramp target, error text, humidity high/low) are switched off by default; turn them on in the entity
  settings if you want them.

**For the thermostat**

- **Safety relay tripped**: on means the Herpstat has cut power to all outlets.
- Relay status text, a power-reset counter (how often it has restarted after losing power), and the internal temperature on models that report it.

**Settings:** the temperature unit, under the integration's **Configure** button. If you ever need to point it at
a different address, use **Reconfigure** on the device page.

## Automation ideas

Paste these into your `automations.yaml`, or recreate them in the automation editor. Check your entity IDs under
Settings → Entities first; they depend on your device and output names.

**Tell me if anything's wrong**, including the thermostat being unreachable for 10 minutes:

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

**Warn me if the basking lamp is on at night**, whether it never switched off or came back on later. Adjust the
times to your schedule; here night starts at 20:00:

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

**More in [`examples/`](https://github.com/yipe/herpstat/tree/main/examples):**

- [`dashboard.yaml`](examples/dashboard.yaml) is the dashboard in the screenshot: current readings, alerts that
  only appear when needed, 24-hour charts and longer trends.
- [`packages/herpstat_day_night.yaml`](examples/packages/herpstat_day_night.yaml) records each day's high
  (8 AM–8 PM) and each night's low (8 PM–8 AM), with 7-day averages.

Both assume a device named `herpstat` with outputs called `Lamp` and `Heat`; adjust the names to match yours.

## How it works

Every 30 seconds, Home Assistant reads the Herpstat's `/RAWSTATUS` page: one small request over your local network.
The manufacturer warns that asking more often than every 10 seconds can get in the way of the thermostat's own
work, so the interval is fixed. If you really need a different one, you can
[turn off polling and trigger updates from an automation](https://www.home-assistant.io/common-tasks/general/#defining-a-custom-polling-interval);
please stay at 10 seconds or slower.

The thermostat occasionally cuts a reply short, so a garbled reply is retried once before an update counts as
failed. If the Herpstat can't be reached, its entities show as *unavailable* and come back on their own.

## Supported devices

Herpstat **SpyderWeb** models with 1, 2, 4 or 6 outputs, on firmware that has the `/RAWSTATUS` page (2.7 or later;
2.8 and later also report alarm thresholds). It's tested on a Herpstat 2 SpyderWeb with firmware 5.2. Other models
and humidity probes should work, but haven't been tried on real hardware yet. If you have one, please report how it
goes. Herpstats without Wi-Fi (the non-SpyderWeb models) can't be supported.

## Known limitations

- **It's read-only.** Change setpoints, schedules and modes on the Herpstat itself.
- **Discovery and IP tracking need Home Assistant to see the Herpstat's network traffic.** That means the same
  network or VLAN, and host networking if you run Home Assistant in Docker. If that isn't possible, add it by IP
  address and give it a fixed IP. Discovery looks for the names a Herpstat 2 (firmware 5.2) uses: the DHCP hostname
  `Herpstat2-<MAC>` and the mDNS service `Herpstat`.
- **The thermostat doesn't report its temperature unit**, so you choose it during setup (you can change it later).
- **While the Herpstat's own web settings page is open**, it keeps reporting the last values, so readings look
  frozen until you leave that page.
- **A newly plugged-in humidity probe** shows up after you reload the integration.
- **Only live readings are imported**, not the thermostat's own short chart history.

## Troubleshooting

| What you see | What to do |
|---|---|
| A repair: "Herpstat /RAWSTATUS is turned off". This often happens after a firmware update resets the settings | Turn the status page back on (see [Before you start](#before-you-start)). The repair clears itself on the next update |
| Entities unavailable, "Could not reach the Herpstat" | Open `http://<ip>/RAWSTATUS` in a browser. A new IP is normally picked up by itself within the hour; to fix it now, use **Reconfigure** |
| Readings stopped changing | Close the Herpstat's web settings page |
| Temperatures look converted wrongly between °F and °C | Integration → **Configure**: the unit must match the Herpstat's display |

If you report a bug, please attach **Download diagnostics** from the device page (⋮ menu). It includes the raw
`/RAWSTATUS` reading, with the MAC and IP addresses removed.

## Removal

1. Settings → Devices & services → **Herpstat SpyderWeb (local)** → ⋮ → **Delete**.
2. Uninstall it in HACS (or delete `config/custom_components/spyderweb`), then restart Home Assistant.
3. Optionally, untick **Enable /RAWSTATUS Page** in the Herpstat's Admin page.

## Contributing

Issues and pull requests are welcome.

- **Bugs:** use the [bug report form](https://github.com/yipe/herpstat/issues/new/choose) and attach the
  diagnostics download described above.
- **Most wanted:** readings from setups that haven't been tested yet: Herpstat 1, 4 or 6 SpyderWeb, humidity
  probes, other firmware versions, and what the `ramping` field says while a ramp is running.

## License

[MIT](https://github.com/yipe/herpstat/blob/main/LICENSE)
