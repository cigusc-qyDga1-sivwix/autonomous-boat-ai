"""Bounded same-day official beforeinfo fallback; no results or old forecasts.
Only verified six names, six unique courses and measured values are admitted.
"""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import hashlib
import re
import unicodedata

if __package__:
    from .entry_exhibition_gate import validated_preview
else:
    from entry_exhibition_gate import validated_preview

UTC = timezone.utc
JST = ZoneInfo("Asia/Tokyo")
SOURCE = "BOATRACE_official_beforeinfo"
LIMIT = 6
MIN_LEAD = timedelta(minutes=4)
MAX_LEAD = timedelta(minutes=20)

class Node:
    def __init__(self, tag="", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []
    def walk(self, tag=None, cls=None):
        for x in self.children:
            if isinstance(x, Node):
                if (tag is None or x.tag == tag) and (cls is None or cls in (x.attrs.get("class") or "").split()):
                    yield x
                yield from x.walk(tag, cls)
    def text(self):
        return "".join(x.text() if isinstance(x, Node) else x for x in self.children).strip()

class Tree(HTMLParser):
    VOID = {"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break
    def handle_data(self, data):
        self.stack[-1].children.append(data)

def norm(value):
    return "".join(unicodedata.normalize("NFKC", str(value or "")).split())

def parse(page, entrants):
    tree = Tree()
    tree.feed(page)
    grids = list(tree.root.walk("div", "grid_unit"))
    # Select exactly one six-lane table by matching ALL scheduled racer names.
    candidates = []
    expected = {str(i): norm((entrants.get(str(i)) or {}).get("name")) for i in range(1,7)}
    if not all(expected.values()) or len(set(expected.values())) != 6:
        raise ValueError("missing or ambiguous program names")
    for grid in grids:
        for table in grid.walk("table"):
            boats = {}
            for body in table.walk("tbody"):
                rows = list(body.walk("tr"))
                if not rows:
                    continue
                cells = [n for n in rows[0].children if isinstance(n, Node) and n.tag == "td"]
                if len(cells) < 6:
                    continue
                lane = norm(cells[0].text())
                if lane not in expected:
                    continue
                names = [norm(a.text()) for a in cells[2].walk("a")]
                if expected[lane] not in names:
                    continue
                if lane in boats:
                    raise ValueError("duplicate lane")
                expo = norm(cells[4].text())
                tilt = norm(cells[5].text())
                if not re.fullmatch(r"\d\.\d{2}", expo):
                    continue
                boats[lane] = {"exhibition_time": float(expo)}
                if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", tilt):
                    boats[lane]["tilt_adjustment"] = float(tilt)
            if set(boats) == set(expected):
                candidates.append(boats)
    if len(candidates) != 1:
        raise ValueError("no unique complete named exhibition-time table")
    boats = candidates[0]
    starts = list(tree.root.walk("div", "table1_boatImage1"))
    if len(starts) != 6:
        raise ValueError("six start exhibition rows required")
    seen = set()
    for course, row in enumerate(starts, 1):
        numbers = list(row.walk("span", "table1_boatImage1Number"))
        times = list(row.walk("span", "table1_boatImage1Time"))
        if len(numbers) != 1 or len(times) != 1:
            raise ValueError("ambiguous start row")
        lane = norm(numbers[0].text())
        raw = norm(times[0].text()).upper()
        if lane not in boats or lane in seen or not re.fullmatch(r"(?:F\.)?\d{2}|\.\d{2}|0\.\d{2}", raw):
            raise ValueError("missing/invalid start row")
        # Bare two-digit tokens are not accepted as seconds.
        if "." not in raw:
            raise ValueError("ambiguous ST format")
        st = -float("0"+raw[1:]) if raw.startswith("F.") else float(raw)
        boats[lane].update(course_number=course, start_timing=st)
        seen.add(lane)
    preview = {"racers": boats}
    if validated_preview(preview) is None:
        raise ValueError("invalid six-boat measurements")
    return preview

def official_url(venue, number, cutoff):
    return ("https://www.boatrace.jp/owpc/pc/race/beforeinfo"
            f"?rno={number}&jcd={int(venue):02d}&hd={cutoff.astimezone(JST):%Y%m%d}")

def fetch_one(target):
    venue, number, cutoff, race = target
    url = official_url(venue, number, cutoff)
    try:
        if datetime.now(UTC) >= cutoff - timedelta(minutes=3):
            return None, "too_late"
        req = Request(url, headers={"User-Agent":"BOAT LAB preview monitor", "Cache-Control":"no-cache"})
        with urlopen(req, timeout=12) as rsp:
            if rsp.geturl() != url:
                return None, "unexpected_redirect"
            raw = rsp.read(750001)
        captured = datetime.now(UTC)
        if len(raw) > 750000 or captured >= cutoff - timedelta(minutes=3):
            return None, "oversize_or_late"
        preview = parse(raw.decode("utf-8"), race.get("racers") or {})
        if datetime.now(UTC) >= cutoff - timedelta(minutes=3):
            return None, "too_late"
        return (preview, {
            "source": SOURCE, "source_url": url,
            "captured_at_utc": captured.isoformat(), "captured_before_cutoff": True,
            "source_body_sha256": hashlib.sha256(raw).hexdigest(),
            "source_observation_time": "not_provided", "six_program_names_matched": True,
            "metrics": [],
        }), None
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        return None, type(exc).__name__ + ":" + str(exc)[:120]

def collect(payload, now, previous=None, *, fetch=fetch_one):
    targets = []
    for code, stadium in ((payload.get("programs") or {}).get("stadiums") or {}).items():
        if not str(code).isdigit() or not 1 <= int(code) <= 24 or int(code) == 3:
            continue
        for n, race in ((stadium or {}).get("races") or {}).items():
            if not isinstance(race, dict) or not str(n).isdigit() or not 1 <= int(n) <= 12:
                continue
            try:
                cutoff = datetime.strptime(race["closed_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
            except (KeyError, TypeError, ValueError):
                continue
            if (cutoff.date() != now.astimezone(JST).date()
                or not MIN_LEAD <= cutoff-now <= MAX_LEAD
                or validated_preview(race.get("preview")) is not None):
                continue
            targets.append((code, int(n), cutoff, race))
    targets.sort(key=lambda t: t[2])
    selected = targets[:LIMIT]
    status = {"eligible_targets": len(targets), "attempted": len(selected), "captured_six_boat": 0, "failures": {}}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for target, (result, reason) in zip(selected, pool.map(fetch, selected)):
            code, n, cutoff, race = target
            if result is None:
                status["failures"][f"{code}-{n}"] = reason
                continue
            preview, origin = result
            # Do not splice two independent sets of six-boat measurements.
            existing = race.get("preview")
            race["preview"] = {**(existing if isinstance(existing, dict) else {}), **preview}
            race["_official_preview_origin"] = origin
            status["captured_six_boat"] += 1
    return status
