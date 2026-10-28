"""Mikuni ephemeral video and conditional shadow invariants; no external HTTP."""
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from types import SimpleNamespace
import unittest

from scripts.mikuni_video_ephemeral import (
    _split_jpegs, decode_in_memory, collect, FRAME_LIMIT,
    numerical_motion_candidates,
)
from scripts.mikuni_video_shadow import (
    SCHEMA, TRACK_SCHEMA, MODEL, build, valid_bets, redistribute_shadow, validate_six_tracks,
)

DAY="2026-10-28"
NOW=datetime(2026,10,28,0,20,tzinfo=timezone.utc)
DIGEST="a"*64
JST=timezone(timedelta(hours=9))


def archive():
    return {"event_date":DAY,"records":[{
        "race_code":"202610281006","venue_code":"10","race":6,
        "boats":[{"lane":i} for i in range(1,7)],
    }]}


def observations(lane):
    k=.1*lane
    return [
        {"segment":"start_early","t_seconds":0,"xy_m":[0,0]},
        {"segment":"start_early","t_seconds":1,"xy_m":[6+k,0]},
        {"segment":"start_late","t_seconds":2,"xy_m":[14,0]},
        {"segment":"start_late","t_seconds":3,"xy_m":[22+k,0]},
        {"segment":"turn_entry","t_seconds":4,"xy_m":[30,0]},
        {"segment":"turn_entry","t_seconds":5,"xy_m":[35+k,0]},
        {"segment":"turn_exit","t_seconds":6,"xy_m":[40,0]},
        {"segment":"turn_exit","t_seconds":7,"xy_m":[47+k,0]},
    ]


def verified_tracks():
    return {"schema":TRACK_SCHEMA,"event_date":DAY,"venue_code":"10","records":[{
        "race":6,"source_sha256":DIGEST,
        "verification_kind":"independent_camera_calibrated_six_boat_tracks",
        "camera_motion_compensated":True,"camera_calibration_confirmed":True,
        "captured_at_utc":"2026-10-28T00:03:00+00:00",
        "verified_at_utc":"2026-10-28T00:06:00+00:00",
        "boats":[{"lane":i,"identity_confidence":.97,"observations":observations(i)}
                 for i in range(1,7)],
    }]}


def observed_video():
    return {"schema":"boatlabs.mikuni_authorized_video_ingestion.v1",
            "event_date":DAY,
            "races":{"6":{"status":"MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY",
                          "source_sha256":DIGEST,
                          "captured_at_utc":"2026-10-28T00:04:00+00:00",
                          "video_observation":{"status":"UNVERIFIED_PIXEL_MOTION_ONLY",
                                               "confirmed_boat_tracks":0}}},
            "summary":{"video_races_observed":1}}


def live():
    return {"event_date":DAY,"forecast_races":[{
        "venue":"三国","race":6,"cutoff_jst":"10:30",
        "phase":"exhibition","model_version":"four-factor-v1.5-point-free-untrained",
        "ticket_status":"formal",
        "entry_exhibition_gate":{"final_eligible":True},
        "sha256":"f"*64,"formal_snapshot_sha256":"f"*64,
        "bets":[{"combination":"1-2-3","virtual_yen":30000},
                {"combination":"2-1-3","virtual_yen":20000}]
    }]}


