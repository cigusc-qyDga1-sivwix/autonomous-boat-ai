"""Race-specific withdrawal notices published by BOAT RACE."""
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def normalize(value):
    return "".join(unicodedata.normalize("NFKC", value).split())


class NoticeTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.heading = None
        self.next_table = False
        self.active = False
        self.cell = None
        self.row = []
        self.rows = []
        self.venues = set()

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            attrs = dict(attrs)
            match = re.fullmatch(r"/static_extra/pc/images/text_place2_(\d{2})\.png",
                                 attrs.get("src", ""))
            if match:
                self.venues.add(match[1])
        elif tag == "h3":
            self.heading = []
            self.next_table = False
        elif tag == "table":
            self.active = self.next_table
            self.next_table = False
        elif self.active and tag == "tr":
            self.row = []
        elif self.active and tag in ("th", "td"):
            self.cell = []

    def handle_data(self, data):
        if self.heading is not None:
            self.heading.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "h3" and self.heading is not None:
            self.next_table = normalize("".join(self.heading)) == "欠場・帰郷"
            self.heading = None
        elif self.active and tag in ("th", "td") and self.cell is not None:
            self.row.append(normalize("".join(self.cell)))
            self.cell = None
        elif self.active and tag == "tr" and len(self.row) == 3:
            self.rows.append(tuple(self.row))
        elif tag == "table":
            self.active = False


def parse_notices(html, day, venue):
    table = NoticeTable()
    table.feed(html)
    if table.venues != {str(venue).zfill(2)}:
        return []
    date_label = f"{day.month}/{day.day}"
    return [(int(match[1]), name) for date, name, notice in table.rows
            if date == date_label and name
            and (match := re.fullmatch(r"([1-9]|1[0-2])R欠場(?:\(.*\))?", notice))]


def match_lanes(notices, race_number, racers):
    if not isinstance(racers, dict):
        return []
    lanes = set()
    for number, name in notices:
        if number != race_number:
            continue
        matches = [lane for lane, racer in racers.items()
                   if lane in ("1", "2", "3", "4", "5", "6") and isinstance(racer, dict)
                   and normalize(str(racer.get("name") or "")) == name]
        if len(matches) == 1:
            lanes.add(int(matches[0]))
    return sorted(lanes)


def fetch_notices(day, venue):
    url = "https://www.boatrace.jp/owpc/pc/race/information?" + urlencode({
        "hd": day.strftime("%Y%m%d"), "jcd": str(venue).zfill(2),
    })
    req = Request(url, headers={"User-Agent": "BOAT-LAB-research/0.2 (read-only)"})
    with urlopen(req, timeout=3) as response:
        if response.geturl() != url:
            return [], url
        return parse_notices(response.read(1_000_000).decode("utf-8"), day, venue), url
