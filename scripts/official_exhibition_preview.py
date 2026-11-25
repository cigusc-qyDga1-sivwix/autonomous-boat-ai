"""Conservative, read-only BOAT RACE beforeinfo fallback.

Only complete six-name, six-lane, six-course measurements are accepted.
No results, odds, inferred courses, or inferred withdrawals.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, urlopen


def norm(value):
    return "".join(unicodedata.normalize("NFKC", str(value)).split())


class BeforeInfo(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None
        self.span = None
        self.start_values = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []
        elif tag == "span":
            classes = dict(attrs).get("class", "").split()
            for kind in ("Number", "Time"):
                if "table1_boatImage1" + kind in classes:
                    self.span = (kind, [])
                    break

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
        if self.span is not None:
            self.span[1].append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None and self.row is not None:
            self.row.append(norm("".join(self.cell)))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
            self.cell = None
        elif tag == "span" and self.span is not None:
            kind, value = self.span
            self.start_values.append((kind, norm("".join(value))))
            self.span = None


def parse_preview(html, racers):
    parser = BeforeInfo()
    parser.feed(html)
    times = {}
    for row in parser.rows:
        if len(row) < 5 or row[0] not in "123456" or len(row[0]) != 1:
            continue
        lane = row[0]
        name = norm((racers.get(lane) or {}).get("name", ""))
        if not name or row[2] != name:
            continue
        if lane in times or not re.fullmatch(r"[5-9]\.\d{2}", row[4]):
            return None
        times[lane] = float(row[4])
    if set(times) != set("123456") or len(parser.start_values) != 12:
        return None
    preview = {}
    for course in range(1, 7):
        (number_kind, lane), (time_kind, st) = parser.start_values[2*course-2:2*course]
        if (number_kind != "Number" or time_kind != "Time"
                or lane not in times or lane in preview
                or not re.fullmatch(r"F?(?:0?\.\d{2}|1\.00)", st)):
            return None
        value = -float(st[1:]) if st.startswith("F") else float(st)
        if not -.5 <= value <= 1.0:
            return None
        preview[lane] = {"course_number": course, "start_timing": value,
                         "exhibition_time": times[lane]}
    return {"racers": preview}


def fetch_preview(day, venue, number, racers, timeout=8):
    query = {"rno": str(number), "jcd": str(venue).zfill(2), "hd": day}
    url = "https://www.boatrace.jp/owpc/pc/race/beforeinfo?" + urlencode(query)
    req = Request(url, headers={"User-Agent": "BOAT-LAB-research/0.2 (read-only)"})
    with urlopen(req, timeout=timeout) as response:
        final = urlsplit(response.geturl())
        if (final.scheme != "https" or final.netloc != "www.boatrace.jp"
                or final.path != "/owpc/pc/race/beforeinfo"
                or parse_qs(final.query) != {key: [value] for key, value in query.items()}):
            return None, url, None
        body = response.read(2_000_001)
    received = datetime.now(timezone.utc)
    if len(body) > 2_000_000:
        return None, url, received
    return parse_preview(body.decode("utf-8"), racers), url, received
