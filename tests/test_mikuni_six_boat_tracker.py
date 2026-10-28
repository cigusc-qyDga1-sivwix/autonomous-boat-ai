"""Six-boat optical-flow and camera stabilization: synthetic scenes only.

No actual race footage or authoritative racer IDs have been tested.
"""
import copy
import hashlib
import io
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from scripts.mikuni_six_boat_tracker import (
    SCHEMA, SEED_SCHEMA, track_seeded_frames, validate_seeds,
)
from scripts.mikuni_video_shadow import build as build_shadow
from scripts.mikuni_video_ephemeral import collect, select_seed_record


SHA="c"*64
DAY="2026-10-28"
WIDTH,HEIGHT=480,320
ANCHOR_POS=[[36,40],[215,32],[445,44],[40,275],[230,289],[442,270]]
BOAT_POS=[[82+57*i,118+14*(i%2)] for i in range(6)]


def seeds():
    return {
        "schema":SEED_SCHEMA,"event_date":DAY,"venue_code":"10","race":7,
        "source_sha256":SHA,
        "reference_frame_index":0,
        "sample_interval_s":.4,
        "frame_size":{"width":WIDTH,"height":HEIGHT},
        "boats":[{"lane":i+1,"center_px":p} for i,p in enumerate(BOAT_POS)],
        "static_landmarks":[{"id":"shore_"+str(i),"center_px":p}
                            for i,p in enumerate(ANCHOR_POS)],
        "annotations_provenance":"manual_label_only_no_independent_video_check",
    }


def synthetic_scene(frame_count=8, camera_dx=1,boat_dx=2):
    import cv2
    import numpy as np
    rng=np.random.default_rng(20261028)
    stamps=[rng.integers(30,220,(19,19),dtype=np.uint8) for _ in range(12)]
    images=[]
    for step in range(frame_count):
        canvas=np.full((HEIGHT,WIDTH),100,dtype=np.uint8)
        for k,center in enumerate(ANCHOR_POS+BOAT_POS):
            offset_x=step*camera_dx+(0 if k<6 else step*boat_dx)
            offset_y=step # all anchor/boat coords shift with camera pan
            x=int(center[0]+offset_x);y=int(center[1]+offset_y)
            canvas[y-9:y+10,x-9:x+10]=stamps[k]
        ok,jpg=cv2.imencode(".jpg",canvas,[cv2.IMWRITE_JPEG_QUALITY,98])
        if not ok:raise RuntimeError("jpeg_synthetic_scene_encode")
        images.append(jpg.tobytes())
    return images