class EphemeralFramePipelineTests(unittest.TestCase):
    def test_jpeg_frames_split_without_disk(self):
        media=b"header"+b"\xff\xd8frame-one\xff\xd9"+b"middle"+b"\xff\xd8frame-two\xff\xd9"
        self.assertEqual(_split_jpegs(media),[b"\xff\xd8frame-one\xff\xd9",b"\xff\xd8frame-two\xff\xd9"])
        with self.assertRaises(ValueError):
            _split_jpegs(b"not a jpeg")

    def test_decode_stdin_only_bounded_output(self):
        calls=[]
        def ffmpeg(args,**kwargs):
            calls.append((args,kwargs))
            return SimpleNamespace(returncode=0,stdout=b"\xff\xd8sample\xff\xd9",stderr=b"")
        image=decode_in_memory(b"\0\0\0\x18ftypisom\0\0\0\0",runner=ffmpeg)
        self.assertEqual(len(image),1)
        cmd,kw=calls[0]
        self.assertEqual(cmd[0],"ffmpeg")
        self.assertIn("pipe:0",cmd)
        self.assertIn("pipe:1",cmd)
        self.assertEqual(kw["timeout"],35)
        self.assertEqual(kw["input"][4:8],b"ftyp")
        self.assertFalse(any(x.endswith(".mp4") for x in cmd))

    def test_mp4_seekable_ram_fd_fallback_does_not_create_disk_video(self):
        import os
        if not hasattr(os,"memfd_create"):
            self.skipTest("Linux anonymous RAM fd unavailable")
        calls=[]
        def ffmpeg(args,**kwargs):
            calls.append((args,kwargs))
            if len(calls)==1:
                return SimpleNamespace(returncode=1,stdout=b"",stderr=b"requires seek")
            # Verify the byte source is an anonymous RAM fd, not a disk file.
            self.assertTrue(any("/proc/self/fd/" in arg for arg in args))
            fd=kwargs["pass_fds"][0]
            self.assertEqual(os.read(fd,4),b"\0\0\0\x18")
            return SimpleNamespace(returncode=0,stdout=b"\xff\xd8ok\xff\xd9",stderr=b"")
        source=b"\0\0\0\x18ftypisom\0\0\0\0"
        frames=decode_in_memory(source,runner=ffmpeg)
        self.assertEqual(len(frames),1)
        self.assertEqual(len(calls),2)
        self.assertNotIn("input",calls[1][1])

    def test_real_ffmpeg_decodes_small_synthetic_avi_in_memory(self):
        import shutil
        import subprocess
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg unavailable")
        result=subprocess.run([
            "ffmpeg","-hide_banner","-loglevel","error",
            "-f","lavfi","-i","testsrc=size=160x90:rate=5",
            "-frames:v","20","-c:v","mjpeg","-f","avi","pipe:1",
        ],capture_output=True,timeout=12,check=False)
        if result.returncode!=0:
            self.skipTest("test MJPEG encoding unavailable")
        self.assertEqual(result.stdout[:4],b"RIFF")
        images=decode_in_memory(result.stdout)
        self.assertGreaterEqual(len(images),2)
        self.assertLessEqual(len(images),FRAME_LIMIT)
        try:
            import cv2
        except ImportError:
            return
        metrics=numerical_motion_candidates(images)
        self.assertGreater(metrics["sampled_frames"],0)
        self.assertEqual(metrics["confirmed_boat_tracks"],0)
        self.assertFalse(metrics["calibrated_water_plane"])

    def test_no_source_means_no_download_or_faked_six_boats(self):
        result=collect(DAY,archive(),None,None,[],now=NOW)
        self.assertEqual(result["summary"]["video_races_observed"],0)
        self.assertEqual(result["summary"]["confirmed_boat_tracks"],0)
        self.assertEqual(result["races"]["6"]["status"],"AUTHORIZED_SOURCE_CONFIGURATION_MISSING")
        self.assertEqual(result["storage"],"MEMORY_ONLY_INPUT_NO_VIDEO_FRAMES_PERSISTED")
        self.assertEqual(result["races"]["1"]["status"],"AWAITING_EXHIBITION_NUMERIC_RESEARCH_ROW")

    def test_authorized_fake_source_parses_bytes_but_not_racers(self):
        called=[]
        def recv(url,hosts):
            called.append(url)
            payload=b"\0\0\0\x18ftypisom\0\0\0\0"
            return payload,{"sha256":hashlib.sha256(payload).hexdigest(),
                            "file_size":len(payload),"content_type":"video/mp4"}
        def analyze(payload):
            self.assertEqual(payload[4:8],b"ftyp")
            return {"status":"UNVERIFIED_PIXEL_MOTION_ONLY",
                    "confirmed_boat_tracks":0,
                    "candidate_colors":{"red_candidate":{"pixel_center":[24,33]}}}
        result=collect(DAY,archive(),None,
            "https://approved.provider.example/video/{yyyymmdd}/{race2}.mp4",
            ["approved.provider.example"],receiver=recv,analyzer=analyze,now=NOW)
        self.assertEqual(len(called),1)
        self.assertEqual(result["summary"]["video_races_observed"],1)
        self.assertEqual(result["races"]["6"]["status"],"MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY")
        self.assertNotIn("approved.provider.example",json.dumps(result))
        self.assertNotIn("ftypisom",json.dumps(result))
        self.assertEqual(result["summary"]["measured_turns"],0)
        replay=collect(DAY,archive(),result,
            "https://approved.provider.example/video/{yyyymmdd}/{race2}.mp4",
            ["approved.provider.example"],receiver=lambda *_:self.fail("re-downloaded"),now=NOW)
        self.assertEqual(replay["races"]["6"],result["races"]["6"])

    def test_colour_image_is_unverified_even_if_bright_and_visible(self):
        try:
            import numpy as np
            import cv2
        except ImportError:
            self.skipTest("opencv optional")
        frame=np.full((100,160,3),(90,90,90),dtype=np.uint8)
        cv2.circle(frame,(65,65),8,(0,0,250),-1)
        ok,encoded=cv2.imencode(".jpg",frame)
        self.assertTrue(ok)
        report=numerical_motion_candidates([encoded.tobytes()])
        self.assertEqual(report["status"],"UNVERIFIED_PIXEL_MOTION_ONLY")
        self.assertEqual(report["confirmed_boat_tracks"],0)
        self.assertEqual(report["turn_metrics_measured"],0)
        self.assertIsNone(report["candidate_colors"]["red_candidate"]["confirmed_boat_id"])


