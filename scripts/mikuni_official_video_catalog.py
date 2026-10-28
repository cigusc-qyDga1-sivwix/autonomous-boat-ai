"""Read-only catalog of the venue-specified *official* Mikuni YouTube channel.

The venue's published 2025-04-01 video-use rules identify this channel.
This collector requests only Atom/RSS metadata (titles, publication dates, IDs);
it never downloads or decodes videos, fetches HLS segments, uses yt-dlp,
bypasses a protected stream, or assumes third-party download permission.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from xml.etree import ElementTree

CHANNEL_ID="UCu-yP6WJQ0zcx5nmWhxvJEg"
CHANNEL_URL=f"https://www.youtube.com/channel/{CHANNEL_ID}"
FEED_URL=f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
RULES_URL="https://www.boatrace-mikuni.jp/uploads/cdn/faq/files/20250401_race_eizo.pdf"
SCHEMA="boatlabs.mikuni_official_youtube_video_catalog.v1"
JST=timezone(timedelta(hours=9))
MAX_BYTES=1024*1024
NS={"atom":"http://www.w3.org/2005/Atom",
    "yt":"http://www.youtube.com/xml/schemas/2015"}


class RestrictedFeedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed=urlparse(newurl)
        if parsed.scheme!="https" or parsed.hostname not in {"www.youtube.com","youtube.com"}:
            raise ValueError("youtube_rss_redirect_to_untrusted_host")
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def request_feed():
    """Query the public channel *metadata feed*, never a video endpoint."""
    opener=build_opener(HTTPSHandler(),RestrictedFeedRedirect())
    request=Request(FEED_URL,headers={"User-Agent":"BOAT-LAB-official-video-metadata-research/1.0",
                                     "Accept":"application/atom+xml,application/xml,text/xml"})
    with opener.open(request,timeout=12) as response:
        final=urlparse(response.geturl())
        if final.scheme!="https" or final.hostname not in ("youtube.com","www.youtube.com"):
            raise ValueError("untrusted_feed_response_host")
        content_type=response.headers.get("Content-Type","").lower()
        if not any(t in content_type for t in ("xml","atom","text/plain")):
            raise ValueError("response_not_atom_feed")
        data=response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:
            raise ValueError("rss_feed_exceeds_limit")
    return data


def _published(value):
    if not value:return None
    try:
        date=datetime.fromisoformat(value.strip().replace("Z","+00:00"))
        return date if date.tzinfo else None
    except (ValueError,TypeError):
        return None


def _racing_title(title):
    return bool(re.search(r"(レース|競走|LIVE|ライブ|展示|三国|BOAT)",title,re.IGNORECASE))


def _date_in_title(title, day):
    yyyy,mm,dd=day.split("-")
    tokens=(day, f"{yyyy}/{mm}/{dd}",f"{yyyy}.{mm}.{dd}",f"{yyyy}年{int(mm)}月{int(dd)}日",
            f"{int(mm)}月{int(dd)}日",f"{int(mm)}/{int(dd)}",f"{int(mm):02d}/{int(dd):02d}")
    return any(token in title for token in tokens)


def parse_feed(feed, day):
    """Accept only this channel's entries; never guess video IDs from page HTML."""
    datetime.strptime(day,"%Y-%m-%d")
    if isinstance(feed,str):
        feed=feed.encode("utf-8")
    if not isinstance(feed,bytes) or len(feed)>MAX_BYTES:
        raise ValueError("invalid_feed_size")
    if b"<!DOCTYPE" in feed.upper() or b"<!ENTITY" in feed.upper():
        raise ValueError("disallowed_xml_entity")
    try:
        root=ElementTree.fromstring(feed)
    except ElementTree.ParseError as exc:
        raise ValueError("invalid_atom_xml") from exc
    if root.tag!="{http://www.w3.org/2005/Atom}feed":
        raise ValueError("not_atom_feed")
    channel=root.findtext("yt:channelId",namespaces=NS)
    if channel!=CHANNEL_ID:
        raise ValueError("wrong_official_channel")
    candidates=[]
    seen=set()
    for item in root.findall("atom:entry",NS):
        vid=(item.findtext("yt:videoId",namespaces=NS) or "").strip()
        title=(item.findtext("atom:title",namespaces=NS) or "").strip()
        creator=(item.findtext("atom:author/atom:name",namespaces=NS) or "").strip()
        entry_channel=item.findtext("yt:channelId",namespaces=NS)
        stamp=_published(item.findtext("atom:published",namespaces=NS))
        if (not re.fullmatch(r"[A-Za-z0-9_-]{11}",vid) or vid in seen
            or entry_channel not in (None,CHANNEL_ID) or not title):
            continue
        seen.add(vid)
        published_jst=stamp.astimezone(JST).date().isoformat() if stamp else None
        matches=_date_in_title(title,day) or (
            published_jst==day and _racing_title(title))
        if matches:
            candidates.append({
                "video_id":vid,"title":title[:180],
                "published_utc":stamp.astimezone(timezone.utc).isoformat() if stamp else None,
                "channel_author":creator[:100],
                "official_watch_url":f"https://www.youtube.com/watch?v={vid}",
                "classification":"CANDIDATE_ONLY_NOT_VERIFIED_RACE_OR_PLAYABLE_VIDEO",
                "race_number":None,
                "video_frames_analyzed":0,
            })
    return {"entries_in_feed":len(root.findall("atom:entry",NS)),
            "candidates":candidates[:20]}


