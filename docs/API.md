# Herpstat SpyderWeb HTTP API (reverse-engineered)

Device: Herpstat 2 SpyderWeb, firmware 5.2, `herpstat.local`, MAC `AA:BB:CC:DD:EE:FF`.
Server: ESP32 Arduino `WebServer`. Plain HTTP, `Connection: close`. Answers in 50–270 ms.
Only TCP/80 is open (scanned 1–1024 plus 1883, 3232, 5000, 6053, 8000, 8080, 8081, 8266, 8443, 8883, 8888, 9000).
Closed ports drop connections silently rather than sending a reset. mDNS advertises `Herpstat._http._tcp` with no TXT
records and no `_arduino._tcp` OTA service.

**Prefer the IP address over `herpstat.local`.** The ESP32 doesn't answer mDNS AAAA queries. On macOS, dual-stack
lookups stalled for 5.0 s on every request; an IPv4-only lookup took 0.29 s cold (`socket.gethostbyname`).
Resolve once and cache, or give the device a DHCP reservation.

**Poll at most once every 10 s.** The device's Admin help text says: "Polling this page should be limited to intervals
of 10 seconds or greater to prevent blocking other tasks". The web server shares the control loop.
Faster polling isn't rejected (5 requests 1 s apart all returned 200), but it can delay regulation.

Reference client: `tools/herpstat_client.py` (read-only, stdlib only).

## Auth

| Step | Request | Result |
|---|---|---|
| 1 | `GET /` | Login page. Sets cookie `Herpstat_<MAC>=0`. |
| 2 | `POST /checkpassword` form `PASSWORD=<pw>&SUBMIT=Submit` | `301 Location: /STATUSPAGE` and `Set-Cookie: Herpstat_<MAC>=<token>` |

- Session state is the cookie only. Send `Cookie: Herpstat_AA:BB:CC:DD:EE:FF=<token>`.
- A request with no cookie header gets `501 "Handler did not handle the request"` on every gated route.
- With cookie `=0` (or an invalid token):
  - Page routes return `301 → /`.
  - `/GETHERPSTATWEBDATA` returns 200 with a "Browser error. Please Log In" fragment.
- **LOGOUT is just `href='/'`.** Hitting `/` resets the cookie to `0`, so don't poll `/`.
- A client should log in at startup, and log in again whenever it gets `301` or "Please Log In".

## Routing behaviour

- There is no not-found handler. Every unknown path returns `501 "Handler did not handle the request"`.
- Paths are case-sensitive (`/getherpstatwebdata` → 501). Query strings are ignored.
- `HEAD` and `OPTIONS` return 501, so there is no CORS preflight. Combined with `ACAO: *` (which can't be used with
  credentials), **a browser on another origin can't send the session cookie. A backend proxy is required.**
- Captive-portal routes, used in AP setup mode: `/generate_204` and `/hotspot-detect.html` → `302 /`.
- Probed with cookie `=0` and found nothing: `/STATUS /status /json /JSON /data /RAWDATA /RAWCHARTS
  /GETHERPSTATCHARTDATA /GETHERPSTATWEBCHARTS /handlewebstatus /handlewebdata /handleStatus /web_status
  /web_output1 /web_output /web_system /web_wifi /web_info /info /version /wizard /setupwizard /favicon.ico /robots.txt`.

## Read endpoints (verified live)

### `GET /GETHERPSTATWEBDATA`: live status (HTML fragment)
`/STATUSPAGE` is only a shell that XHR-polls this every 5 s and injects the HTML.
Sends `Access-Control-Allow-Origin: *`.
It is a `<table>`: one `<td>` for the system, then one `<td>` per output, with lines separated by `<br>`.

