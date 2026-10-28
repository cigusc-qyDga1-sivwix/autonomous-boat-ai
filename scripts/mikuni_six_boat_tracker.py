"""Research-only seeded six-boat motion tracker with static-scene stabilization.

Input: decoded JPEG frames from a *separately approved* video and user-provided
initial pixel seeds for boats 1..6 + >=6 static, visible world landmarks.
Uses LK forward/back optical flow and per-frame RANSAC homography of the fixed
shore points to subtract camera pan/zoom. Handles occlusions by dropping track
points rather than inventing positions or reassigning numbers.

OUTPUT IS A CANDIDATE TRACK LEDGER, never a verified six-boat record.
No race outcomes, automatic boat IDs, calibrated real-world speeds, or bets.
An independently reviewed source video, ID review, and surveyed water-plane
coordinates are needed before a separate human verification/promote step.
"""
from __future__ import annotations

from datetime import datetime
import math
import re

SCHEMA="boatlabs.mikuni_seeded_six_boat_pixel_tracks.v0.1"
SEED_SCHEMA="boatlabs.mikuni_video_seed_annotations.v0.1"
FRAME_LIMIT=48
SOURCE_VENUE_CODE="10"
MAX_LK_BACKTRACK_PX=2.5
MAX_LK_STEP_PX=90.0
MAX_CAMERA_REPROJECTION_PX=4.0
MIN_LANDMARKS=6


def _point(x, w, h, margin=8):
    if (not isinstance(x,(list,tuple)) or len(x)!=2 or
        any(isinstance(z,bool) or not isinstance(z,(int,float)) or not math.isfinite(z)
            for z in x)):
        raise ValueError("invalid_pixel_point")
    a,b=map(float,x)
    if a<margin or b<margin or a>=w-margin or b>=h-margin:
        raise ValueError("seed_outside_safe_image")
    return [a,b]


def _size(a):
    if (not isinstance(a,dict) or isinstance(a.get("width"),bool)
        or isinstance(a.get("height"),bool) or not isinstance(a.get("width"),int)
        or not isinstance(a.get("height"),int)
        or a["width"]<120 or a["height"]<80 or a["width"]>4096
        or a["height"]>2160):
        raise ValueError("invalid_frame_dimensions")
    return a["width"],a["height"]


