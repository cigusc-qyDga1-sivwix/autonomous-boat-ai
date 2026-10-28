"""Offline tests for Mikuni official YouTube RSS discovery (no video downloads)."""
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from xml.sax.saxutils import escape
import unittest

from scripts.mikuni_official_video_catalog import (
    CHANNEL_ID, CHANNEL_URL, FEED_URL, SCHEMA, build, parse_feed,
    RestrictedFeedRedirect, GoogleAPIHostRedirect, parse_official_api, _failure_reason
)

DAY="2026-10-28"
NOW=datetime(2026,10,28,0,40,tzinfo=timezone.utc)

def fake_feed(title="ボートレース三国 2026年10月28日 1R〜12R レースライブ",
              channel=CHANNEL_ID, published="2026-10-28T00:31:00+00:00",
              video_id="abc123DEF45"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015">
  <yt:channelId>{channel}</yt:channelId>
  <entry>
    <id>yt:video:{video_id}</id>
    <yt:videoId>{video_id}</yt:videoId>
    <yt:channelId>{channel}</yt:channelId>
    <title>{escape(title)}</title>
    <author><name>ボートレース三国</name></author>
    <published>{published}</published>
  </entry>
</feed>""".encode("utf-8")


class OfficialChannelCatalogTests(unittest.TestCase):
    def test_official_source_is_not_a_video_file(self):
        self.assertIn("youtube.com/channel/",CHANNEL_URL)
        self.assertIn("youtube.com/feeds/videos.xml",FEED_URL)
        self.assertEqual(len(CHANNEL_ID),24)

    def test_parse_valid_official_stream_metadata(self):
        entry=parse_feed(fake_feed(),DAY)
        self.assertEqual(entry["entries_in_feed"],1)
        self.assertEqual(len(entry["candidates"]),1)
        v=entry["candidates"][0]
        self.assertEqual(v["official_watch_url"],"https://www.youtube.com/watch?v=abc123DEF45")
        self.assertEqual(v["video_frames_analyzed"],0)
        self.assertIsNone(v["race_number"])
        self.assertEqual(v["classification"],"CANDIDATE_ONLY_NOT_VERIFIED_RACE_OR_PLAYABLE_VIDEO")

    def test_no_other_channels_or_fake_ids(self):
        with self.assertRaisesRegex(ValueError,"wrong_official_channel"):
            parse_feed(fake_feed(channel="UC1234567890123456789012"),DAY)
        result=parse_feed(fake_feed(video_id="https://not-a-video.example"),DAY)
        self.assertEqual(result["candidates"],[])

    def test_realistic_cup_final_stream_title_is_not_dropped(self):
        title="スポーツクラブ新田塚アーク杯　最終日　８：００～"
        result=parse_feed(fake_feed(title=title,published="2026-10-28T00:15:00Z"),DAY)
        self.assertEqual(len(result["candidates"]),1)

    def test_require_titled_racing_or_exact_date(self):
        out=parse_feed(fake_feed(title="別の日のレース 2026/10/10",published="2026-10-10T01:00:00Z"),DAY)
        self.assertFalse(out["candidates"])
        out=parse_feed(fake_feed(title="10/28 レース展示"),DAY)
        self.assertEqual(len(out["candidates"]),1)
        out=parse_feed(fake_feed(title="日常の楽しいお知らせ",published="2026-10-28T00:31:00Z"),DAY)
        self.assertEqual(len(out["candidates"]),0)

    def test_fail_closed_on_entities_and_non_feed(self):
        for feed in (b"<!DOCTYPE foo><feed/>",b"<html>not atom</html>",
                     b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"/>'):
            with self.assertRaises(ValueError):
                parse_feed(feed,DAY)
        with self.assertRaises(ValueError):
            parse_feed(b" "*(1024*1024+1),DAY)

    def test_never_claim_stream_downloads_and_retain_prior_metadata(self):
        first=build(DAY,feed_fetcher=fake_feed,now=NOW)
        self.assertEqual(first["schema"],SCHEMA)
        self.assertEqual(first["source_status"],"OFFICIAL_CHANNEL_RSS_METADATA_READ")
        self.assertEqual(first["candidate_count"],1)
        self.assertEqual(first["video_bytes_downloaded"],0)
        self.assertEqual(first["video_frames_analyzed"],0)
        self.assertEqual(first["six_boats_identified"],0)
        self.assertEqual(first["may_download_youtube_content"],False)
        gone=build(DAY,first,feed_fetcher=lambda:(_ for _ in ()).throw(URLError("unavailable")),now=NOW)
        self.assertEqual(gone["candidate_count"],1)
        self.assertEqual(gone["source_status"],"RSS_UNAVAILABLE_OR_UNVERIFIED")
        self.assertEqual(gone["failure_reason"],"YOUTUBE_RSS_NETWORK_UNAVAILABLE")
        wrong_day=build("2026-10-29",first,feed_fetcher=lambda:fake_feed(title="10/27 video",published="2026-10-27T02:00:00Z"),now=NOW)
        self.assertEqual(wrong_day["candidate_count"],0)

    def test_https_redirect_gate(self):
        guard=RestrictedFeedRedirect()
        req=type("Req",(),{"full_url":FEED_URL})()
        with self.assertRaises(ValueError):
            guard.redirect_request(req,None,302,"Moved",{},"http://youtube.com/path")
        with self.assertRaises(ValueError):
            guard.redirect_request(req,None,302,"Moved",{},"https://evil.example.org/a")

    def test_official_api_metadata_fallback_recovers_from_rss_404(self):
        api={
            "items":[{
                "snippet":{
                    "resourceId":{"kind":"youtube#video","videoId":"bQpDFGkH123"},
                    "videoOwnerChannelId":CHANNEL_ID,
                    "title":"スポーツクラブ新田塚アーク杯　最終日　８：００～",
                    "publishedAt":"2026-10-28T00:02:00Z"
                },
                "contentDetails":{"videoPublishedAt":"2026-10-27T22:40:00Z"}
            }]
        }
        def fail_feed():
            raise HTTPError(FEED_URL,404,"not found",None,None)
        result=build(DAY,feed_fetcher=fail_feed,now=NOW,
                     api_key="test-fake-key-not-real",
                     api_fetcher=lambda key:api)
        self.assertEqual(result["source_status"],"OFFICIAL_YOUTUBE_DATA_API_METADATA_READ")
        self.assertEqual(result["source_kind"],"OFFICIAL_YOUTUBE_DATA_API_METADATA_ONLY")
        self.assertEqual(result["failure_reason"],"YOUTUBE_RSS_HTTP_404")
        self.assertEqual(result["candidate_count"],1)
        self.assertEqual(result["candidates"][0]["video_id"],"bQpDFGkH123")
        self.assertEqual(result["candidates"][0]["video_frames_analyzed"],0)
        self.assertEqual(result["video_bytes_downloaded"],0)
        self.assertFalse(result["may_download_youtube_content"])
        self.assertNotIn("test-fake-key-not-real",str(result))

    def test_api_rejects_another_channel_and_fake_winning_motion(self):
        candidates=parse_official_api({"items":[
           {"snippet":{"resourceId":{"videoId":"abc123DEF45"},
                       "videoOwnerChannelId":"UCwrongchannel12345678900",
                       "title":"三国レース","publishedAt":"2026-10-28T00:31:00Z"}},
           {"snippet":{"resourceId":{"videoId":"abc123DEF46"},
                       "videoOwnerChannelId":CHANNEL_ID,
                       "title":"三国レース 10/28","publishedAt":"2026-10-28T00:31:00Z"}},
        ]},DAY)
        self.assertEqual(len(candidates["candidates"]),1)
        self.assertEqual(candidates["candidates"][0]["video_id"],"abc123DEF46")
        self.assertIsNone(candidates["candidates"][0]["race_number"])
        self.assertEqual(candidates["candidates"][0]["video_frames_analyzed"],0)

    def test_api_failure_does_not_expose_key_in_audit(self):
        def fail_feed():raise HTTPError(FEED_URL,404,"not found",None,None)
        def fail_api(_):raise URLError("https://www.googleapis.com/secret-key-not-for-logging")
        result=build(DAY,feed_fetcher=fail_feed,now=NOW,api_key="secret-key-not-for-logging",api_fetcher=fail_api)
        self.assertEqual(result["source_status"],"RSS_AND_API_UNAVAILABLE")
        self.assertEqual(result["candidate_count"],0)
        self.assertTrue(result["api_fallback_attempted"])
        self.assertNotIn("secret-key-not-for-logging",str(result))

    def test_api_https_redirect_checks(self):
        guard=GoogleAPIHostRedirect()
        req=type("Req",(),{"full_url":"https://www.googleapis.com/youtube/v3/channels"})()
        with self.assertRaises(ValueError):
            guard.redirect_request(req,None,302,"redirect",{},"https://evil.example/steal")
        with self.assertRaises(ValueError):
            guard.redirect_request(req,None,302,"redirect",{},"http://www.googleapis.com/youtube/v3/")

    def test_feed_unavailable_without_network_never_becomes_video_success(self):
        def denied():
            raise HTTPError(FEED_URL,403,"Forbidden",None,None)
        status=build(DAY,feed_fetcher=denied,now=NOW)
        self.assertEqual(status["failure_reason"],"YOUTUBE_RSS_HTTP_403")
        self.assertEqual(status["candidate_count"],0)
        self.assertEqual(status["video_frames_analyzed"],0)


if __name__=="__main__":
    unittest.main()