class SixBoatTrackerTests(unittest.TestCase):
    def setUp(self):
        try:
            import numpy
            import cv2
        except ImportError:
            self.skipTest("OpenCV optional; no real six-boat claim")

    def test_all_six_seeded_candidates_stabilize_camera_pan(self):
        output=track_seeded_frames(synthetic_scene(),seeds(),SHA)
        self.assertEqual(output["schema"],SCHEMA)
        self.assertEqual(output["frames_seen"],8)
        self.assertEqual(output["candidate_fully_tracked_boats"],6)
        self.assertEqual(output["camera_stabilized_frames"],8)
        self.assertEqual(output["confirmed_boat_tracks"],0)
        self.assertFalse(output["water_plane_metre_calibration_confirmed"])
        self.assertFalse(output["eligible_for_formal_or_shadow_forecast"])
        for record in output["unverified_tracks"]:
            self.assertEqual(record["tracked_frames"],8)
            start=record["samples"][0]["camera_stabilized_center_px"]
            end=record["samples"][-1]["camera_stabilized_center_px"]
            # Motion of boat excluding x-only camera pan (~2 px/frame)
            self.assertAlmostEqual(end[0]-start[0],7*2,delta=3)
            self.assertAlmostEqual(end[1]-start[1],0,delta=2.5)
            self.assertFalse(record["id_independently_verified"])

    def test_bad_provenance_does_not_create_candidate_metrics(self):
        sample=seeds()
        cases=[]
        wrong=copy.deepcopy(sample);wrong["source_sha256"]="f"*64;cases.append(wrong)
        wrong=copy.deepcopy(sample);wrong["boats"].pop();cases.append(wrong)
        wrong=copy.deepcopy(sample);wrong["boats"][5]["lane"]=1;cases.append(wrong)
        wrong=copy.deepcopy(sample);wrong["boats"][4]["center_px"]=wrong["boats"][3]["center_px"];cases.append(wrong)
        wrong=copy.deepcopy(sample);wrong["static_landmarks"]=wrong["static_landmarks"][:4];cases.append(wrong)
        wrong=copy.deepcopy(sample);wrong["frame_size"]["width"]=550;cases.append(wrong)
        wrong=copy.deepcopy(sample);wrong["event_date"]="2026-02-30";cases.append(wrong)
        wrong=copy.deepcopy(sample);wrong["sample_interval_s"]=0;cases.append(wrong)
        wrong=copy.deepcopy(sample);wrong["static_landmarks"]=[
            {"id":"shore_"+str(i),"center_px":[35+40*i,40]} for i in range(6)]
        cases.append(wrong)
        for item in cases:
            with self.assertRaises(ValueError, msg=str(item)[:100]):
                validate_seeds(item,sha256=SHA,actual_size=(WIDTH,HEIGHT))

    def test_incorrect_timestamps_are_rejected(self):
        jpgs=synthetic_scene(4)
        for times in ([0,.4,.4,1.2],[-1,0,.4,.8],[0,.4]):
            with self.assertRaises(ValueError):
                track_seeded_frames(jpgs,seeds(),SHA,times=list(times))

    def test_camera_reference_visibility_required_for_metric_claims(self):
        img=synthetic_scene(6)
        # A hard scene cut loses all anchors, so new-frame measurements must fail closed.
        import cv2
        import numpy as np
        blank=np.full((HEIGHT,WIDTH),70,dtype=np.uint8)
        ok,jpg=cv2.imencode(".jpg",blank)
        self.assertTrue(ok)
        output=track_seeded_frames(img[:3]+[jpg.tobytes()]*3,seeds(),SHA)
        self.assertLess(output["candidate_fully_tracked_boats"],6)
        self.assertEqual(output["confirmed_boat_tracks"],0)

    def test_seed_library_is_strictly_keyed_by_sha_date_venue_race(self):
        pack={"schema":"boatlabs.mikuni_seed_library.v0.1","event_date":DAY,
              "venue_code":"10","records":[seeds()]}
        self.assertEqual(select_seed_record(pack,DAY,7,SHA),seeds())
        self.assertIsNone(select_seed_record(pack,DAY,6,SHA))
        self.assertIsNone(select_seed_record(pack,DAY,7,"a"*64))
        self.assertIsNone(select_seed_record(pack,"2026-10-29",7,SHA))
        pack["records"].append(seeds())
        self.assertIsNone(select_seed_record(pack,DAY,7,SHA))

    def test_real_collector_wires_seeded_six_track_candidate_without_promoting(self):
        jpgs=synthetic_scene()
        tagged=seeds()
        tagged["sample_interval_s"]=.5
        library={"schema":"boatlabs.mikuni_seed_library.v0.1","event_date":DAY,
                 "venue_code":"10","records":[tagged]}
        archive={"event_date":DAY,"records":[{
            "race_code":"202610281007","venue_code":"10","race":7,
            "boats":[{"lane":i} for i in range(1,7)]}]}
        payload=b"RIFF"+b"\0"*4+b"AVI "+b"test"
        called=[]
        def receive(url,hosts):
            called.append(url)
            return payload,{"sha256":SHA,"file_size":len(payload),
                            "content_type":"video/x-msvideo"}
        args=(DAY,archive,None,
              "https://approved.provider.example/video/{yyyymmdd}/{race2}.avi",
              ["approved.provider.example"])
        with patch("scripts.mikuni_video_ephemeral.decode_in_memory",return_value=jpgs) as decoder:
            output=collect(*args,receiver=receive,seed_library=library,
                           now=datetime(2026,10,28,0,30,tzinfo=timezone.utc))
        self.assertEqual(len(called),1)
        self.assertEqual(output["summary"]["video_races_observed"],1)
        audit=output["races"]["7"]["video_observation"]
        self.assertEqual(audit["seeded_tracking_status"],"UNVERIFIED_CANDIDATE_COMPUTED")
        report=audit["six_boat_seeded_tracking_candidate"]
        self.assertEqual(report["candidate_fully_tracked_boats"],6)
        self.assertEqual(report["confirmed_boat_tracks"],0)
        self.assertFalse(report["eligible_for_formal_or_shadow_forecast"])
        self.assertNotIn("test",str(output))
        self.assertNotIn("approved.provider.example",str(output))
        self.assertEqual(output["summary"]["confirmed_boat_tracks"],0)

    def test_seed_can_reprocess_same_sha_after_first_unseeded_observation(self):
        jpgs=synthetic_scene()
        tagged=seeds()
        tagged["sample_interval_s"]=.5
        library={"schema":"boatlabs.mikuni_seed_library.v0.1",
                 "event_date":DAY,"venue_code":"10","records":[tagged]}
        archive={"event_date":DAY,"records":[{
            "race_code":"202610281007","venue_code":"10","race":7,
            "boats":[{"lane":i} for i in range(1,7)]}]}
        payload=b"RIFF"+b"\0"*4+b"AVI "+b"content"
        calls=[]
        def receive(url,hosts):
            calls.append(1)
            return payload,{"sha256":SHA,"file_size":len(payload),
                            "content_type":"video/x-msvideo"}
        args=(DAY,archive,None,
              "https://approved.provider.example/video/{yyyymmdd}/{race2}.avi",
              ["approved.provider.example"])
        with patch("scripts.mikuni_video_ephemeral.decode_in_memory",return_value=jpgs):
            original=collect(*args,receiver=receive,now=datetime(2026,10,28,0,30,tzinfo=timezone.utc))
            self.assertEqual(original["races"]["7"]["video_observation"]["seeded_tracking_status"],
                             "NO_SIX_BOAT_SEEDS")
            updated=collect(DAY,archive,original,args[3],args[4],receiver=receive,
                            seed_library=library,now=datetime(2026,10,28,0,31,tzinfo=timezone.utc))
            self.assertEqual(updated["races"]["7"]["video_observation"]["seeded_tracking_status"],
                             "UNVERIFIED_CANDIDATE_COMPUTED")
            again=collect(DAY,archive,updated,args[3],args[4],receiver=receive,
                          seed_library=library,now=datetime(2026,10,28,0,32,tzinfo=timezone.utc))
        self.assertEqual(len(calls),2)
        self.assertEqual(again["races"]["7"],updated["races"]["7"])

    def test_annotation_sample_interval_mismatch_cannot_publish_pixel_tracks(self):
        jpgs=synthetic_scene()
        tagged=seeds()
        # Human labels must match decoder's fixed interval (0.5 s).
        library={"schema":"boatlabs.mikuni_seed_library.v0.1",
                 "event_date":DAY,"venue_code":"10","records":[tagged]}
        archive={"event_date":DAY,"records":[{
            "race_code":"202610281007","venue_code":"10","race":7,
            "boats":[{"lane":i} for i in range(1,7)]}]}
        payload=b"RIFF"+b"\0"*4+b"AVI "+b"content"
        with patch("scripts.mikuni_video_ephemeral.decode_in_memory",return_value=jpgs):
            out=collect(DAY,archive,None,
                        "https://approved.provider.example/video/{yyyymmdd}/{race2}.avi",
                        ["approved.provider.example"],seed_library=library,
                        receiver=lambda *_:(payload,{"sha256":SHA,"file_size":len(payload),"content_type":"video/x-msvideo"}))
        self.assertEqual(out["summary"]["video_races_observed"],0)
        self.assertEqual(out["races"]["7"]["status"],"SOURCE_OR_ANALYSIS_NOT_READY")

    def test_unverified_candidates_cannot_be_promoted_to_shadow_by_schema(self):
        candidate=track_seeded_frames(synthetic_scene(),seeds(),SHA)
        faux_doc={"event_date":DAY,"schema":candidate["schema"],"venue_code":"10",
                  "records":[candidate]}
        snap={"event_date":DAY,"forecast_races":[{
            "venue":"三国","race":7,"cutoff_jst":"14:00","phase":"exhibition",
            "model_version":"four-factor-v1.5-point-free-untrained",
            "ticket_status":"formal","entry_exhibition_gate":{"final_eligible":True},
            "sha256":"a"*64,"formal_snapshot_sha256":"a"*64,
            "bets":[{"combination":"1-2-3","virtual_yen":50000}]}]}
        source={"schema":"boatlabs.mikuni_authorized_video_ingestion.v1",
                "event_date":DAY,"races":{"7":{
                    "status":"MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY","source_sha256":SHA,
                    "captured_at_utc":"2026-10-28T02:00:00+00:00"}}}
        result=build_shadow(DAY,snap,source,faux_doc,
                            now=datetime(2026,10,28,2,20,tzinfo=timezone.utc))
        self.assertEqual(result["summary"]["video_shadow_frozen_races"],0)
        self.assertEqual(result["rejected"][0]["reason"],"verified_six_boat_tracks_missing")


if __name__=="__main__":
    unittest.main()
