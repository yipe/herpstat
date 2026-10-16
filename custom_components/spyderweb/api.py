"""Read-only client for the Herpstat SpyderWeb /RAWSTATUS JSON endpoint.

/RAWSTATUS needs no login but must be enabled in the device's Admin page;
otherwise the device answers HTTP 501 "Handler did not handle the request".
The response is JSON served as text/html, so it is decoded manually.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any

import aiohttp

REQUEST_TIMEOUT = 10
_OUTPUT_KEY = re.compile(r"^output(\d+)$")


class SpyderWebError(Exception):
    """Base error."""


class SpyderWebConnectionError(SpyderWebError):
    """Device unreachable or timed out."""


class SpyderWebRawStatusDisabled(SpyderWebError):
    """/RAWSTATUS is turned off in the device's Admin page."""


class SpyderWebInvalidResponse(SpyderWebError):
    """Device answered with something that is not a usable status payload."""


@dataclass(frozen=True, slots=True)
class Output:
    index: int
    nickname: str
    mode: str | None
    temperature: float | None
    setpoint: float | None
    ramping: str | None
    end_of_ramp_setpoint: float | None
    temperature_max: float | None
    temperature_min: float | None
    humidity: float | None
    humidity_max: float | None
    humidity_min: float | None
    power: int | None
    power_limit: int | None
    alarm_enabled: bool
    high_alarm: float | None
    low_alarm: float | None
    error_code: int | None
    error_description: str | None

    @property
    def has_humidity(self) -> bool:
        """RH fields read 0 when no humidity probe is attached."""
        return any(v for v in (self.humidity, self.humidity_max, self.humidity_min))

    @property
    def has_error(self) -> bool:
        return bool(self.error_code)


@dataclass(frozen=True, slots=True)
class System:
    mac: str
    nickname: str | None
    ip: str | None
    firmware: str | None
    power_resets: int | None
    safety_relay: str | None

    @property
    def safety_relay_tripped(self) -> bool:
        # Normal reads "OFF (Normal Operation)"; anything else means power to outputs is cut.
        return self.safety_relay is not None and not self.safety_relay.upper().startswith("OFF")


@dataclass(frozen=True, slots=True)
class Status:
    system: System
    outputs: dict[int, Output]
    raw: dict[str, Any] = field(repr=False, compare=False)  # original payload, for diagnostics


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    f = _float(value)
    return None if f is None else int(f)


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_status(payload: Any) -> Status:
    if not isinstance(payload, dict) or not isinstance(payload.get("system"), dict):
        raise SpyderWebInvalidResponse("payload has no 'system' object")
    sysd = payload["system"]
    mac = _str(sysd.get("mac"))
    if not mac:
        raise SpyderWebInvalidResponse("payload has no system.mac")
    system = System(
        mac=mac,
        nickname=_str(sysd.get("nickname")),
        ip=_str(sysd.get("ip")),
        firmware=_str(sysd.get("firmware")),
        power_resets=_int(sysd.get("powerresets")),
        safety_relay=_str(sysd.get("safetyrelay")),
    )
    outputs: dict[int, Output] = {}
    for key, out in payload.items():
        match = _OUTPUT_KEY.match(key)
        if not match or not isinstance(out, dict):
            continue
        index = int(match[1])
        outputs[index] = Output(
            index=index,
            nickname=_str(out.get("outputnickname")) or f"Output {index}",
            mode=_str(out.get("outputmode")),
            temperature=_float(out.get("probereadingTEMP")),
            setpoint=_float(out.get("currentsetting")),
            ramping=_str(out.get("ramping")),
            end_of_ramp_setpoint=_float(out.get("endoframpsetting")),
            temperature_max=_float(out.get("probereadingTEMPMAX")),
            temperature_min=_float(out.get("probereadingTEMPMIN")),
            humidity=_float(out.get("probereadingRH")),
            humidity_max=_float(out.get("probereadingRHMAX")),
            humidity_min=_float(out.get("probereadingRHMIN")),
            power=_int(out.get("poweroutput")),
            power_limit=_int(out.get("poweroutputLIMIT")),
            alarm_enabled=bool(_int(out.get("enablehighlowalarm"))),
            high_alarm=_float(out.get("highalarm")),
            low_alarm=_float(out.get("lowalarm")),
            error_code=_int(out.get("errorcode")),
            error_description=_str(out.get("errorcodedescription")),
        )
    return Status(system=system, outputs=dict(sorted(outputs.items())), raw=payload)


async def fetch_status(session: aiohttp.ClientSession, host: str) -> Status:
    """GET http://<host>/RAWSTATUS and parse it."""
    url = f"http://{host}/RAWSTATUS"
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with session.get(url) as resp:
                body = await resp.text(errors="replace")
                status = resp.status
    except (aiohttp.ClientError, TimeoutError) as err:
        raise SpyderWebConnectionError(f"{url}: {err!r}") from err
    if status == 501:
        raise SpyderWebRawStatusDisabled(f"{url}: HTTP 501, /RAWSTATUS is disabled")
    if status != 200:
        raise SpyderWebInvalidResponse(f"{url}: HTTP {status}")
    try:
        payload = json.loads(body)
    except ValueError as err:
        raise SpyderWebInvalidResponse(f"{url}: not JSON") from err
    return parse_status(payload)
