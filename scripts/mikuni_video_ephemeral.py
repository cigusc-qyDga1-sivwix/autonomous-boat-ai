"""Mikuni research: HTTPS direct media -> bounded memory -> FFmpeg frames -> numeric audit.

No persistent video or frames. The provider must supply a *direct* approved
media URL (MIKUNI_VIDEO_SOURCE_TEMPLATE / MIKUNI_VIDEO_ALLOWED_HOSTS).
No player scraping, HLS token guessing, copyright bypass, DRM handling or
download from YouTube/JLC via unofficial means.

Default processing needs no boat/shore clicks: automatic colour candidates
and background-camera estimation run on every decoded clip. Identities and
physical motion remain unverified until tested on real calibrated footage.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPSHandler

from scripts.mikuni_video_autocollect import (
    SCHEMA, VENUE_CODE, MAX_VIDEO_BYTES, ACCEPTED_TYPES, StrictRedirect,
    _check_url, _media_magic, _rows, media_url, _reason, _valid_host,
)
from scripts.mikuni_auto_vision import (
    MODEL as AUTO_VISION_MODEL, analyze_automatic_frames, propose_clip_starts,
)

FRAME_LIMIT=48
FFMPEG_TIMEOUT_S=35
JPEG_OUTPUT_LIMIT=16*1024*1024
SAMPLE_GAP_SECONDS=0.5
RESEARCH_MODEL="mikuni-ephemeral-unattended-candidates-v0.3"
COLORS={
    "red_candidate":[((0,90,70),(10,255,255)),((170,90,70),(179,255,255))],
    "blue_candidate":[((95,90,60),(130,255,255))],
    "yellow_candidate":[((18,90,90),(40,255,255))],
    "green_candidate":[((40,75,55),(90,255,255))],
}


def receive_approved_video(url, allowed_hosts):
    """Read only media bytes into RAM; limit size and reject HTML/HLS/redirects."""
    _check_url(url,allowed_hosts)
    req=Request(url,headers={
        "Accept":"video/mp4,video/webm,video/quicktime,video/x-msvideo",
        "User-Agent":"BOAT-LAB-venue-authorized-ephemeral-video-research/0.1",
    })
    opener=build_opener(HTTPSHandler(),StrictRedirect(allowed_hosts))
    with opener.open(req,timeout=14) as response:
        _check_url(response.geturl(),allowed_hosts)
        content_type=response.headers.get("Content-Type","").split(";",1)[0].lower().strip()
        if content_type not in ACCEPTED_TYPES:
            raise ValueError("not_direct_video_media")
        length=response.headers.get("Content-Length")
        if length and length.isdigit() and int(length)>MAX_VIDEO_BYTES:
            raise ValueError("video_too_large")
        first=response.read(32)
        if not _media_magic(first):
            raise ValueError("not_recognized_direct_video_container")
        sink=io.BytesIO()
        sink.write(first)
        while True:
            chunk=response.read(1048576)
            if not chunk:break
            if sink.tell()+len(chunk)>MAX_VIDEO_BYTES:
                raise ValueError("video_too_large")
            sink.write(chunk)
    blob=sink.getvalue()
    return blob,{"sha256":hashlib.sha256(blob).hexdigest(),
                 "file_size":len(blob),"content_type":content_type}


def _split_jpegs(jpeg_stream):
    """Extract bounded JPEG images from FFmpeg stdout (not saved to disk)."""
    if len(jpeg_stream)>JPEG_OUTPUT_LIMIT:
        raise ValueError("video_frame_output_too_large")
    cursor=0
    images=[]
    while len(images)<FRAME_LIMIT:
        start=jpeg_stream.find(b"\xff\xd8",cursor)
        if start<0:break
        end=jpeg_stream.find(b"\xff\xd9",start+2)
        if end<0:break
        images.append(jpeg_stream[start:end+2])
        cursor=end+2
    if not images:raise ValueError("video_no_decodable_frames")
    return images


def decode_in_memory(blob, *, runner=subprocess.run, start_seconds=0, sample_interval_s=.5):
    """FFmpeg reads from stdin; scaled JPEG frames from stdout, never a file.

    FFmpeg executable must be installed on the runner. Results are capped.
    The input bytes are transient and are discarded after processing.
    """
    if not isinstance(blob,bytes) or not blob or len(blob)>MAX_VIDEO_BYTES or not _media_magic(blob[:32]):
        raise ValueError("not_recognized_direct_video_container")
    if (isinstance(start_seconds,bool) or not isinstance(start_seconds,(int,float))
        or not math.isfinite(start_seconds) or not 0<=start_seconds<=300):
        raise ValueError("clip_start_seconds_invalid")
    if (isinstance(sample_interval_s,bool) or not isinstance(sample_interval_s,(int,float))
        or not math.isfinite(sample_interval_s) or not .1<=sample_interval_s<=10):
        raise ValueError("decode_sample_interval_invalid")
    args=["ffmpeg","-hide_banner","-loglevel","error",
          "-nostdin","-i","pipe:0",
          "-an","-sn","-dn",
          "-ss",f"{start_seconds:.3f}",
          "-vf",f"fps={1/sample_interval_s:.6g},scale='min(640,iw)':-2",
          "-frames:v",str(FRAME_LIMIT),
          "-f","image2pipe","-vcodec","mjpeg","pipe:1"]
    try:
        result=runner(args,input=blob,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                      timeout=FFMPEG_TIMEOUT_S,check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg_not_available") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffmpeg_timed_out") from exc
    if result.returncode!=0:
        # Some MP4 moov indices need seeking, which regular stdin cannot do.
        # Linux anonymous memfd is seekable RAM (not a persistent video file).
        # Never write video to /tmp or the repository.
        if not hasattr(os,"memfd_create"):
            raise ValueError("video_decode_failed")
        fd=os.memfd_create("boatlabs-ephemeral-video",flags=0)
        try:
            offset=0
            while offset<len(blob):
                written=os.write(fd,blob[offset:offset+1048576])
                if written<=0:raise ValueError("in_memory_video_write_failed")
                offset+=written
            os.lseek(fd,0,os.SEEK_SET)
            fd_args=[a if a!="pipe:0" else f"/proc/self/fd/{fd}" for a in args]
            try:
                result=runner(fd_args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              timeout=FFMPEG_TIMEOUT_S,check=False,pass_fds=(fd,))
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("ffmpeg_timed_out") from exc
            if result.returncode!=0:
                raise ValueError("video_decode_failed")
        finally:
            os.close(fd)
    return _split_jpegs(result.stdout)


def numerical_motion_candidates(jpeg_images):
    """Per-frame colour-region center candidates in *pixel* units only.

    Camera pans, water reflections and on-screen graphics are not masked.
    Therefore delta px/s is NOT speed and colours are NOT boat IDs.
    """
    import cv2
    import numpy as np
    points={name:[] for name in COLORS}
    valid_frames=0
    for i,jpg in enumerate(jpeg_images[:FRAME_LIMIT]):
        if not isinstance(jpg,bytes):continue
        frame=cv2.imdecode(np.frombuffer(jpg,dtype=np.uint8),cv2.IMREAD_COLOR)
        if frame is None:continue
        valid_frames+=1
        h,w=frame.shape[:2]
        if w<30 or h<30:continue
        hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
        for name,ranges in COLORS.items():
            mask=np.zeros((h,w),dtype=np.uint8)
            for low,high in ranges:
                mask=cv2.bitwise_or(mask,cv2.inRange(hsv,low,high))
            kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3))
            mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,kernel)
            contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            regions=[]
            for contour in contours:
                area=cv2.contourArea(contour)
                if not 18<=area<=h*w*.03:continue
                moment=cv2.moments(contour)
                if moment["m00"]<=0:continue
                regions.append((area,round(moment["m10"]/moment["m00"],1),
                               round(moment["m01"]/moment["m00"],1)))
            # Multiple regions make an unambiguous boat track impossible.
            if len(regions)==1:
                area,x,y=regions[0]
                points[name].append({"frame":i,"t_s":round(i*SAMPLE_GAP_SECONDS,2),
                                     "pixel_center":[x,y],"region_area_px":round(area,1)})
    if not valid_frames:raise ValueError("video_no_decodable_frames")
    summaries={}
    for name,track in points.items():
        step_lengths=[]
        for a,b in zip(track,track[1:]):
            if b["frame"]!=a["frame"]+1:continue
            d=math.hypot(b["pixel_center"][0]-a["pixel_center"][0],
                         b["pixel_center"][1]-a["pixel_center"][1])
            step_lengths.append(round(d/SAMPLE_GAP_SECONDS,2))
        summaries[name]={
            "unverified_color_region_samples":len(track),
            "candidate_pixel_center_first":track[0]["pixel_center"] if track else None,
            "candidate_pixel_center_last":track[-1]["pixel_center"] if track else None,
            "median_apparent_motion_px_per_s":sorted(step_lengths)[len(step_lengths)//2] if step_lengths else None,
            "confirmed_boat_id":None,
            "camera_motion_compensated":False,
        }
    return {
        "status":"UNVERIFIED_PIXEL_MOTION_ONLY",
        "sampled_frames":valid_frames,
        "sample_gap_seconds":SAMPLE_GAP_SECONDS,
        "candidate_colors":summaries,
        "confirmed_boat_tracks":0,
        "turn_metrics_measured":0,
        "post_start_stretch_measured":0,
        "calibrated_water_plane":False,
        "note":"Apparent pixel motion may be camera pan, overlay or wake. Not validated six-boat speed, ST or turn.",
    }


def analyze_bytes(blob, *, seed_record=None, source_sha256=None):
    """Automatically sample, detect and track; optional historical seed baseline.

    Optional historical labels only affect the separate seeded comparison.
    Invalid historical seeds never block the unattended analysis path.
    """
    preview=decode_in_memory(blob,sample_interval_s=5)
    starts=propose_clip_starts(preview)
    best=None
    for start in starts:
        images=decode_in_memory(blob,start_seconds=start)
        automatic=analyze_automatic_frames(images,sample_interval_s=SAMPLE_GAP_SECONDS)
        score=(automatic["candidate_boat_tracks"],automatic["camera_stabilized_frames"])
        if best is None or score>best[0]:
            best=(score,start,images,automatic)
    _,clip_start,images,automatic=best
    audit=numerical_motion_candidates(images)
    audit["automatic_tracking_candidate"]=automatic
    audit["automatic_clip_selection"]={
        "preview_sample_interval_s":5,"candidate_starts_s":starts,
        "selected_start_s":clip_start,"manual_start_required":False,
    }
    audit["automatic_tracking_status"]="AUTOMATIC_CANDIDATES_COMPUTED"
    audit["manual_inputs_required"]=0
    if seed_record is not None:
        try:
            seed_start=seed_record.get("clip_start_seconds",0) if isinstance(seed_record,dict) else 0
            interval=seed_record.get("sample_interval_s") if isinstance(seed_record,dict) else None
            if (isinstance(interval,bool) or not isinstance(interval,(int,float)) or
                not math.isfinite(interval) or abs(interval-SAMPLE_GAP_SECONDS)>.0001):
                raise ValueError("annotation_sample_interval_does_not_match_decoder")
            from scripts.mikuni_six_boat_tracker import track_seeded_frames
            seed_images=decode_in_memory(blob,start_seconds=seed_start)
            candidate=track_seeded_frames(seed_images,seed_record,source_sha256)
            audit["six_boat_seeded_tracking_candidate"]=candidate
            audit["seeded_tracking_status"]="UNVERIFIED_CANDIDATE_COMPUTED"
        except (ValueError,RuntimeError,TypeError,KeyError) as exc:
            audit["seeded_tracking_status"]="SEED_INVALID_OR_TRACKING_UNAVAILABLE"
            audit["seeded_tracking_error_class"]=type(exc).__name__
    else:
        audit["seeded_tracking_status"]="NO_SIX_BOAT_SEEDS"
    return audit


def select_seed_record(seed_library,day,race,video_sha):
    """Never apply a seed set to another venue/date/race/video digest."""
    if (not isinstance(seed_library,dict)
        or seed_library.get("schema")!="boatlabs.mikuni_seed_library.v0.1"
        or seed_library.get("event_date")!=day
        or seed_library.get("venue_code")!="10"):
        return None
    matches=[r for r in seed_library.get("records",[]) if
             isinstance(r,dict) and r.get("race")==race and
             r.get("event_date")==day and r.get("venue_code")=="10"
             and r.get("source_sha256")==video_sha]
    return matches[0] if len(matches)==1 else None


def collect(day,archive,previous,template,hosts,*,now=None,
            receiver=receive_approved_video,analyzer=analyze_bytes,
            seed_library=None):
    """Incremental observation without retaining raw video, tracks or money."""
    datetime.strptime(day,"%Y-%m-%d")
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("timezone_required")
    hosts={h.strip().lower() for h in hosts
           if isinstance(h,str) and _valid_host(h.strip().lower())}
    known=_rows(archive,day)
    old=(previous.get("races",{}) if isinstance(previous,dict)
         and previous.get("schema")==SCHEMA and previous.get("event_date")==day else {})
    races={}
    for race in range(1,13):
        r=str(race)
        old_record=old.get(r) if isinstance(old.get(r),dict) else None
        seed_reprocess=(old_record and
            old_record.get("status")=="MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY"
            and isinstance(old_record.get("source_sha256"),str)
            and select_seed_record(seed_library,day,race,old_record["source_sha256"]) is not None
            and (old_record.get("video_observation") or {}).get("seeded_tracking_status")!="UNVERIFIED_CANDIDATE_COMPUTED")
        old_auto_model=(((old_record or {}).get("video_observation") or {})
                        .get("automatic_tracking_candidate") or {}).get("model")
        auto_reprocess=(analyzer is analyze_bytes and old_record and
            old_record.get("status")=="MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY"
            and isinstance(old_record.get("source_sha256"),str)
            and old_auto_model!=AUTO_VISION_MODEL)
        eligible_reprocess=seed_reprocess or auto_reprocess
        if old_record and old_record.get("status")=="MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY" and not eligible_reprocess:
            races[r]=old_record
            continue
        if race not in known:
            races[r]={"status":"AWAITING_EXHIBITION_NUMERIC_RESEARCH_ROW"}
            continue
        if not template or not hosts:
            if old_record and old_record.get("status")=="MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY":
                races[r]={**old_record,"seed_reprocess_status":"AUTHORIZED_SOURCE_NOT_CONFIGURED",
                          "analysis_reprocess_status":"AUTHORIZED_SOURCE_NOT_CONFIGURED"}
            else:
                races[r]={"status":"AUTHORIZED_SOURCE_CONFIGURATION_MISSING"}
            continue
        try:
            address=media_url(template,day,race,hosts)
            blob,metadata=receiver(address,hosts)
            if not isinstance(blob,bytes) or not _media_magic(blob[:32]):
                raise ValueError("not_recognized_direct_video_container")
            if eligible_reprocess and metadata["sha256"]!=old_record["source_sha256"]:
                races[r]={**old_record,"seed_reprocess_status":"VIDEO_SOURCE_SHA_CHANGED_NO_REPROCESS",
                          "analysis_reprocess_status":"VIDEO_SOURCE_SHA_CHANGED_NO_REPROCESS"}
                continue
            seed=select_seed_record(seed_library,day,race,metadata["sha256"])
            if seed is None:
                stats=analyzer(blob)
            elif analyzer is analyze_bytes:
                stats=analyzer(blob,seed_record=seed,source_sha256=metadata["sha256"])
            else:
                # Test replacements cannot claim to produce validated tracks.
                stats=analyzer(blob)
            # Never write binary source or decoded frames to Git or log URL.
            del blob
            races[r]={
                "status":"MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY",
                "registered_to_race_key":day.replace("-","")+VENUE_CODE+f"{race:02d}",
                "captured_at_utc":now.astimezone(timezone.utc).isoformat(),
                "source_sha256":metadata["sha256"],
                "media_bytes":metadata["file_size"],
                "content_type":metadata.get("content_type"),
                "video_observation":stats,
                "not_formal_frozen_forecast":True,
            }
        except (HTTPError,URLError,ValueError,RuntimeError,OSError,TimeoutError,KeyError,TypeError) as exc:
            if eligible_reprocess:
                races[r]={**old_record,"seed_reprocess_status":"REPROCESS_UNAVAILABLE_OR_ERROR",
                          "analysis_reprocess_status":"REPROCESS_UNAVAILABLE_OR_ERROR"}
                continue
            error=_reason(exc)
            if error=="COLLECTOR_FAILED_REDACTED" or error=="VIDEO_VALIDATION_FAILED":
                error="VIDEO_SOURCE_OR_DECODE_UNAVAILABLE"
            races[r]={"status":"SOURCE_OR_ANALYSIS_NOT_READY","reason":error}
    return {
        "schema":SCHEMA,
        "event_date":day,"venue":"三国","venue_code":VENUE_CODE,
        "permission_provenance":"USER_REPORTED_VENUE_PERMISSION_PERSONAL_AUTO_ANALYSIS_NO_REPOST",
        "independent_distributor_rights":"DIRECT_MEDIA_PROVIDER_APPROVAL_REQUIRED",
        "storage":"MEMORY_ONLY_INPUT_NO_VIDEO_FRAMES_PERSISTED",
        "research_model":RESEARCH_MODEL,
        "use":"PIXEL_RESEARCH_ONLY_NO_FORMAL_FORECAST_NO_BETS_NO_RESULTS",
        "source_configured":bool(template and hosts),
        "automation_mode":"UNATTENDED_NO_MANUAL_BOAT_OR_SHORE_SEEDS_REQUIRED",
        "input_connection_status":"CONFIGURED" if template and hosts else "DIRECT_MEDIA_SOURCE_REQUIRED",
        "races":races,
        "summary":{
            "exhibition_rows_seen":len(known),
            "video_races_observed":sum(v.get("status")=="MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY" for v in races.values()),
            "automatic_candidate_races":sum(
                (v.get("video_observation") or {}).get("automatic_tracking_status")=="AUTOMATIC_CANDIDATES_COMPUTED"
                for v in races.values()),
            "automatic_six_candidate_races":sum(
                ((v.get("video_observation") or {}).get("automatic_tracking_candidate") or {})
                  .get("all_six_candidates_supported") is True for v in races.values()),
            "seeded_motion_candidate_races":sum(
                (v.get("video_observation") or {}).get("seeded_tracking_status")=="UNVERIFIED_CANDIDATE_COMPUTED"
                for v in races.values()),
            "full_six_seeded_candidate_races":sum(
                ((v.get("video_observation") or {}).get("six_boat_seeded_tracking_candidate") or {})
                  .get("candidate_fully_tracked_boats")==6 for v in races.values()),
            "confirmed_boat_tracks":0,
            "measured_turns":0,
            "measured_post_start_stretches":0,
            "ready_for_trained_video_model":False,
        },
    }


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--date",default=datetime.now(timezone.utc).astimezone(
        timezone(__import__("datetime").timedelta(hours=9))).date().isoformat())
    parser.add_argument("--exhibition",type=Path)
    parser.add_argument("--out",type=Path)
    args=parser.parse_args(argv)
    source=args.exhibition or Path(f"app/data/exhibition/{args.date}.json")
    dest=args.out or Path(f"app/data/experiments/mikuni-video-auto-{args.date}.json")
    try:archive=json.loads(source.read_text(encoding="utf-8"))
    except (OSError,ValueError):archive=None
    try:previous=json.loads(dest.read_text(encoding="utf-8"))
    except (OSError,ValueError):previous=None
    template=os.environ.get("MIKUNI_VIDEO_SOURCE_TEMPLATE","").strip()
    hosts=os.environ.get("MIKUNI_VIDEO_ALLOWED_HOSTS","").split(",")
    annotations=Path(f"app/data/experiments/mikuni-6boat-seeds-{args.date}.json")
    try:seed_library=json.loads(annotations.read_text(encoding="utf-8"))
    except (OSError,ValueError):seed_library=None
    result=collect(args.date,archive,previous,template,hosts,seed_library=seed_library)
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists() or dest.read_text(encoding="utf-8")!=json.dumps(result,ensure_ascii=False,indent=2)+"\n":
        output=dest.with_suffix(".tmp")
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        output.replace(dest)
    print(json.dumps({
        "schema":SCHEMA,"date":args.date,"source_configured":result["source_configured"],
        "video_races_observed":result["summary"]["video_races_observed"],
        "confirmed_boat_tracks":0,"video_bytes_persisted":0,
    },ensure_ascii=False))


if __name__=="__main__":
    main()

