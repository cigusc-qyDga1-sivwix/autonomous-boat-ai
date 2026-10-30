"""Temporary rendered frames -> unverified numeric motion research only.

Operates only after the *official* JLC replay page has been independently
matched by date, venue and race, and the HTML5 video clock advanced.
Keeps Playwright screenshots and JPEGs in RAM. Nothing visual is written to
disk or logs; this does NOT independently validate six boat identities.
"""
from __future__ import annotations
import math

MIN_FRAMES=6
MAX_FRAMES=10
MAX_EDGE_PX=1920
MIN_CLOCK_DELTA_S=0.15


def analyze_png_samples(png_samples, timestamps):
    """Fail closed if pictures do not move; output only bounded numeric data."""
    import cv2
    import numpy as np
    from scripts.mikuni_auto_vision import analyze_automatic_frames
    if (not isinstance(png_samples, (list,tuple)) or
            not MIN_FRAMES<=len(png_samples)<=MAX_FRAMES or
            len(timestamps)!=len(png_samples)):
        raise ValueError("insufficient_rendered_frames")
    if (any(not isinstance(t,(float,int)) or isinstance(t,bool) or
            not math.isfinite(t) for t in timestamps) or
            any(b-a<MIN_CLOCK_DELTA_S for a,b in zip(timestamps,timestamps[1:]))):
        raise ValueError("video_clock_not_strictly_advancing")
    imgs=[]
    jpegs=[]
    for data in png_samples:
        if not isinstance(data, bytes) or not 100<=len(data)<=3_000_000:
            raise ValueError("invalid_in_memory_player_screenshot")
        im=cv2.imdecode(np.frombuffer(data,dtype=np.uint8),cv2.IMREAD_COLOR)
        if im is None or im.ndim!=3:
            raise ValueError("video_player_pixels_unreadable")
        h,w=im.shape[:2]
        if not 120<=w<=MAX_EDGE_PX or not 80<=h<=MAX_EDGE_PX:
            raise ValueError("video_player_frame_bounds_invalid")
        if imgs and imgs[0].shape!=im.shape:
            raise ValueError("video_player_frame_size_changed")
        imgs.append(im)
        ok,encoded=cv2.imencode(".jpg",im,[cv2.IMWRITE_JPEG_QUALITY,88])
        if not ok:
            raise ValueError("in_memory_jpeg_encode_failed")
        jpegs.append(encoded.tobytes())
    moving=sum(float(np.mean(cv2.absdiff(a,b)))>=1.0
               for a,b in zip(imgs,imgs[1:]))
    result={
        "schema":"boatlabs.mikuni_cloud_rendered_visual_candidates.v1",
        "player_screenshot_samples":len(imgs),
        "visually_changing_frame_pairs":moving,
        "real_video_identity_verified":False,
        "confirmed_boat_tracks":0,
        "eligible_for_formal_forecast":False,
        "raw_frames_persisted":0,
        "pixel_to_metre_calibrated":False,
        "automatic_candidate_tracks":0,
        "six_colour_candidates_supported":False,
    }
    if moving<4:
        result["status"]="RENDERED_VIDEO_STATIC_OR_BLACK_NO_CANDIDATES"
        return result
    intervals=[b-a for a,b in zip(timestamps,timestamps[1:])]
    dt=float(np.median(intervals))
    detected=analyze_automatic_frames(jpegs,sample_interval_s=dt)
    result["status"]="RENDERED_VIDEO_UNVERIFIED_CANDIDATES"
    result["automatic_candidate_tracks"]=int(detected["candidate_boat_tracks"])
    result["six_colour_candidates_supported"]=bool(detected["all_six_candidates_supported"])
    result["camera_stabilized_frames"]=int(detected["camera_stabilized_frames"])
    return result


async def collect_rendered_player(frame, *, sample_count=8, interval_ms=700):
    """Playwright DOM screenshot of a *visible* video element, no raw stream."""
    if not MIN_FRAMES<=sample_count<=MAX_FRAMES:
        raise ValueError("invalid_frame_count")
    locator=frame.locator("video")
    if await locator.count()!=1:
        raise ValueError("expected_one_visible_video_element")
    v=locator.first
    if not await v.is_visible():
        raise ValueError("video_element_not_visible")
    png=[]
    stamps=[]
    for _ in range(sample_count):
        sample=await frame.evaluate("""()=>{
          const v=document.querySelector('video');
          if(!v)return null;
          return {time:v.currentTime,paused:v.paused,ended:v.ended,ready:v.readyState};
        }""")
        if not sample or sample["paused"] or sample["ended"] or sample["ready"]<2:
            raise ValueError("player_not_actively_playing")
        picture=await v.screenshot(type="png",timeout=4500,animations="disabled")
        png.append(picture)
        stamps.append(float(sample["time"]))
        await frame.wait_for_timeout(interval_ms)
    try:
        return analyze_png_samples(png,stamps)
    finally:
        png.clear()
