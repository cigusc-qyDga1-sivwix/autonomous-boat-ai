"""Karatsu venue official preview capture (shadow/audit only).
No forecast promotion until live HTML and date identity have been verified.
"""
from datetime import datetime, timedelta
from hashlib import sha256
from html.parser import HTMLParser
import re
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
URL = "https://www.boatrace-karatsu.jp/sp/index.php?page=yosou-cyokuzen&race={race}&run=0"

class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None
        self.visible = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag == "tr":
            self.row = []
        if tag in ("td", "th") and self.row is not None:
            self.cell = []
        if tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
            self.cell = None

    def handle_data(self, data):
        if self.hidden:
            return
        self.visible.append(data)
        if self.cell is not None:
            self.cell.append(data)

def norm(s):
    return re.sub(r"\s+", "", str(s))

def st_number(s):
    s = norm(s).upper()
    if re.fullmatch(r"F\.?\d{2}", s):
        return -int(s[-2:]) / 100
    if re.fullmatch(r"0?\.\d{2}", s):
        return float(s)
    return None

def parse(html, race, expected_names, cutoff):
    p = Tables()
    p.feed(html)
    visible = norm("".join(p.visible))
    if len(expected_names) != 6 or any(not norm(n) or norm(n) not in visible for n in expected_names):
        raise ValueError("six program names not found")
    # Current page is not date-addressed: these are evidence, not proof of date.
    if not re.search(rf"{race}R[^0-9]{{0,40}}締切時刻{cutoff.strftime('%H:%M')}", visible):
        raise ValueError("race heading/cutoff mismatch")
    courses, metrics = {}, {}
    for row in p.rows:
        c = [norm(x) for x in row]
        if len(c) >= 4 and c[0] in "123456" and len(c[0]) == 1 and c[1] in "123456" and len(c[1]) == 1 and any(x in ("S", "D") for x in c[2:]):
            vals = [st_number(x) for x in c[-2:]]
            vals = [x for x in vals if x is not None]
            if len(vals) == 1:
                lane = int(c[1])
                if lane in courses:
                    raise ValueError("duplicate start row")
                courses[lane] = (int(c[0]), vals[0])
        if len(c) >= 8 and c[0] in "123456" and len(c[0]) == 1:
            # Weight/adjustment/tilt may vary; require exactly one contiguous
            # exhibition/lap/turn/straight numeric quartet in physical ranges.
            quartets = []
            for i in range(1, len(c)-3):
                try:
                    ex, lap, turn, straight = map(float, c[i:i+4])
                except ValueError:
                    continue
                if 5 <= ex <= 10 and 25 <= lap <= 50 and 3 <= turn <= 8 and 5 <= straight <= 10:
                    quartets.append((ex, lap, turn, straight))
            if len(quartets) == 1:
                lane = int(c[0])
                if lane in metrics:
                    raise ValueError("duplicate measurement row")
                metrics[lane] = quartets[0]
    if set(courses) != set(range(1, 7)) or set(metrics) != set(range(1, 7)) or {x[0] for x in courses.values()} != set(range(1, 7)):
        raise ValueError("six complete unique rows unavailable")
    return [{"lane": n, "name": expected_names[n-1], "course": courses[n][0],
             "start_timing": courses[n][1], "exhibition_time": metrics[n][0],
             "lap_time": metrics[n][1], "turn_time": metrics[n][2],
             "straight_time": metrics[n][3]} for n in range(1, 7)]

def collect(payload, now, *, fetch=urlopen):
    """At most one imminent race per run; first race has priority."""
    venue = ((payload.get("programs") or {}).get("stadiums") or {}).get("23", {})
    targets = []
    for key, row in (venue.get("races") or {}).items():
        try:
            n = int(key)
            cutoff = datetime.strptime(row["closed_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
            names = [row["racers"][str(i)]["name"] for i in range(1, 7)]
        except (KeyError, ValueError, TypeError):
            continue
        if 1 <= n <= 12 and cutoff.date() == now.astimezone(JST).date() and timedelta(minutes=4) < cutoff-now <= timedelta(minutes=45 if n == 1 else 25):
            targets.append((n != 1, cutoff, n, names))
    if not targets:
        return {"status": "NO_TARGET", "formal_input": False}
    _, cutoff, n, names = min(targets)
    url = URL.format(race=n)
    out = {"race_id": f"23-{n}", "source_url": url, "event_date": cutoff.date().isoformat(), "formal_input": False}
    try:
        with fetch(Request(url, headers={"User-Agent": "BOAT-LAB-research/0.2 (read-only)", "Cache-Control": "no-cache"}), timeout=5) as response:
            raw = response.read(2_000_001)
            encoding = response.headers.get_content_charset() or "utf-8"
        received = datetime.now(JST)
        out.update({"captured_at_jst": received.isoformat(), "response_sha256": sha256(raw).hexdigest()})
        if len(raw) > 2_000_000 or received >= cutoff-timedelta(minutes=3):
            raise ValueError("oversize or late response")
        out["boats"] = parse(raw.decode(encoding), n, names, cutoff)
        out["status"] = "SIX_BOAT_PARSED_SHADOW"
        out["date_identity_verified"] = False
    except Exception as exc:
        out.update({"status": "UNAVAILABLE", "reason": f"{type(exc).__name__}: {exc}"})
    return out
