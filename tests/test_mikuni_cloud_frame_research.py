"""No user PC or copyrighted video required; synthetic pixel tests only."""
import unittest
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = np = None
from scripts.mikuni_cloud_frame_research import analyze_png_samples


def frame(shift=0):
    im=np.full((240,360,3),75,dtype=np.uint8)
    cv2.rectangle(im,(60+shift,100),(76+shift,118),(240,240,240),-1)
    ok,data=cv2.imencode(".png",im)
    assert ok
    return data.tobytes()


@unittest.skipIf(cv2 is None, 'optional video dependencies absent in general unit-test CI')
class CloudFrameTests(unittest.TestCase):
    def test_static_video_pixels_are_not_accepted_as_boats(self):
        image=frame(0)
        report=analyze_png_samples([image]*8,[i*.7 for i in range(8)])
        self.assertEqual(report["status"],"RENDERED_VIDEO_STATIC_OR_BLACK_NO_CANDIDATES")
        self.assertEqual(report["automatic_candidate_tracks"],0)
        self.assertEqual(report["confirmed_boat_tracks"],0)
        self.assertFalse(report["eligible_for_formal_forecast"])
        self.assertEqual(report["raw_frames_persisted"],0)

    def test_non_advancing_video_clock_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"video_clock"):
            analyze_png_samples([frame()]*8,[0.0]*8)

    def test_bad_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            analyze_png_samples([b"notpng"]*8,[i*.7 for i in range(8)])

    def test_not_enough_frames_rejected(self):
        with self.assertRaises(ValueError):
            analyze_png_samples([frame()]*3,[0,.7,1.4])

    def test_full_hd_browser_capture_reaches_bounded_tracking(self):
        # Real browser video elements are wider than the tracker's 640px cap.
        base = np.random.default_rng(71).integers(40, 100, (180, 320, 3), dtype=np.uint8)
        images = []
        for i in range(8):
            image = cv2.resize(np.roll(base, i * 3, axis=1), (1920, 1080))
            ok, encoded = cv2.imencode('.png', image)
            self.assertTrue(ok)
            images.append(encoded.tobytes())
        report = analyze_png_samples(images, [i * .7 for i in range(8)])
        self.assertEqual(report['status'], 'RENDERED_VIDEO_UNVERIFIED_CANDIDATES')
        self.assertEqual(report['player_screenshot_samples'], 8)
        self.assertEqual(report['confirmed_boat_tracks'], 0)
        self.assertFalse(report['eligible_for_formal_forecast'])

    def test_source_size_changes_are_rejected_before_resizing(self):
        normal = frame()
        image = cv2.imdecode(np.frombuffer(normal, np.uint8), cv2.IMREAD_COLOR)
        ok, encoded = cv2.imencode('.png', cv2.resize(image, (720, 480)))
        self.assertTrue(ok)
        with self.assertRaisesRegex(ValueError, 'frame_size_changed'):
            analyze_png_samples([normal] * 7 + [encoded.tobytes()], [i * .7 for i in range(8)])


if __name__=="__main__":
    unittest.main()
