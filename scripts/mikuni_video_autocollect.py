"""Mikuni-only video auto-ingestion from an EXPLICITLY AUTHORIZED direct media feed.

Research-only. The venue's personally permitted use was user-reported, but
automated downloading from an independent distributor must be within that
distributor's terms too. No stream scraping, scraping dynamic URL tokens,
decrypting DRM, or guessing HLS segment URLs.

For unattended collection, the operator must configure an authorized direct
MP4/WebM/AVI URL template via MIKUNI_VIDEO_SOURCE_TEMPLATE (GitHub secret).
Only HTTPS media on explicitly authorized hostnames is accepted. Videos remain
ephemeral on CI runners; only a metadata audit is committed to Git.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler

JST=timezone(timedelta(hours=9))
SCHEMA="boatlabs.mikuni_authorized_video_ingestion.v1"
VENUE_CODE="10"
MAX_VIDEO_BYTES=120*1024*1024
ACCEPTED_TYPES=("video/mp4","video/quicktime","video/webm","video/x-msvideo",
                "application/octet-stream")
ENV_TEMPLATE="MIKUNI_VIDEO_SOURCE_TEMPLATE"
ENV_HOSTS="MIKUNI_VIDEO_ALLOWED_HOSTS"


def _valid_host(host):
    if not isinstance(host,str) or not host or len(host)>253:
        return False
    host=host.lower()
    if host in ("localhost","localhost.localdomain") or host.endswith(".local"):
        return False
    try:
        # Never accept a literal IP, including non-routable addresses.
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+",host):
        return False
    return all(label and len(label)<=63 and not label.startswith("-")
               and not label.endswith("-") for label in host.split("."))


def _check_url(url,allowed_hosts):
    parsed=urlparse(url)
    if (parsed.scheme!="https" or parsed.username is not None or
        parsed.password is not None or parsed.port not in (None,443) or
        parsed.fragment or not _valid_host(parsed.hostname) or
        parsed.hostname.lower() not in allowed_hosts):
        raise ValueError("unapproved_media_host_or_transport")
    if len(url)>4096 or not parsed.path.startswith("/"):
        raise ValueError("invalid_media_path")
    return parsed.hostname.lower()


class StrictRedirect(HTTPRedirectHandler):
    """Reject redirects to unexpected domains, plaintext or local targets."""
    def __init__(self,hosts):
        super().__init__()
        self.hosts=hosts
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        _check_url(newurl,self.hosts)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def media_url(template,day,race,allowed_hosts):
    if not isinstance(day,str) or not re.fullmatch(r"20\d\d-\d\d-\d\d",day):
        raise ValueError("invalid_date")
    datetime.strptime(day,"%Y-%m-%d")
    if isinstance(race,bool) or not isinstance(race,int) or not 1<=race<=12:
        raise ValueError("invalid_race")
    if not isinstance(template,str) or not template.startswith("https://"):
        raise ValueError("media_url_template_missing")
    # Do not construct from JLC/BOATCAST player internals. Only a direct
    # source which the owner explicitly provided to this collector.
    try:
        url=template.format(date=day,yyyymmdd=day.replace("-",""),
                            venue="mikuni",jcd=VENUE_CODE,race=race,
                            race2=f"{race:02d}")
    except (KeyError,IndexError,ValueError) as exc:
        raise ValueError("media_url_template_invalid") from exc
    _check_url(url,allowed_hosts)
    return url


def _media_magic(sample):
    return (len(sample)>=12 and sample[4:8]==b"ftyp" or
            sample.startswith(b"\x1a\x45\xdf\xa3") or
            sample.startswith(b"RIFF") and sample[8:12]==b"AVI ")


def fetch_media(url,target,allowed_hosts):
    """Use a directly supplied approved media URL, not a replay webpage."""
    _check_url(url,allowed_hosts)
    req=Request(url,headers={"User-Agent":"BOAT-LAB-personal-licensed-research/0.1",
                             "Accept":"video/mp4,video/webm,video/quicktime,video/x-msvideo"})
    opener=build_opener(HTTPSHandler(),StrictRedirect(allowed_hosts))
    sha=hashlib.sha256()
    with opener.open(req,timeout=14) as response:
        _check_url(response.geturl(),allowed_hosts)
        media_type=response.headers.get("Content-Type","").split(";",1)[0].strip().lower()
        if media_type not in ACCEPTED_TYPES:
            raise ValueError("not_direct_video_media")
        size_header=response.headers.get("Content-Length")
        if size_header and size_header.isdigit() and int(size_header)>MAX_VIDEO_BYTES:
            raise ValueError("video_too_large")
        first=response.read(32)
        if not _media_magic(first):
            raise ValueError("not_recognized_direct_video_container")
        count=0
        with target.open("wb") as output:
            chunk=first
            while chunk:
                count+=len(chunk)
                if count>MAX_VIDEO_BYTES:
                    raise ValueError("video_too_large")
                sha.update(chunk);output.write(chunk)
                chunk=response.read(1048576)
    return {"sha256":sha.hexdigest(),"file_size":count,"content_type":media_type}


def video_color_audit(video):
    """Experimental frame-level observations; never 6 racer identities."""
    try:
        import cv2
    except ImportError:
        raise RuntimeError("opencv_not_available")
    cap=cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError("video_decode_failed")
    try:
        fps=float(cap.get(cv2.CAP_PROP_FPS))
        frames_total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not 1<=fps<=240 or frames_total<1:
            raise ValueError("video_timing_unavailable")
        gap=max(1,round(fps*.6))
        sample=0; colour_frames=0; total_regions=0
        categories={"red_candidate":0,"blue_candidate":0,
                    "yellow_candidate":0,"green_candidate":0}
        for i in range(0,frames_total,gap):
            if sample>=40:break
            cap.set(cv2.CAP_PROP_POS_FRAMES,i)
            ok,frame=cap.read()
            if not ok:continue
            sample+=1
            h,w=frame.shape[:2]
            if not h or not w:continue
            scale=min(1.0,640/w)
            if scale<1:frame=cv2.resize(frame,(round(w*scale),round(h*scale)))
            hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
            ranges={
                "red_candidate":[((0,100,70),(10,255,255)),((170,100,70),(179,255,255))],
                "blue_candidate":[((96,95,60),(133,255,255))],
                "yellow_candidate":[((18,80,65),(40,255,255))],
                "green_candidate":[((41,75,55),(89,255,255))],
            }
            seen_here=False
            for key,edges in ranges.items():
                mask=None
                for low,high in edges:
                    x=cv2.inRange(hsv,low,high)
                    mask=x if mask is None else cv2.bitwise_or(mask,x)
                contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                count=sum(12<=cv2.contourArea(c)<=frame.shape[0]*frame.shape[1]*.05 for c in contours)
                categories[key]+=count
                total_regions+=count
                seen_here|=count>0
            colour_frames+=int(seen_here)
        if sample==0:
            raise ValueError("video_no_decodable_frames")
        return {
            "status":"PIXEL_RESEARCH_ONLY_NOT_BOAT_IDENTITIES",
            "sample_frames":sample,"frames_with_colour_candidates":colour_frames,
            "unverified_color_region_count":total_regions,
            "region_counts":categories,
            "verified_boats":0,"verified_turns":0,
            "verified_post_start_stretches":0,
            "estimated_turn_radius_m":None,"estimated_stretch_speed_mps":None,
            "note":"Colours are unverified pixel candidates. No six-boat IDs or calibrated turn marks.",
        }
    finally:
        cap.release()


def _rows(archive,day):
    if not isinstance(archive,dict) or archive.get("event_date")!=day:
        return set()
    return {int(row["race"]) for row in archive.get("records",[]) if
            isinstance(row,dict) and row.get("venue_code")==VENUE_CODE and
            row.get("race_code")==day.replace("-","")+VENUE_CODE+str(row.get("race")).zfill(2)
            and isinstance(row.get("race"),int) and row.get("race") in range(1,13)
            and isinstance(row.get("boats"),list) and len(row["boats"])==6}


def _reason(exc):
    if isinstance(exc,HTTPError):
        if exc.code==404:return "HTTP_404_NOT_READY"
        if exc.code==403:return "HTTP_403_SOURCE_RESTRICTED"
        return "HTTP_STATUS_"+str(exc.code)
    if isinstance(exc,URLError):return "NETWORK_UNAVAILABLE"
    if isinstance(exc,TimeoutError):return "NETWORK_TIMEOUT"
    if isinstance(exc,(ValueError,KeyError,TypeError)):
        return str(exc)[:100] if str(exc) in {
            "video_too_large","not_direct_video_media","not_recognized_direct_video_container",
            "video_decode_failed","video_timing_unavailable","video_no_decodable_frames",
            "unapproved_media_host_or_transport","invalid_media_path",
            "media_url_template_missing","media_url_template_invalid","opencv_not_available",
            "invalid_date","invalid_race"} else "VIDEO_VALIDATION_FAILED"
    return "COLLECTOR_FAILED_REDACTED"


def run(day,archive,previous,template,hosts,*,fetcher=fetch_media,analyzer=video_color_audit,now=None):
    """Build immutable research status; do not touch official forecast ledger."""
    datetime.strptime(day,"%Y-%m-%d")
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("timezone_required")
    prior=previous.get("races",{}) if isinstance(previous,dict) and (
          previous.get("schema")==SCHEMA and previous.get("event_date")==day) else {}
    hosts={h.lower().strip() for h in hosts if _valid_host(h.lower().strip())}
    observed=_rows(archive,day)
    races={}
    for race in range(1,13):
        key=str(race)
        old=prior.get(key) if isinstance(prior,dict) else None
        if isinstance(old,dict) and old.get("status")=="MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY":
            races[key]=old
            continue
        if race not in observed:
            races[key]={"status":"AWAITING_EXHIBITION_NUMERIC_RESEARCH_ROW"}
            continue
        if not template or not hosts:
            races[key]={"status":"AUTHORIZED_SOURCE_CONFIGURATION_MISSING"}
            continue
        try:
            url=media_url(template,day,race,hosts)
            with tempfile.TemporaryDirectory(prefix="mikuni-research-") as temp:
                source=Path(temp)/"licensed-video.mp4"
                data=fetcher(url,source,hosts)
                observed_pixels=analyzer(source)
            races[key]={
                "status":"MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY",
                "captured_at_utc":now.astimezone(timezone.utc).isoformat(),
                "source_sha256":data["sha256"],
                "media_bytes":data["file_size"],
                "content_type":data.get("content_type"),
                "video_observation":observed_pixels,
                "registered_to_race_key":day.replace("-","")+VENUE_CODE+f"{race:02d}",
                "not_formal_frozen_forecast":True,
            }
        except (ValueError,KeyError,TypeError,HTTPError,URLError,TimeoutError,RuntimeError,OSError) as exc:
            races[key]={"status":"SOURCE_OR_ANALYSIS_NOT_READY",
                        "reason":_reason(exc)}
    return {
        "schema":SCHEMA,"event_date":day,"venue":"三国","venue_code":VENUE_CODE,
        "permission_provenance":"USER_REPORTED_VENUE_VERBAL_CONSENT_PERSONAL_AUTOMATED_ANALYSIS_NO_REPOST",
        "independent_distributor_rights":"SOURCE_MUST_BE_EXPLICITLY_APPROVED_SEPARATELY",
        "storage":"EPHEMERAL_VIDEO_NO_RAW_MEDIA_IN_REPOSITORY",
        "use":"RESEARCH_ONLY_NO_FORECAST_CHANGES_NO_REAL_BETS",
        "source_configured":bool(template and hosts),
        "races":races,
        "summary":{
            "exhibition_rows_seen":len(observed),
            "video_races_observed":sum(r["status"]=="MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY" for r in races.values()),
            "confirmed_boat_tracks":0,"measured_turns":0,"measured_post_start_stretches":0,
            "ready_for_trained_video_model":False,
        }
    }


def main(argv=None):
    p=argparse.ArgumentParser(description="Mikuni licensed direct-video metadata collector")
    p.add_argument("--date",default=datetime.now(JST).date().isoformat())
    p.add_argument("--exhibition",type=Path)
    p.add_argument("--out",type=Path)
    args=p.parse_args(argv)
    archive_path=args.exhibition or Path(f"app/data/exhibition/{args.date}.json")
    output=args.out or Path(f"app/data/experiments/mikuni-video-auto-{args.date}.json")
    try:archive=json.loads(archive_path.read_text(encoding="utf-8"))
    except (OSError,ValueError):archive=None
    try:prior=json.loads(output.read_text(encoding="utf-8"))
    except (OSError,ValueError):prior=None
    template=os.environ.get(ENV_TEMPLATE,"").strip()
    hosts=os.environ.get(ENV_HOSTS,"").split(",")
    ledger=run(args.date,archive,prior,template,hosts)
    output.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(ledger,ensure_ascii=False,indent=2)+"\n"
    if not output.exists() or output.read_text(encoding="utf-8")!=content:
        temp=output.with_suffix(".tmp")
        temp.write_text(content,encoding="utf-8")
        temp.replace(output)
    print(json.dumps({"file":str(output),"date":args.date,
                      "source_configured":ledger["source_configured"],
                      "summary":ledger["summary"]},ensure_ascii=False))


if __name__=="__main__":
    main()
