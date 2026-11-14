import unittest
from vision_ai.source_job import collect

ENV = {'MIKUNI_VIDEO_SOURCE_TEMPLATE': 'https://approved.example/{yyyymmdd}/{race2}.mp4',
       'MIKUNI_VIDEO_ALLOWED_HOSTS': 'approved.example'}


def observation(status, code=None):
    return {'status': status, 'http_status': code, 'stages': {'media_received': False,
            'frames_decoded': False, 'automatic_tracking_computed': False}}


class SourceJobTests(unittest.TestCase):
    def test_missing_source_does_not_call_network(self):
        r = collect('2026-11-03', [1], environment={}, processor=lambda *a, **k: self.fail('network'))
        self.assertEqual(r['races'][0]['status'], 'SOURCE_CONFIGURATION_MISSING')
        self.assertEqual(r['summary']['media_received'], 0)

    def test_existing_settings_work_without_numerical_exhibition_rows(self):
        calls = []
        def process(manifest, **kwargs):
            calls.append((manifest['race'], kwargs['video_url']))
            return observation('SOURCE_HTTP_ERROR', 403)
        r = collect('2026-11-03', [1, 12], environment=ENV, processor=process)
        self.assertEqual(calls, [(1, 'https://approved.example/20261103/01.mp4'),
                                 (12, 'https://approved.example/20261103/12.mp4')])
        self.assertNotIn('approved.example', str(r))
        self.assertFalse(r['eligible_for_formal_forecast'])

    def test_404_retry_is_bounded_403_is_not_retried(self):
        for code, count in ((404, 3), (403, 1)):
            r = collect('2026-11-03', [1], environment=ENV, attempts=3, pause=lambda _: None,
                        processor=lambda *a, **k: observation('SOURCE_HTTP_ERROR', code))
            self.assertEqual(len(r['races'][0]['attempts']), count)

    def test_invalid_templates_do_not_reach_provider(self):
        for template in ('https://approved.example/fixed.mp4',
                         'https://approved.example/{date}/{race.__class__}.mp4',
                         'https://other.example/{date}/{race}.mp4'):
            env = {**ENV, 'MIKUNI_VIDEO_SOURCE_TEMPLATE': template}
            r = collect('2026-11-03', [1], environment=env, processor=lambda *a, **k: self.fail('network'))
            self.assertEqual(r['races'][0]['status'], 'SOURCE_CONFIGURATION_INVALID')

    def test_provider_configuration_is_not_mixed(self):
        env = {**ENV, 'VISION_VIDEO_SOURCE_TEMPLATE': 'https://new.example/{date}/{race}.mp4'}
        r = collect('2026-11-03', [1], environment=env)
        self.assertEqual(r['source_configuration'], 'MISSING')

    def test_invalid_scope_is_rejected(self):
        for races in ([True], [1, 1], [0], []):
            with self.assertRaises(ValueError):
                collect('2026-11-03', races, environment={})
