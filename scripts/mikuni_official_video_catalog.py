"""Read-only catalog of the venue-specified *official* Mikuni YouTube channel.

The venue's published 2025-04-01 video-use rules identify this channel.
This collector requests only Atom/RSS metadata (titles, publication dates, IDs);
it never downloads or decodes videos, fetches HLS segments, uses yt-dlp,
bypasses a protected stream, or assumes third-party download permission.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlencode
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from xml.etree import ElementTree

CHANNEL_ID="UCu-yP6WJQ0zcx5nmWhxvJEg"
CHANNEL_URL=f"https://www.youtube.com/channel/{CHANNEL_ID}"
FEED_URL=f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
FEED_ALTERNATES=(
    f"https://youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}",
)
OFFICIAL_API_HOST="www.googleapis.com"
OFFICIAL_API_KEY_ENV="MIKUNI_YOUTUBE_DATA_API_KEY"
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
    """Query official public channel Atom metadata, with a hostname fallback.

    YouTube RSS 404 can be transient for a valid live channel. Avoid treating
    one 404 as evidence the channel no longer exists. No video media fetched.
    """
    opener=build_opener(HTTPSHandler(),RestrictedFeedRedirect())
    last_error=None
    for url in (FEED_URL,)+FEED_ALTERNATES:
        request=Request(url,headers={"User-Agent":"BOAT-LAB-official-video-metadata-research/1.0",
                                     "Accept":"application/atom+xml,application/xml,text/xml"})
        try:
            with opener.open(request,timeout=9) as response:
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
        except (HTTPError,URLError,TimeoutError) as error:
            last_error=error
    if last_error:
        raise last_error
    raise ValueError("youtube_rss_sources_unavailable")



class GoogleAPIHostRedirect(HTTPRedirectHandler):
    """YouTube official metadata API cannot redirect to another host."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed=urlparse(newurl)
        if parsed.scheme!="https" or parsed.hostname!=OFFICIAL_API_HOST:
            raise ValueError("unapproved_youtube_api_redirect")
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def _get_api_json(path,params,key):
    """Only public metadata from Google's official Data API v3."""
    if path not in ("channels","playlistItems"):
        raise ValueError("unapproved_youtube_api_method")
    if not isinstance(key,str) or not key or len(key)>512:
        raise ValueError("youtube_api_key_missing")
    query=urlencode({**params,"key":key})
    url="https://www.googleapis.com/youtube/v3/"+path+"?"+query
    request=Request(url,headers={"Accept":"application/json",
                                "User-Agent":"BOAT-LAB-official-metadata-client/1.0"})
    opener=build_opener(HTTPSHandler(),GoogleAPIHostRedirect())
    with opener.open(request,timeout=12) as response:
        target=urlparse(response.geturl())
        if target.scheme!="https" or target.hostname!=OFFICIAL_API_HOST:
            raise ValueError("unapproved_youtube_api_host")
        if "json" not in response.headers.get("Content-Type","").lower():
            raise ValueError("youtube_api_not_json")
        data=response.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError("youtube_api_response_too_large")
    parsed=json.loads(data)
    if not isinstance(parsed,dict) or not isinstance(parsed.get("items"),list):
        raise ValueError("youtube_api_invalid_response")
    return parsed


def request_official_api(api_key):
    """Official YouTube Data API key; channel and upload playlist metadata only.

    2 low-cost list requests (1 quota unit each) if properly configured.
    Data API has no supported method to download third-party YouTube videos.
    """
    channel=_get_api_json("channels",{
        "part":"contentDetails",
        "id":CHANNEL_ID,
        "maxResults":"1",
    },api_key)
    items=channel["items"]
    if len(items)!=1 or items[0].get("id")!=CHANNEL_ID:
        raise ValueError("youtube_api_wrong_channel")
    playlist=(items[0].get("contentDetails",{}).get("relatedPlaylists",{})
              .get("uploads"))
    if not isinstance(playlist,str) or not re.fullmatch(r"[A-Za-z0-9_-]{24,64}",playlist):
        raise ValueError("youtube_uploads_playlist_missing")
    uploads=_get_api_json("playlistItems",{
        "part":"snippet,contentDetails",
        "playlistId":playlist,
        "maxResults":"50",
    },api_key)
    return uploads