def validate_seeds(annotations, *, sha256, actual_size):
    """Annotated seed record must match video bytes, day, venue, race and 6 IDs.

    The unverified annotations may *start* tracking. They cannot independently
    certify correct racer identities, world calibration or forecast readiness.
    """
    if not isinstance(annotations,dict) or annotations.get("schema")!=SEED_SCHEMA:
        raise ValueError("seed_annotation_schema_missing")
    if annotations.get("venue_code")!=SOURCE_VENUE_CODE:
        raise ValueError("seed_wrong_venue")
    if (not isinstance(annotations.get("event_date"),str)
        or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",annotations["event_date"])):
        raise ValueError("seed_invalid_event_date")
    try:
        datetime.strptime(annotations["event_date"],"%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("seed_invalid_event_date") from exc
    race=annotations.get("race")
    if isinstance(race,bool) or not isinstance(race,int) or not 1<=race<=12:
        raise ValueError("seed_invalid_race")
    if not isinstance(sha256,str) or not re.fullmatch(r"[a-f0-9]{64}",sha256):
        raise ValueError("invalid_source_video_sha")
    if annotations.get("source_sha256")!=sha256:
        raise ValueError("seed_video_sha_mismatch")
    width,height=_size(annotations.get("frame_size"))
    if (width,height)!=tuple(actual_size):
        raise ValueError("seed_frame_size_mismatch")
    interval=annotations.get("sample_interval_s")
    if (isinstance(interval,bool) or not isinstance(interval,(float,int))
        or not math.isfinite(interval) or not .1<=interval<=3.0):
        raise ValueError("seed_sample_interval_invalid")
    offset=annotations.get("clip_start_seconds",0)
    if (isinstance(offset,bool) or not isinstance(offset,(int,float)) or
        not math.isfinite(offset) or not 0<=offset<=300):
        raise ValueError("seed_clip_start_invalid")
    if annotations.get("reference_frame_index")!=0:
        raise ValueError("seed_reference_not_first_frame")
    boats=annotations.get("boats")
    if not isinstance(boats,list) or len(boats)!=6:
        raise ValueError("six_boat_seeds_required")
    coords={};raw=[]
    for item in boats:
        if not isinstance(item,dict):
            raise ValueError("invalid_boat_seed")
        lane=item.get("lane")
        if isinstance(lane,bool) or not isinstance(lane,int) or lane not in range(1,7) or lane in coords:
            raise ValueError("duplicate_or_invalid_lane")
        p=_point(item.get("center_px"),width,height)
        coords[lane]=p
        raw.append(p)
    if set(coords)!=set(range(1,7)):
        raise ValueError("missing_boat_seed")
    if min(math.dist(p,q) for i,p in enumerate(raw) for q in raw[i+1:])<10:
        raise ValueError("boat_seeds_overlap")
    anchors=annotations.get("static_landmarks")
    if not isinstance(anchors,list) or not MIN_LANDMARKS<=len(anchors)<=20:
        raise ValueError("not_enough_static_landmarks")
    px=[];ids=set()
    for a in anchors:
        if not isinstance(a,dict):
            raise ValueError("invalid_static_landmark")
        label=a.get("id")
        if not isinstance(label,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}",label) or label in ids:
            raise ValueError("duplicate_static_landmark_id")
        ids.add(label)
        px.append(_point(a.get("center_px"),width,height))
    if min(math.dist(p,q) for i,p in enumerate(px) for q in px[i+1:])<6:
        raise ValueError("static_landmarks_overlap")
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("opencv_required_for_six_boat_tracking") from exc
    spread=cv2.contourArea(cv2.convexHull(np.asarray(px,dtype=np.float32)))
    if spread<width*height*.02:
        raise ValueError("static_landmarks_collinear_or_localized")
    # World coords are intentionally NOT accepted as proof of camera calibration.
    # Only pixel stabilization is produced; metre distances remain unknown.
    return {
        "venue_code":SOURCE_VENUE_CODE,"race":race,"event_date":annotations["event_date"],
        "source_sha256":sha256,"width":width,"height":height,
        "interval_s":float(interval),
        "clip_start_seconds":float(offset),
        "boats":[coords[i] for i in range(1,7)],
        "landmarks":px,
    }


def _lk(prev_gray,gray,points):
    """Forward-backward check rejects swaps, jumps and unreliable matches."""
    import cv2
    import numpy as np
    if not len(points):
        return [],[]
    source=np.asarray(points,dtype=np.float32).reshape(-1,1,2)
    cfg={"winSize":(31,31),"maxLevel":3,
         "criteria":(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,30,.01)}
    nxt,forward,_=cv2.calcOpticalFlowPyrLK(prev_gray,gray,source,None,**cfg)
    if nxt is None:
        return [None]*len(points),[None]*len(points)
    back,backward,_=cv2.calcOpticalFlowPyrLK(gray,prev_gray,nxt,None,**cfg)
    if back is None:
        return [None]*len(points),[None]*len(points)
    candidates=[];errors=[]
    for k in range(len(points)):
        if not forward[k,0] or not backward[k,0]:
            candidates.append(None);errors.append(None);continue
        xy=nxt[k,0]
        residual=float(np.linalg.norm(back[k,0]-source[k,0]))
        step=float(np.linalg.norm(xy-source[k,0]))
        if not np.all(np.isfinite(xy)) or residual>MAX_LK_BACKTRACK_PX or step>MAX_LK_STEP_PX:
            candidates.append(None);errors.append(None);continue
        candidates.append([float(xy[0]),float(xy[1])])
        errors.append(round(residual,3))
    return candidates,errors


def _image(jpeg):
    import cv2
    import numpy as np
    if not isinstance(jpeg,bytes) or not jpeg:
        raise ValueError("missing_decoded_frame")
    image=cv2.imdecode(np.frombuffer(jpeg,dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("unreadable_decoded_frame")
    return image


def track_seeded_frames(jpeg_frames,annotations,source_sha256, *, times=None):
    """Track six *user-labelled* initial points with camera motion compensation.

    Returns numerical candidates only. This function intentionally does not
    produce 'boatlabs.verified_six_boat_tracks.v1' or independent identity proof.
    """
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("opencv_required_for_six_boat_tracking") from exc
    if not isinstance(jpeg_frames,(list,tuple)) or not 2<=len(jpeg_frames)<=FRAME_LIMIT:
        raise ValueError("insufficient_or_excessive_video_frames")
    first=_image(jpeg_frames[0]);h,w=first.shape[:2]
    seeds=validate_seeds(annotations,sha256=source_sha256,actual_size=(w,h))
    if times is None:
        times=[round(i*seeds["interval_s"],4) for i in range(len(jpeg_frames))]
    if (not isinstance(times,list) or len(times)!=len(jpeg_frames)
        or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x)
               for x in times) or
        any(times[i+1]<=times[i] for i in range(len(times)-1))):
        raise ValueError("invalid_frame_time_axis")
    if abs(times[0])>1e-6:
        raise ValueError("first_frame_timestamp_not_zero")
    bpts=list(seeds["boats"]);lpts=list(seeds["landmarks"])
    origin=np.asarray(lpts,dtype=np.float32)
    reports={k:[] for k in range(1,7)}
    alive={k:True for k in range(1,7)}
    camera_checks=[]
    last_frame=first
    lost_anchors=set()
    for frame_index,encoded in enumerate(jpeg_frames):
        gray=first if frame_index==0 else _image(encoded)
        if gray.shape!=first.shape:
            raise ValueError("video_camera_resolution_changed")
        if frame_index>0:
            active_labels=[k for k in range(1,7) if alive[k]]
            candidates,errors=_lk(last_frame,gray,[bpts[k-1] for k in active_labels])
            for k,p,err in zip(active_labels,candidates,errors):
                if p is None or not 8<=p[0]<w-8 or not 8<=p[1]<h-8:
                    alive[k]=False
                else:
                    bpts[k-1]=p
            active_anchors=[i for i in range(len(lpts)) if i not in lost_anchors]
            moved,errs=_lk(last_frame,gray,[lpts[i] for i in active_anchors])
            for k,p,err in zip(active_anchors,moved,errs):
                if p is None or not 8<=p[0]<w-8 or not 8<=p[1]<h-8:
                    lost_anchors.add(k)
                else:
                    lpts[k]=p
            last_frame=gray
        matched=[i for i in range(len(lpts)) if i not in lost_anchors]
        if len(matched)<4:
            camera_checks.append({"frame":frame_index,"valid":False,
                                  "anchor_count":len(matched),"reason":"not_enough_static_anchor_tracks"})
            continue
        current=np.asarray([lpts[i] for i in matched],dtype=np.float32)
        initial=origin[matched]
        homography,mask=cv2.findHomography(current,initial,cv2.RANSAC,3.5)
        if homography is None or not np.all(np.isfinite(homography)):
            camera_checks.append({"frame":frame_index,"valid":False,
                                  "anchor_count":len(matched),"reason":"camera_registration_failed"})
            continue
        inliers=int(mask.sum()) if mask is not None else len(matched)
        transformed=cv2.perspectiveTransform(current.reshape(-1,1,2),homography).reshape(-1,2)
        residuals=np.linalg.norm(transformed-initial,axis=1)
        med=float(np.median(residuals))
        good=inliers>=4 and med<=MAX_CAMERA_REPROJECTION_PX
        camera_checks.append({"frame":frame_index,"valid":good,
                              "anchor_count":len(matched),"ransac_inliers":inliers,
                              "median_anchor_error_px":round(med,3)})
        if not good:continue
        pairs=[]
        for lane in range(1,7):
            if not alive[lane]:continue
            pos=np.asarray(bpts[lane-1],dtype=np.float32).reshape(1,1,2)
            adjusted=cv2.perspectiveTransform(pos,homography)[0,0]
            if not np.all(np.isfinite(adjusted)):continue
            if not 0<=adjusted[0]<w or not 0<=adjusted[1]<h:continue
            pairs.append((lane,bpts[lane-1],adjusted))
        # Ambiguous overlaps can indicate track swapping, so reject these
        # frames entirely, rather than assigning identities by color/position.
        if len(pairs)>1 and min(math.dist(p[1],q[1]) for i,p in enumerate(pairs)
                                for q in pairs[i+1:])<7:
            camera_checks[-1]["valid"]=False
            camera_checks[-1]["reason"]="boat_track_overlap_ambiguous"
            continue
        for lane,unadjusted,adjusted in pairs:
            reports[lane].append({
                "frame":frame_index,"t_seconds":round(float(times[frame_index]),4),
                "raw_center_px":[round(float(x),2) for x in unadjusted],
                "camera_stabilized_center_px":[round(float(x),2) for x in adjusted],
                "identity_verified":False,
            })
    total=len(jpeg_frames)
    summary=[]
    for lane in range(1,7):
        track=reports[lane];steps=[]
        for a,b in zip(track,track[1:]):
            if b["frame"]!=a["frame"]+1:continue
            dt=b["t_seconds"]-a["t_seconds"]
            if dt<=0:continue
            p,q=a["camera_stabilized_center_px"],b["camera_stabilized_center_px"]
            steps.append(math.dist(p,q)/dt)
        summary.append({
            "lane_seed_label":lane,
            "tracked_frames":len(track),
            "coverage_ratio":round(len(track)/total,3),
            "median_stabilized_apparent_motion_px_per_s":round(float(np.median(steps)),3)
               if steps else None,
            "samples":track,
            "id_independently_verified":False,
        })
    full=sum(len(x["samples"])==total for x in summary)
    stabilized=sum(bool(x["valid"]) for x in camera_checks)
    return {
        "schema":SCHEMA,
        "status":"UNVERIFIED_CAMERA_STABILIZED_SIX_SEED_CANDIDATES",
        "source_sha256":source_sha256,
        "event_date":seeds["event_date"],"venue_code":"10","race":seeds["race"],
        "frames_seen":total,"camera_stabilized_frames":stabilized,
        "clip_start_seconds":seeds["clip_start_seconds"],
        "seed_annotated_boats":6,
        "candidate_fully_tracked_boats":full,
        "unverified_tracks":summary,
        "camera_registration":camera_checks,
        "confirmed_boat_tracks":0,"turn_metrics_measured":0,
        "post_start_stretch_measured":0,
        "water_plane_metre_calibration_confirmed":False,
        "approved_verified_track_ledger_created":False,
        "eligible_for_formal_or_shadow_forecast":False,
        "note":"Boats are user-seeded pixel labels only. Camera stabilization does not calibrate metres or independently verify lane identity. Do not use as motion forecasts.",
    }