def _failure_reason(exc):
    if isinstance(exc,HTTPError):
        return "YOUTUBE_RSS_HTTP_"+str(exc.code)
    if isinstance(exc,(URLError,TimeoutError,OSError)):
        return "YOUTUBE_RSS_NETWORK_UNAVAILABLE"
    if isinstance(exc,ValueError):
        if str(exc) in {"invalid_atom_xml","not_atom_feed","wrong_official_channel",
                        "disallowed_xml_entity","invalid_feed_size","rss_feed_exceeds_limit",
                        "response_not_atom_feed","untrusted_feed_response_host",
                        "youtube_rss_redirect_to_untrusted_host"}:
            return str(exc).upper()
        return "FEED_VALIDATION_ERROR"
    return "UNEXPECTED_CATALOG_ERROR"


def build(day, previous=None, feed_fetcher=request_feed, now=None):
    datetime.strptime(day,"%Y-%m-%d")
    timestamp=now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("timestamp_requires_timezone")
    old=previous if isinstance(previous,dict) and previous.get("schema")==SCHEMA and previous.get("event_date")==day else None
    # Keep previously independently observed entries if later RSS pages rotate.
    stored={c["video_id"]:c for c in (old or {}).get("candidates",[])
            if isinstance(c,dict) and re.fullmatch(r"[A-Za-z0-9_-]{11}",str(c.get("video_id","")))}
    try:
        outcome=parse_feed(feed_fetcher(),day)
        state="OFFICIAL_CHANNEL_RSS_METADATA_READ"
        reason=None
        for row in outcome["candidates"]:
            stored[row["video_id"]]=row
        count=outcome["entries_in_feed"]
    except (HTTPError,URLError,TimeoutError,OSError,ValueError) as exc:
        state="RSS_UNAVAILABLE_OR_UNVERIFIED"
        reason=_failure_reason(exc)
        count=None
    return {
        "schema":SCHEMA,
        "event_date":day,
        "venue":"三国","venue_code":"10",
        "channel_url":CHANNEL_URL,
        "channel_id":CHANNEL_ID,
        "source_url":FEED_URL,
        "official_2025_video_rules":RULES_URL,
        "source_kind":"OFFICIAL_YOUTUBE_RSS_METADATA_ONLY",
        "source_status":state,
        "failure_reason":reason,
        "checked_at_utc":timestamp.astimezone(timezone.utc).isoformat(),
        "entries_in_current_feed":count,
        "candidate_count":len(stored),
        "candidates":list(stored.values()),
        "video_bytes_downloaded":0,
        "video_frames_analyzed":0,
        "six_boats_identified":0,
        "turn_geometry_verified":0,
        "post_start_stretch_verified":0,
        "may_download_youtube_content":False,
        "note":"No direct MP4 URL or YouTube downloader is provided. This is a public metadata discovery ledger, not media capture or replay verification.",
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description="Official Mikuni channel metadata discovery only")
    parser.add_argument("--date",default=datetime.now(JST).date().isoformat())
    parser.add_argument("--out",type=Path)
    args=parser.parse_args(argv)
    out=args.out or Path(f"app/data/experiments/mikuni-video-catalog-{args.date}.json")
    try:
        old=json.loads(out.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        old=None
    result=build(args.date,old)
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(out)
    print(json.dumps({"status":result["source_status"],"candidates":result["candidate_count"],
                      "frames_analyzed":0,"downloaded":False},ensure_ascii=False))


if __name__=="__main__":
    main()