System cell:
```
Device Nickname: herpstat
IP Address: 192.168.1.233
MAC: AA:BB:CC:DD:EE:FF
Firmware Version: 5.2
Device Clock: 09:15:39 A          <- firmware truncates AM/PM to A/P; NTP-synced (matched host clock to within 1 s)
Power Resets: 1
Safety Relay Status=OFF  (Normal Operation)
```
Output cell (`Output #<n> <nickname>`):
```
Mode: Heat (Dimming) Basking Assist & PS
Temp: 71.2            Setting: 90.0
High Temp: 71.2       Low Temp: 66.6      <- since last High/Low reset
Power: 100%
High/Low Alarm: Enabled|Disabled
High Alarm Setting: 90.0   Low Alarm Setting: 65.0   <- only when the alarm is enabled
Probe Error Status= Normal
```
Lines appear and disappear depending on mode, so parse them as generic `key[:=]value` pairs.
Humidity outputs probably add RH lines (unverified: no RH probe here). Units follow the device display setting (°F here).

### `GET /handlewebcharts`: history (HTML + inline Google Charts JS)
Each output has one `google.visualization.arrayToDataTable([...])` literal:
```
[['Time','Temp1','Power1'], ['09:09:45 AM',70.9,100], ...]   // 100 rows
var options = {title: 'SpyderWeb Output #1 Lamp', ...}
... Lowest Temp Recorded: 70.9<br>Highest Temp Recorded: 71.1
```
- Up to 100 points. Their span comes from the device's GraphPeriod setting (currently `5 minutes`).
- **Saving settings resets the history.** After an output config change at ~11:23 the arrays held 32 points.
  While partly filled, each array ends with a trailing comma (`...,['11:24:05 AM',93.2,86],]`): valid JS, invalid JSON.
  Strip `,]` before parsing.
- Measured cadence over 299 s: 3 s ×93, 4 s ×4, 2 s ×2.
- The header text gives the span: `100 data points over last 5 minutes`.
- Timestamps are wall-clock strings only (no date).
- "Lowest/Highest Temp Recorded" is the min/max of those 100 points (verified). It is not the status High/Low,
  which runs since the last reset.
- The page reloads itself every 60 s.
- **For longer history the UI has to record it itself.** Poll `/GETHERPSTATWEBDATA`, or merge chart windows by timestamp.

### `GET /RAWSTATUS`: JSON status (no auth; verified live)
- Turned on via Admin → "Show Advanced Status Integration Options" → "Enable /RAWSTATUS Page" (`FORMENABLERAWSTATUS`).
  Returns 501 when off.
- **No cookie needed.** Sends `Access-Control-Allow-Origin: *`, so a browser can `fetch()` it directly.
  The content type is mislabelled `text/html`, so parse it as JSON yourself. About 1 KB, 0.1–0.5 s.
- This is the preferred source for live data. Use the HTML routes only for history.

```json
{"system":{"mac":"AA:BB:CC:DD:EE:FF","nickname":"herpstat","ip":"192.168.1.233","firmware":5.2,
           "numberofoutputs":2,"powerresets":1,"safetyrelay":"OFF (Normal Operation)"},
 "output1":{"outputnickname":"Lamp","outputmode":"Heat(Dimming)","probereadingTEMP":72.0,"currentsetting":90.0,
            "ramping":"Not In Session","endoframpsetting":0.0,"probereadingTEMPMAX":72.0,"probereadingTEMPMIN":66.6,
            "probereadingRH":0,"probereadingRHMAX":0,"probereadingRHMIN":0,"poweroutput":29,"poweroutputLIMIT":100,
            "enablehighlowalarm":0,"highalarm":100.0,"lowalarm":65.0,"errorcode":0,"errorcodedescription":"No Errors"},
 "output2":{ ...same keys... }}
```
Compared with the HTML status (values matched field-for-field at the same moment):
- **Extra in JSON:**
  - `numberofoutputs`
  - `ramping` / `endoframpsetting`
  - `poweroutputLIMIT` (= MaxPower)
  - RH fields (`0` = no probe)
  - numeric `errorcode`
  - alarm thresholds even when alarms are disabled