def parse_official_api(response,day):
    """All candidate videos must belong to the venue's verified channel."""
    datetime.strptime(day,"%Y-%m-%d")
    if not isinstance(response,dict) or not isinstance(response.get("items"),list):
        raise ValueError("youtube_api_invalid_response")
    seen=set();candidates=[]
    for row in response["items"][:50]:
        if not isinstance(row,dict):continue
        snippet=row.get("snippet") or {}
        if not isinstance(snippet,dict):continue
        ident=(snippet.get("resourceId") or {}).get("videoId")
        owner=snippet.get("videoOwnerChannelId")
        # Reject unknown owners rather than silently treating playlist
        # memberships or another channel's clip as an official Mikuni upload.
        if owner!=CHANNEL_ID or not isinstance(ident,str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}",ident) or ident in seen:
            continue
        seen.add(ident)
        title=snippet.get("title")
        if not isinstance(title,str) or not title.strip():continue
        published=_published((row.get("contentDetails") or {}).get("videoPublishedAt") or
                             snippet.get("publishedAt"))
        published_day=published.astimezone(JST).date().isoformat() if published else None
        if not (_date_in_title(title,day) or (published_day==day and _racing_title(title))):
            continue
        candidates.append({
            "video_id":ident,"title":title[:180],
            "published_utc":published.astimezone(timezone.utc).isoformat() if published else None,
            "channel_author":"「公式」ボートレース三国",
            "official_watch_url":f"https://www.youtube.com/watch?v={ident}",
            "classification":"CANDIDATE_ONLY_NOT_VERIFIED_RACE_OR_PLAYABLE_VIDEO",
            "race_number":None,"video_frames_analyzed":0,
        })
    return {"entries_in_feed":len(response["items"]),"candidates":candidates[:20]}


def _published(value):
    if not value:return None
    try:
        date=datetime.fromisoformat(value.strip().replace("Z","+00:00"))
        return date if date.tzinfo else None
    except (ValueError,TypeError):
        return None


def _racing_title(title):
    return bool(re.search(r"(レース|競走|LIVE|ライブ|展示|三国|BOAT|最終日|初日|[2-6２-６]日目|杯|優勝戦|決勝)",title,re.IGNORECASE))


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
                        "youtube_api_wrong_channel","youtube_uploads_playlist_missing",
                        "youtube_api_invalid_response","youtube_api_response_too_large",
                        "youtube_api_not_json","youtube_api_key_missing",
                        "unapproved_youtube_api_host","unapproved_youtube_api_redirect",
                        "disallowed_xml_entity","invalid_feed_size","rss_feed_exceeds_limit",
                        "response_not_atom_feed","untrusted_feed_response_host",
                        "youtube_rss_redirect_to_untrusted_host"}:
            return str(exc).upper()
        return "FEED_VALIDATION_ERROR"
    return "UNEXPECTED_CATALOG_ERROR"


def build(day, previous=None, feed_fetcher=request_feed, now=None,
          api_key=None, api_fetcher=request_official_api):
    datetime.strptime(day,"%Y-%m-%d")
    timestamp=now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("timestamp_requires_timezone")
    old=previous if isinstance(previous,dict) and previous.get("schema")==SCHEMA and previous.get("event_date")==day else None
    # Keep previously independently observed entries if later RSS pages rotate.
    stored={c["video_id"]:c for c in (old or {}).get("candidates",[])
            if isinstance(c,dict) and re.fullmatch(r"[A-Za-z0-9_-]{11}",str(c.get("video_id","")))}
    source_kind="OFFICIAL_YOUTUBE_RSS_METADATA_ONLY"
    attempted_api=False
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
        if api_key:
            attempted_api=True
            try:
                outcome=parse_official_api(api_fetcher(api_key),day)
                source_kind="OFFICIAL_YOUTUBE_DATA_API_METADATA_ONLY"
                state="OFFICIAL_YOUTUBE_DATA_API_METADATA_READ"
                count=outcome["entries_in_feed"]
                for row in outcome["candidates"]:
                    stored[row["video_id"]]=row
            except (HTTPError,URLError,TimeoutError,OSError,ValueError,TypeError) as api_exc:
                # No URL/key/token or upstream response body is ever exposed.
                state="RSS_AND_API_UNAVAILABLE"
                reason=reason+";API_METADATA_UNAVAILABLE"
    
    return {
        "schema":SCHEMA,
        "event_date":day,
        "venue":"三国","venue_code":"10",
        "channel_url":CHANNEL_URL,
        "channel_id":CHANNEL_ID,
        "source_url":FEED_URL,
        "official_2025_video_rules":RULES_URL,
        "source_kind":source_kind,
        "api_fallback_configured":bool(api_key),
        "api_fallback_attempted":attempted_api,
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
    api_key=os.environ.get(OFFICIAL_API_KEY_ENV,"").strip()
    result=build(args.date,old,api_key=api_key)
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(out)
    print(json.dumps({"status":result["source_status"],"candidates":result["candidate_count"],
                      "frames_analyzed":0,"downloaded":False},ensure_ascii=False))


if __name__=="__main__":
    main()
