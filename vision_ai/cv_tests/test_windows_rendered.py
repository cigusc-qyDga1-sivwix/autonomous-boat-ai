"""Generated pixels only: these tests cannot prove real-video accuracy."""
import unittest
import cv2
import numpy as np
from test_tracking import scene
from vision_ai.windows_runner import analyze_rendered_samples, SUCCESS

class RenderedTests(unittest.TestCase):
    def test_generated_moving_scene_remains_unverified(self):
        report=analyze_rendered_samples(scene(),[.7*i for i in range(8)])
        self.assertEqual(report['status'],SUCCESS)
        self.assertEqual(report['candidate_boat_tracks'],6)
        self.assertEqual(report['tracking']['confirmed_boat_tracks'],0)
        self.assertNotIn('source_media_sha256',report)
        self.assertEqual(len(report['rendered_frame_sequence_sha256']),64)

    def test_normal_hd_frames_are_consistently_resized(self):
        frames=[]
        for encoded in scene():
            original=cv2.imdecode(np.frombuffer(encoded,np.uint8),cv2.IMREAD_COLOR)
            ok,png=cv2.imencode('.png',cv2.resize(original,(1280,854)))
            self.assertTrue(ok)
            frames.append(png.tobytes())
        report=analyze_rendered_samples(frames,[.7*i for i in range(8)])
        self.assertEqual(report['rendered_frame_size'],{'width':1280,'height':854})
        self.assertEqual(report['analysis_frame_size']['width'],640)

    def test_black_and_static_never_become_candidates(self):
        for value in (0,75):
            ok,png=cv2.imencode('.png',np.full((320,480,3),value,np.uint8))
            self.assertTrue(ok)
            report=analyze_rendered_samples([png.tobytes()]*8,[.7*i for i in range(8)])
            self.assertEqual(report['status'],'RENDERED_FRAMES_STATIC_OR_BLACK')
            self.assertNotIn('tracking',report)

    def test_stalled_irregular_clock_corrupt_and_resized_input_rejected(self):
        frames=scene()
        for stamps in ([0]*8,[0,.7,1.4,2.1,2.8,3.5,4.2,6.0],[float('nan')]*8):
            with self.assertRaises(ValueError):
                analyze_rendered_samples(frames,stamps)
        with self.assertRaises(ValueError):
            analyze_rendered_samples([b'x'*100]*8,[.7*i for i in range(8)])
        im=cv2.imdecode(np.frombuffer(frames[-1],np.uint8),cv2.IMREAD_COLOR)
        _,png=cv2.imencode('.png',im[:200])
        with self.assertRaisesRegex(ValueError,'dimensions_changed'):
            analyze_rendered_samples(frames[:-1]+[png.tobytes()],[.7*i for i in range(8)])
