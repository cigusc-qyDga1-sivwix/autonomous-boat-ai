"""Bounded direct official beforeinfo acquisition, using the six-boat gate.
Source layout: official beforeinfo racer table and start exhibition graphic.
No results, odds, or payouts are read. Invalid/missing source data stays missing.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
import re
import unicodedata
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc

def norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(s)))

class Node:
    def __init__(self, tag="", attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []
    def text(self):
        return "".join(x if isinstance(x, str) else x.text() for x in self.children)
    def find(self, cls):
        return [n for n in self.walk() if cls in (n.attrs.get("class") or "").split()]
    def walk(self):
        yield self
        for x in self.children:
            if isinstance(x, Node):
                yield from x.walk()

class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag not in {"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}:
            self.stack.append(n)
    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break
    def handle_data(self, data):
        self.stack[-1].children.append(data)

def parse(html, expected_names):
    p = Tree()
    p.feed(html)
    # Rows are explicitly lane numbered, and each row must contain the
    # matching program name. Never align unrelated tables by row count.
    racers = {}
    for row in p.root.find("is-fs12"):
        cells = [n for n in row.walk() if n.tag == "td"]
        if len(cells) < 6:
            continue
        lane = norm(cells[0].text())
        if lane not in ("1","2","3","4","5","6"):
            continue
        if lane in racers or not norm(expected_names[int(lane)-1]) or norm(expected_names[int(lane)-1]) not in norm(row.text()):
            raise ValueError("racer identity mismatch")
        et = norm(cells[4].text())
        if not re.fullmatch(r"[5-9]\.\d{2}", et):
            raise ValueError("exhibition time missing")
        r = {"entry_number": int(lane), "exhibition_time": float(et)}
        tilt = norm(cells[5].text())
        if re.fullmatch(r"[+-]?\d(?:\.\d+)?", tilt):
            r["tilt_adjustment"] = float(tilt)
        racers[lane] = r
    starts = p.root.find("table1_boatImage1")
    if set(racers) != set("123456") or len(starts) != 6:
        raise ValueError("six racer/start rows missing")
    seen = set()
    for course, node in enumerate(starts, 1):
        nums = node.find("table1_boatImage1Number")
        times = node.find("table1_boatImage1Time")
        if len(nums) != 1 or len(times) != 1:
            raise ValueError("ambiguous start row")
        lane = norm(nums[0].text())
        st = norm(times[0].text()).upper()
        if lane not in racers or lane in seen or not re.fullmatch(r"(?:F\.?|0?\.)\d{2}", st):
            raise ValueError("invalid or incomplete start row")
        seen.add(lane)
        racers[lane].update(course_number=course, start_timing=(-1 if st.startswith("F") else 1)*int(st[-2:])/100)
    return {"racers": racers}

def fetch_one(code, n, race, cutoff, *, fetch=urlopen, clock=lambda: datetime.now(UTC)):
    day = cutoff.astimezone(JST).date()
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={int(n)}&jcd={int(code):02d}&hd={day:%Y%m%d}"
    status = {"race_id": f"{code}-{n}", "source_url": url}
    try:
        if clock() >= cutoff-timedelta(minutes=3):
            raise ValueError("too late")
        names = [race["racers"][str(i)]["name"] for i in range(1,7)]
        with fetch(Request(url, headers={"User-Agent":"BOAT-LAB-research/0.2 (read-only)","Cache-Control":"no-cache"}), timeout=5) as rsp:
            if rsp.geturl() != url:
                raise ValueError("source redirect")
            raw = rsp.read(1_000_001)
        received = clock()
        if len(raw)>1_000_000 or received>=cutoff-timedelta(minutes=3):
            raise ValueError("oversize or too late")
        preview = parse(raw.decode("utf-8"), names)
        preview.update(date=day.isoformat(), stadium_number=int(code), race_number=int(n))
        status.update(status="SIX_BOAT_PARSED", captured_at_utc=received.isoformat(), response_sha256=sha256(raw).hexdigest())
        return preview, status
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        status.update(status="UNAVAILABLE", reason=f"{type(exc).__name__}: {exc}")
        return None, status

def collect(payload, now, cutoff_of, valid_entrants, preview_complete, *, fetcher=fetch_one, clock=lambda: datetime.now(UTC)):
    targets=[]
    for code, stadium in ((payload.get("programs") or {}).get("stadiums") or {}).items():
        if not str(code).isdigit() or not 1<=int(code)<=24 or int(code)==3:
            continue
        for n, race in (stadium.get("races") or {}).items():
            if not isinstance(race,dict) or not str(n).isdigit() or not 1<=int(n)<=12 or not valid_entrants(race) or preview_complete(race):
                continue
            cutoff=cutoff_of(race)
            if cutoff and cutoff.astimezone(JST).date()==now.astimezone(JST).date() and timedelta(minutes=3,seconds=30)<cutoff-now<=timedelta(minutes=20):
                targets.append((cutoff,str(code),str(n),race))
    targets.sort(key=lambda t:(t[0],t[2]!="1",t[1]))
    selected=targets[:12]
    def run(item):
        cutoff,code,n,race=item
        return item,fetcher(code,n,race,cutoff)
    attempts=[]
    updated=[]
    # Limit simultaneous requests and total work; never hold live processing
    # for an unbounded source retry.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for (cutoff,code,n,race),(preview,status) in pool.map(run,selected):
            attempts.append(status)
            if preview is None or clock()>=cutoff-timedelta(minutes=3):
                continue
            candidate={**race,"preview":preview}
            if not preview_complete(candidate):
                continue
            race["preview"]=preview
            race["_preview_refresh_source_url"]=status["source_url"]
            race["_preview_refresh_received_at_utc"]=status["captured_at_utc"]
            race["_official_preview_response_sha256"]=status["response_sha256"]
            updated.append(f"{code}-{n}")
    return {"target_count":len(targets),"attempts":attempts,"updated":updated,
            "remaining_ids":[f"{c}-{n}" for _,c,n,_ in targets if f"{c}-{n}" not in updated]}
