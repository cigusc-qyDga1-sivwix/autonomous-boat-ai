"""Verify refundable boat numbers against the official, race-specific result page.

Never infer a refunded boat from the payoff table's bare "返" marker.
Only the official result page can authorize a virtual ticket refund.
"""
from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request, urlopen

RESULT_URL = "https://www.boatrace.jp/owpc/pc/race/raceresult"


class _ResultText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.image_alts = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            alt = dict(attrs).get("alt", "")
            if alt:
                self.image_alts.append(unicodedata.normalize("NFKC", alt).strip())

    def handle_data(self, data):
        value = unicodedata.normalize("NFKC", data).strip()
        if value:
            self.parts.append(value)


def parse_official_refund(html: str, yyyymmdd: str, venue_name: str,
                          expected_finish: str | None, expected_payout: int | None,
                          void_trifecta: bool = False) -> dict:
    """Fail closed on venue/day, payout, missing return boats or ambiguous evidence."""
    if not re.fullmatch(r"20\d{6}", yyyymmdd):
        raise ValueError("Invalid race day")
    doc = _ResultText()
    doc.feed(html)
    parts = doc.parts
    if venue_name not in doc.image_alts:
        raise ValueError("Official result venue mismatch")
    date_label = f"{int(yyyymmdd[4:6])}月{int(yyyymmdd[6:8])}日"
    if date_label not in "".join(parts):
        raise ValueError("Official result day mismatch")
    if "3連単" not in parts:
        raise ValueError("No trifecta evidence on official result page")
    first = parts.index("3連単")
    end = next((i for i in range(first + 1, len(parts))
                if parts[i] in ("3連複", "2連単", "返還")), len(parts))
    tri = " ".join(parts[first + 1:end])
    if void_trifecta:
        if "不成立" not in tri:
            raise ValueError("No proof of void trifecta")
    else:
        if (not expected_finish or not re.fullmatch(r"[1-6]-[1-6]-[1-6]", expected_finish)
                or len(set(expected_finish.split("-"))) != 3
                or not isinstance(expected_payout, int) or expected_payout < 100):
            raise ValueError("Invalid expected payoff")
        expected = r"\s*[-‐‑–ー]\s*".join(expected_finish.split("-"))
        if not re.search(expected, tri):
            raise ValueError("Trifecta combination mismatch")
        money = f"{expected_payout:,}"
        if not re.search(r"[¥￥]\\s*" + re.escape(money) + r"(?![\d,])", tri):
            # HTMLParser may split a currency symbol across text nodes.
            if not re.search(r"[¥￥]\s*" + re.escape(money) + r"(?![\d,])", tri):
                raise ValueError("Trifecta payout mismatch")
    if "返還" not in parts:
        raise ValueError("Official refund section absent")
    pos = parts.index("返還")
    stop = next((i for i in range(pos + 1, len(parts))
                 if parts[i] in ("決まり手", "備考", "ボートレースガイド")), len(parts))
    section = parts[pos + 1:stop]
    if not section or len(section) > 12:
        raise ValueError("Refund boat section missing or ambiguous")
    boats = []
    for token in section:
        for v in token.split():
            if not re.fullmatch("[1-6]", v) or int(v) in boats:
                raise ValueError("Unexpected refund boat value")
            boats.append(int(v))
    if not boats:
        raise ValueError("No official refunded boat numbers")
    # A detailed reason is extra information; the explicit official return
    # section is the sole authority for deciding which tickets are refunded.
    causes = {}
    for index, token in enumerate(parts[:first]):
        normalized = token.upper()
        if normalized in ("F", "L", "欠場", "欠") and index + 1 < len(parts):
            match = re.fullmatch("[1-6]", parts[index + 1])
            if match and int(match.group()) in boats:
                causes[match.group()] = ("F" if normalized == "F" else
                                         "L" if normalized == "L" else "欠場")
    return {"refunded_boats": sorted(boats),
            "refund_reasons": causes,
            "void_trifecta": bool(void_trifecta)}


def official_race_url(yyyymmdd: str, venue_code: str, race_number: int) -> str:
    if (not re.fullmatch(r"20\d{6}", yyyymmdd)
            or not re.fullmatch(r"(?:[1-9]|1\d|2[0-4])", str(venue_code))
            or not 1 <= race_number <= 12):
        raise ValueError("Invalid race identifier")
    return RESULT_URL + "?" + urlencode({
        "rno": str(race_number), "jcd": f"{int(venue_code):02d}", "hd": yyyymmdd
    })


def fetch_race_result(yyyymmdd: str, venue_code: str, race_number: int,
                      timeout: int = 9) -> str:
    url = official_race_url(yyyymmdd, venue_code, race_number)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (BOAT-LAB-official-refunds/1.0)",
                                    "Accept": "text/html,application/xhtml+xml"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError("Official race result HTTP error")
        raw = response.read(600_001)
    if len(raw) > 600_000:
        raise ValueError("Official race result exceeded maximum size")
    return raw.decode("utf-8")