class VerifiedMotionShadowTests(unittest.TestCase):
    def test_missing_tracks_cannot_generate_predicted_bets(self):
        source=live()
        copy_source=copy.deepcopy(source)
        out=build(DAY,source,observed_video(),None,now=NOW)
        self.assertEqual(out["summary"]["video_shadow_frozen_races"],0)
        self.assertEqual(out["rejected"][0]["reason"],"verified_six_boat_tracks_missing")
        self.assertEqual(source,copy_source)

    def test_valid_verified_six_boat_tracks_produce_independent_shadow(self):
        source=live()
        before=copy.deepcopy(source)
        doc=build(DAY,source,observed_video(),verified_tracks(),now=NOW)
        self.assertEqual(doc["schema"],SCHEMA)
        self.assertEqual(len(doc["records"]),1)
        row=doc["records"][0]
        self.assertEqual(row["model"],MODEL)
        self.assertEqual(row["source_video_sha256"],DIGEST)
        self.assertEqual(row["baseline_sha256"],"f"*64)
        self.assertTrue(row["verified_before_cutoff"])
        self.assertFalse(row["result_data_used"])
        self.assertTrue(row["formal_buy_and_settlement_unchanged"])
        self.assertTrue(valid_bets(row["shadow_bets"]))
        self.assertNotEqual(row["shadow_bets"],row["source_bets"])
        self.assertEqual(source,before)
        repeated=build(DAY,source,observed_video(),verified_tracks(),doc,now=NOW+timedelta(seconds=1))
        self.assertEqual(repeated["records"],doc["records"])
        self.assertEqual(row["record_sha256"],repeated["records"][0]["record_sha256"])

    def test_no_post_cutoff_shadow_or_hindsight(self):
        out=build(DAY,live(),observed_video(),verified_tracks(),
                  now=datetime(2026,10,28,1,29,tzinfo=timezone.utc))
        self.assertEqual(out["summary"]["video_shadow_frozen_races"],0)
        self.assertEqual(out["rejected"][0]["reason"],"too_late_to_freeze_video_shadow")

    def test_unverified_identity_camera_or_sha_rejected(self):
        for mutation in ("identity","sha","camera","time"):
            tracks=verified_tracks()
            r=tracks["records"][0]
            if mutation=="identity":r["boats"][0]["identity_confidence"]=.71
            if mutation=="sha":r["source_sha256"]="b"*64
            if mutation=="camera":r["camera_calibration_confirmed"]=False
            if mutation=="time":r["verified_at_utc"]="2026-10-28T02:00:00+00:00"
            result=build(DAY,live(),observed_video(),tracks,now=NOW)
            self.assertEqual(result["summary"]["video_shadow_frozen_races"],0,mutation)

    def test_unverified_pixel_regions_cannot_masquerade_as_tracks(self):
        data=verified_tracks()
        data["records"][0]["verification_kind"]="color_blobs_guessed_as_boats"
        out=build(DAY,live(),observed_video(),data,now=NOW)
        self.assertEqual(out["summary"]["video_shadow_frozen_races"],0)
        self.assertEqual(out["rejected"][0]["reason"],"unverified_boat_identity")

    def test_baseline_and_stake_guards(self):
        source=live()
        source["forecast_races"][0]["ticket_status"]="provisional"
        self.assertEqual(build(DAY,source,observed_video(),verified_tracks(),now=NOW)["records"],[])
        source=live()
        source["forecast_races"][0]["model_version"]="four-factor-v1.4-venue-aware-23-untrained"
        self.assertEqual(build(DAY,source,observed_video(),verified_tracks(),now=NOW)["records"],[])
        with self.assertRaises(ValueError):
            redistribute_shadow([{"combination":"1-2-3","virtual_yen":1000}],{i:0 for i in range(1,7)})


if __name__=="__main__":
    unittest.main()
