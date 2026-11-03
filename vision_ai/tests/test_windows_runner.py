"""Configuration, race identity and fail-closed queue tests; no network."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from vision_ai import windows_runner as w

CONFIG = {'schema':'boatlabs.vision_ai.windows_runner_config.v1','venue_code':'10',
          'event_date':'2026-10-28','races':[1], 'permission_reference':'test-only'}
PLAYER = 'https://front.player.boatrace-cdn.jp/player/vod?service=jyobb&stadium=10mikuni&raceType=exhibition&raceDate=20261028&raceNumber=1'
WRAPPER = 'https://livebb.jlc.ne.jp/bb_top/new_bb/streamer/streamer.php?md=T&jo=10&ymd=2026-10-28&race=1'

class WindowsRunnerTests(unittest.TestCase):
    def test_config_limits_and_jst_today(self):
        now = datetime(2026,10,28,16,tzinfo=timezone.utc)
        self.assertEqual(w.validate_config({**CONFIG,'event_date':'today'},now=now)['event_date'],'2026-10-29')
        for patch in ({'venue_code':'02'}, {'races':[True]}, {'races':[1,1]}, {'sample_count':100},
                      {'clip_starts_seconds':[-1]}, {'media_url':'https://example.com'}, {'permission_reference':''},
                      {'event_date':'2026-10-30'}, {'max_attempts':6}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                w.validate_config({**CONFIG,**patch},now=now)

    def test_exact_race_date_venue_type_and_host_required(self):
        self.assertTrue(w.matches_player(PLAYER,'2026-10-28',1))
        self.assertTrue(w.matches_wrapper(WRAPPER,'2026-10-28',1))
        bad = [PLAYER.replace('raceNumber=1','raceNumber=11'), PLAYER+'&raceNumber=1',
               PLAYER.replace('10mikuni','02toda'),PLAYER.replace('exhibition','race'),
               PLAYER.replace('20261028','20261027'),PLAYER.replace('https:','http:'),
               PLAYER.replace('boatrace-cdn.jp','boatrace-cdn.jp.evil.invalid'),
               PLAYER.replace('/player/vod','/player/live')]
        for url in bad:
            self.assertFalse(w.matches_player(url,'2026-10-28',1),url)
        self.assertFalse(w.matches_wrapper(WRAPPER.replace('md=T','md=R'),'2026-10-28',1))

    def test_official_handler_is_parsed_not_executed(self):
        handler = "ymd='2026-10-28';race=1;md='T';createpageset();"
        self.assertEqual(w.parse_official_link(handler),('2026-10-28',1))
        for bad in (handler+'alert(1)',handler.replace('md=\'T\'','md=\'R\''),handler.replace('race=1','race=13'),None):
            self.assertIsNone(w.parse_official_link(bad))

    def test_player_requires_matching_parent_and_no_ambiguity(self):
        wrapper=Mock(url=WRAPPER)
        player=Mock(url=PLAYER,parent_frame=wrapper)
        page=Mock(frames=[wrapper,player])
        self.assertIs(w.pick_player(page,'2026-10-28',1),player)
        page.frames.append(Mock(url=PLAYER))
        with self.assertRaisesRegex(w.CaptureError,'PLAYER_AMBIGUOUS'):
            w.pick_player(page,'2026-10-28',1)
        page.frames=[wrapper,Mock(url=PLAYER,parent_frame=Mock(url=WRAPPER))]
        with self.assertRaisesRegex(w.CaptureError,'PLAYER_IDENTITY_MISMATCH'):
            w.pick_player(page,'2026-10-28',1)

    def test_viewing_denial_stops_without_capture(self):
        frame=Mock()
        frame.locator.return_value.inner_text.return_value='この映像の視聴は許可されていません。'
        with self.assertRaisesRegex(w.CaptureError,'VIEWING_DENIED'):
            w.check_denied(frame)
        frame.screenshot.assert_not_called()

    def test_failure_queue_persists_numeric_report_and_never_retries_denial(self):
        def denied(config,race):
            report=w.base_report(config,race)
            report['status']='VIEWING_DENIED'
            return w.finish(report)
        processor=Mock(side_effect=denied)
        sleeper=Mock()
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(w.run_queue(CONFIG,folder,watch=True,processor=processor,sleep=sleeper),2)
            reports=list(Path(folder).glob('*.json'))
            self.assertEqual(len(reports),1)
            report=json.loads(reports[0].read_text())
            self.assertEqual(report['confirmed_boat_tracks'],0)
            self.assertFalse(report['eligible_for_formal_forecast'])
            self.assertFalse(report['eligible_for_shadow_forecast'])
            self.assertEqual(report['raw_frames_persisted'],0)
            self.assertEqual(report['source_media_sha256'],None)
        processor.assert_called_once()
        sleeper.assert_not_called()

    def test_unavailable_retry_is_bounded_and_success_is_not_repeated(self):
        seen={1:0,2:0}
        def process(config,race):
            seen[race]+=1
            report=w.base_report(config,race)
            report['status']=w.SUCCESS if race==1 else 'RACE_NOT_AVAILABLE'
            return w.finish(report)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(w.run_queue({**CONFIG,'races':[1,2]},folder,watch=True,processor=process,sleep=lambda _:None),2)
        self.assertEqual(seen,{1:1,2:3})

    def test_production_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'production_output_path_forbidden'):
                w.save_attempt(w.finish(w.base_report(CONFIG,1)),Path(folder)/'formal')

if __name__=='__main__':
    unittest.main()
