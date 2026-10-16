"""Read-only client for a Spyder Robotics Herpstat SpyderWeb (firmware 5.2).

Stdlib only. Only GET requests are issued, plus the one POST /checkpassword
login, which creates a session and changes no settings. /RAWSTATUS needs no
login; status() and history() do. Poll no faster than every 10 s (vendor guidance).

    HERPSTAT_PASSWORD=... python3 tools/herpstat_client.py [host]   # prompts if unset
"""

import getpass
import http.cookiejar
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from html import unescape


class HerpstatError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Herpstat:
    def __init__(self, host="herpstat.local", timeout=10):
        # Resolve once, IPv4 only: the ESP32 never answers mDNS AAAA queries, so a
        # dual-stack lookup of *.local stalls ~5 s on every request (macOS).
        self.base = f"http://{socket.gethostbyname(host)}"
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), _NoRedirect)

    def _request(self, path, form=None):
        body = urllib.parse.urlencode(form).encode() if form else None
        req = urllib.request.Request(self.base + path, data=body)
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                return r.status, r.headers, r.read().decode("latin-1")
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode("latin-1")

    def _get(self, path):
        status, headers, text = self._request(path)
        if status == 301:
            raise HerpstatError(f"GET {path}: not logged in (redirect to {headers.get('Location')})")
        if status != 200:
            raise HerpstatError(f"GET {path}: HTTP {status}: {text.strip()}")
        if "Please Log In" in text:
            raise HerpstatError(f"GET {path}: session rejected")
        return text

    def login(self, password):
        # The device only answers requests carrying its cookie; GET / issues it (value 0).
        self._request("/")
        status, headers, _ = self._request("/checkpassword", {"PASSWORD": password, "SUBMIT": "Submit"})
        if status != 301 or headers.get("Location") != "/STATUSPAGE":
            raise HerpstatError(f"login failed: HTTP {status} -> {headers.get('Location')}")

    def status(self):
        return parse_status(self._get("/GETHERPSTATWEBDATA"))

    def history(self):
        return parse_charts(self._get("/handlewebcharts"))

    def rawstatus(self):
        """JSON status; no login needed. HTTP 501 if disabled in Admin."""
        return json.loads(self._get("/RAWSTATUS"))


def _cells(html):
    """Split the status fragment into <td> cells of plain-text lines."""
    cells = []
    for cell in re.findall(r"<td[^>]*>(.*?)</td>", html, re.S):
        text = re.sub(r"<br\s*/?>", "\n", cell)
        text = unescape(re.sub(r"<[^>]+>", "", text))
        cells.append([line.strip() for line in text.split("\n") if line.strip()])
    return cells


def _num(value):
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)%?", value)
    if not m:
        return value
    return float(m[1]) if "." in m[1] else int(m[1])


def _pairs(lines):
    out = {}
    for line in lines:
        m = re.match(r"([^:=]+?)\s*[:=]\s*(.*)", line)
        if m:
            out[m[1].strip()] = _num(m[2].strip())
    return out


def parse_status(html):
    cells = _cells(html)
    if not cells:
        raise HerpstatError("status fragment had no table cells")
    system = _pairs(cells[0])
    # "Device Nickname: " and its value render on one line; firmware truncates "AM"/"PM" to "A"/"P".
    clock = str(system.get("Device Clock", ""))
    if re.fullmatch(r"\d\d:\d\d:\d\d [AP]", clock):
        system["Device Clock"] = clock + "M"
    outputs = []
    for lines in cells[1:]:
        m = re.match(r"Output #(\d+)\s*(.*)", lines[0])
        if not m:
            continue
        outputs.append({"index": int(m[1]), "name": m[2], **_pairs(lines[1:])})
    return {"system": system, "outputs": outputs}


_CHART_RE = re.compile(
    r"arrayToDataTable\((\[.*?\])\);var options = \{title: '([^']*)'.*?"
    r"Lowest Temp Recorded: (-?[\d.]+)<br>Highest Temp Recorded: (-?[\d.]+)",
    re.S,
)


def parse_charts(html):
    span = re.search(r"(\d+) data points over last ([^<]+)<", html)
    charts = []
    for table, title, low, high in _CHART_RE.findall(html):
        # Partially filled history (e.g. right after a settings change) ends with ",]".
        rows = json.loads(re.sub(r",\s*\]$", "]", table.replace("'", '"')))
        header, data = rows[0], rows[1:]
        m = re.match(r"SpyderWeb Output #(\d+)\s*(.*)", title)
        charts.append(
            {
                "index": int(m[1]) if m else None,
                "name": m[2] if m else title,
                "columns": header,
                "points": data,
                "low": float(low),
                "high": float(high),
            }
        )
    return {
        "points": int(span[1]) if span else None,
        "period": span[2].strip() if span else None,
        "outputs": charts,
    }


if __name__ == "__main__":
    dev = Herpstat(sys.argv[1] if len(sys.argv) > 1 else "herpstat.local")
    raw = dev.rawstatus()  # before login: proves it is unauthenticated
    dev.login(os.environ.get("HERPSTAT_PASSWORD") or getpass.getpass("Herpstat admin password: "))
    hist = dev.history()
    for c in hist["outputs"]:
        c["points"] = c["points"][-3:]  # keep the demo output short
    print(json.dumps({"rawstatus": raw, "status": dev.status(), "history": hist}, indent=2))
