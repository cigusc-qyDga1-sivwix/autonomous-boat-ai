"""Read-only, strict extraction of trifecta payouts from BOATRACE's official pay page.

Source: https://www.boatrace.jp/owpc/pc/race/pay?hd=YYYYMMDD
The HTML includes multiple five-venue tables. Each result cell contains an exact
rno/jcd/hd data-href, which is validated against its table header, row and day.

Refunds (返), cancellations, ambiguous / multiple payouts and incomplete races
are deliberately *not* scored as wins or losses. No ticket purchases.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


OFFICIAL_URL = "https://www.boatrace.jp/owpc/pc/race/pay"
VENUE_CODES = {
    "桐生": "1", "戸田": "2", "江戸川": "3", "平和島": "4", "多摩川": "5",
    "浜名湖": "6", "蒲郡": "7", "常滑": "8", "津": "9", "三国": "10",
    "びわこ": "11", "住之江": "12", "尼崎": "13", "鳴門": "14",
    "丸亀": "15", "児島": "16", "宮島": "17", "徳山": "18",
    "下関": "19", "若松": "20", "芦屋": "21", "福岡": "22",
    "唐津": "23", "大村": "24",
}
COMBO = re.compile(r"^[1-6]{3}$")
PAY = re.compile(r"^[¥￥]\s*([\d,]+)\s*$")
DATE = re.compile(r"^\d{8}$")


class PayTables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.depth = 0
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "table":
            if self.table is not None:
                self.depth += 1
            elif "is-strited1" in props.get("class", ""):
                self.table = []
                self.depth = 0
            return
        if self.table is None or self.depth:
            return
        if tag == "tr":
            self.row = []
        elif tag in ("th", "td") and self.row is not None:
            self.cell = {"tag": tag, "attrs": props, "text": [], "images": []}
        elif tag == "img" and self.cell is not None:
            self.cell["images"].append(props.get("alt", ""))

    def handle_data(self, value):
        self.text_parts.append(value)
        if self.cell is not None:
            self.cell["text"].append(value)

    def handle_endtag(self, tag):
        if tag == "table" and self.table is not None:
            if self.depth:
                self.depth -= 1
            else:
                self.tables.append(self.table)
                self.table = None
            return
        if self.table is None or self.depth:
            return
        if tag in ("th", "td") and self.cell is not None:
            self.cell["text"] = re.sub(r"\s+", "", "".join(self.cell["text"]))
            if self.row is not None:
                self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None


def _href_details(cell):
    href = cell["attrs"].get("data-href") or ""
    u = urlparse(href)
    if u.path != "/owpc/pc/race/raceresult":
        return None
    q = parse_qs(u.query)
    try:
        return int(q["jcd"][0]), int(q["rno"][0]), q["hd"][0]
    except (KeyError, ValueError, IndexError):
        return None


def _parse_group(cells, code, race_number, date_yyyymmdd):
    if len(cells) != 3:
        if any("中止" in c["text"] for c in cells):
            return "cancelled", None
        if any("返" in c["text"] for c in cells):
            return "review", "refund"
        return "pending", None

    parts = [c["text"] for c in cells]
    if any("中止" in s for s in parts):
        return "cancelled", None

    # Payout has to exist and correspond to the exact official race page.
    payout = PAY.fullmatch(parts[1])
    if not payout:
        if "返" in "".join(parts):
            return "review", "refund"
        if any("¥" in s or "￥" in s for s in parts):
            return "review", "malformed_payout"
        return "pending", None

    links = [_href_details(c) for c in cells]
    if any(link != (int(code), race_number, date_yyyymmdd) for link in links):
        return "review", "race_identifier_mismatch"
    if "返" in "".join(parts):
        return "review", "refund"
    combo_digits = parts[0]
    if not COMBO.fullmatch(combo_digits) or len(set(combo_digits)) != 3:
        return "review", "ambiguous_combination"
    value = int(payout.group(1).replace(",", ""))
    if not 100 <= value <= 100_000_000 or value % 10:
        return "review", "invalid_payout"
    return "verified", {"finish": "-".join(combo_digits), "payout_per_100": value}


def parse_pay_page(raw_html: str, date_yyyymmdd: str) -> dict:
    if not DATE.fullmatch(date_yyyymmdd):
        raise ValueError("Date must be YYYYMMDD")
    month, day = int(date_yyyymmdd[4:6]), int(date_yyyymmdd[6:8])
    p = PayTables()
    p.feed(raw_html)
    text = "".join(p.text_parts)
    # Prevent a stale day's page from silently being applied to today's races.
    if not re.search(rf"{month}月{day}日レースの払戻金", text):
        raise ValueError("Official pay page heading does not match the requested date")
    if not p.tables:
        raise ValueError("Official pay page contains no supported tables")

    results = {}
    reviews = {}
    cancellations = {}
    pending = 0
    venues = set()
    for rows in p.tables:
        if len(rows) < 3:
            continue
        header = rows[0]
        venue_headers = [c for c in header if c["tag"] == "th" and c["images"]]
        venue_codes = []
        for col in venue_headers:
            names = [x for x in col["images"] if x in VENUE_CODES]
            if len(names) != 1:
                raise ValueError("Could not identify official venue header")
            code = VENUE_CODES[names[0]]
            if code in venues:
                raise ValueError("Duplicate official venue column")
            venues.add(code)
            venue_codes.append(code)

        if not venue_codes:
            continue
        for row in rows[2:]:
            if not row or row[0]["tag"] != "th":
                continue
            match = re.fullmatch(r"(1[0-2]|[1-9])R", row[0]["text"])
            if not match:
                continue
            race_number = int(match.group(1))
            remainder = row[1:]
            i = 0
            for code in venue_codes:
                cells = []
                width = 0
                while width < 3 and i < len(remainder):
                    c = remainder[i]
                    i += 1
                    colspan_raw = c["attrs"].get("colspan", "1")
                    try:
                        colspan = int(colspan_raw)
                    except (TypeError, ValueError):
                        colspan = 1
                    width += colspan
                    cells.append(c)
                if width != 3:
                    raise ValueError("Official race table columns do not align")
                status, value = _parse_group(cells, code, race_number, date_yyyymmdd)
                key = f"{code}-{race_number}"
                if status == "verified":
                    results[key] = value
                elif status == "cancelled":
                    cancellations[key] = {"reason": "レース中止"}
                elif status == "review":
                    reviews[key] = {"reason": value}
                else:
                    pending += 1
            if i != len(remainder):
                raise ValueError("Unexpected extra payoff columns")
    if not venues:
        raise ValueError("No official venue headings in payoff tables")
    return {
        "date": f"{date_yyyymmdd[:4]}-{date_yyyymmdd[4:6]}-{date_yyyymmdd[6:]}",
        "results": results,
        "reviews": reviews,
        "cancellations": cancellations,
        "pending_count": pending,
        "venue_codes": sorted(venues, key=int),
    }


def fetch_official_pay(date_yyyymmdd: str, timeout: int = 23) -> dict:
    if not DATE.fullmatch(date_yyyymmdd):
        raise ValueError("Date must be YYYYMMDD")
    url = f"{OFFICIAL_URL}?hd={date_yyyymmdd}"
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; BOAT-LAB-results-research/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError(f"Official pay HTTP {response.status}")
        content = response.read(1_500_001)
    if len(content) > 1_500_000:
        raise ValueError("Official page exceeded safety size")
    doc = content.decode("utf-8")
    values = parse_pay_page(doc, date_yyyymmdd)
    values["source_url"] = url
    values["retrieved_at_utc"] = datetime.now(timezone.utc).isoformat()
    return values


if __name__ == "__main__":
    import json
    import sys
    from zoneinfo import ZoneInfo
    date = (sys.argv[1] if len(sys.argv) > 1 else
            datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d"))
    v = fetch_official_pay(date)
    print(json.dumps({
        "date": v["date"], "venues": len(v["venue_codes"]),
        "verified": len(v["results"]), "reviews": len(v["reviews"]),
        "cancelled": len(v["cancellations"]), "pending": v["pending_count"],
        "sample": dict(list(v["results"].items())[:6])
    }, ensure_ascii=False))