- **Missing from JSON:**
  - device clock
  - the mode's feature suffix: the HTML says `Heat (Dimming) Basking Assist & PS`, the JSON says `Heat(Dimming)`
  - history
- **Types:**
  - `enablehighlowalarm` and `errorcode` are 0/1 ints.
  - `safetyrelay` and `ramping` are free text.
  - Mode strings have no space before `(` here, but do in the HTML.
- No temperature unit anywhere. It follows the device's display setting (°F here).

### Custom Database Upload (push; not enabled)
The Advanced section also has `FORMCUSTOMDATABASEENABLE`, `FORMCUSTOMDATABASEURL` (`http://` only) and
`FORMCUSTOMDATABASEAPIKEY`. The vendor marks it "(Unsupported)".
When enabled, the device pushes its status to that URL, which would avoid polling altogether.
The payload format and push interval are unknown. They can be captured by pointing the URL at a listener (a settings change).

## Write surface (documented only, never submitted)

`POST /handleAdminControls`. Checkboxes come paired with a hidden field of the same name and value `0`.

| Field | Meaning |
|---|---|
| `FORMADMINPASSWORD` | Admin password (8–16 chars) |
| `FORMNICKNAME` | Device nickname (alphanumeric, ≤20 chars; changes the mDNS name after reboot) |
| `scheduleemailinterval` | `0` / `360` / `720` / `1439` minutes |
| `FORMENABLEEMERGENCYEMAIL` | Checkbox |
| `FORMENABLENUMBEREDEMAILS` | Checkbox |
| `FORMENABLEEMERGENCYSHUTDOWN` | **Trips the safety relay: all outputs off** |
| `FORMRESETHIGHLOW` | Reset High/Low and PowerReset counters |
| `FORMENABLEDATABASEUPLOAD` | Upload to herpstat.com (currently on) |
| `FORMSHOWADVANCEDSTATUSOPTIONS` | Auto-submits on change; reveals the RAWSTATUS/custom-upload options |
| `FORMSETUPWIZARD` | Restart the setup wizard |
| `FORMSUBMIT=SUBMIT` | Submit button |

`FORMSENDTOEMAILADDRESS` is rendered `disabled`.

### Per-output config (behind `/web_mainmenu`, layout from the vendor's screenshot)
Fields: Mode, Schedule Type (Constant / 2–4 periods), Set Temp per period (time + temp), Enable High/Low Alarms,
Low Alarm 30-min Mute, High/Low Temp Alarm, SensorMatch (ADD/SUB, -5 to +5), BaskingAssist, MaxPower (25–100%).
The vendor's page says **"The MODE option updates immediately. Mode changes will adjust corresponding settings to defaults."**
So the Mode `<select>` submits on change. A new UI must put a confirm step in front of mode changes.
Field names are unknown until that page is fetched.

## Not touched (deliberately)

| Route | Why |
|---|---|
| `GET /web_mainmenu` | Device configuration (per-output modes and setpoints). The physical menu turns all outputs off while it is open, and the web version may do the same. Fetch it only while someone is watching the enclosure. **Observed 2026-10-16:** while the web config UI was open (until ~11:16), `/RAWSTATUS` returned frozen values (Lamp 95.0°F / 0%, Heat 73.4°F / 0%, unchanged for 2+ min), and `/handlewebcharts` returned "Device is currently being adjusted. Please wait..." instead of chart data. Values resumed within ~10 s of leaving the UI. `/RAWSTATUS` has no flag for this state, so consumers can't tell frozen from steady. Whether outputs are cut during the web menu is still unverified (the lamp wasn't on the Herpstat at the time). |
| `GET /fwupdate` | May trigger a firmware check or update. |
| herpstat.com cloud viewer | `POST https://www.herpstat.com/spyderweb/login.php` (`username`=email, `password`=device admin pw). The device uploads there every ~4 min. Not explored. |

## Security

The device speaks plain HTTP and has no TLS. Keep it on a trusted LAN, never expose it to the internet, and have
any custom UI talk to it from a server-side proxy rather than from the browser.
