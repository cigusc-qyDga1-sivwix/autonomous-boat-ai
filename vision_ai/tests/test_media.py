"""Direct-source eligibility and memory-only HTTP response checks."""
import hashlib
import io
import unittest
from unittest.mock import patch

from vision_ai.media import MAX_VIDEO_BYTES, StrictRedirect, receive_approved_video

URL = "https://authorized.example/exhibition.avi"
HOSTS = {"authorized.example"}
PAYLOAD = b"RIFF" + b"\0" * 4 + b"AVI " + b"synthetic-test-data" * 3


class Response(io.BytesIO):
    def __init__(self, payload, content_type="video/x-msvideo", length=None):
        super().__init__(payload)
        self.headers = {"Content-Type": content_type, "Content-Length": str(length or len(payload))}

    def geturl(self):
        return URL


class MediaTests(unittest.TestCase):
    def test_approved_response_is_received_in_ram_and_hashed(self):
        with patch("vision_ai.media.build_opener") as opener:
            opener.return_value.open.return_value = Response(PAYLOAD)
            data, info = receive_approved_video(URL, HOSTS)
        self.assertEqual(data, PAYLOAD)
        self.assertEqual(info["sha256"], hashlib.sha256(PAYLOAD).hexdigest())
        self.assertEqual(info["file_size"], len(PAYLOAD))
        self.assertNotIn("https:", str(info))

    def test_html_hls_and_excessive_content_are_not_direct_video(self):
        for response in (Response(b"<html>player</html>", "text/html"),
                         Response(b"#EXTM3U", "application/vnd.apple.mpegurl"),
                         Response(PAYLOAD, length=MAX_VIDEO_BYTES + 1),
                         Response(b"invalid-video", "video/mp4")):
            with patch("vision_ai.media.build_opener") as opener:
                opener.return_value.open.return_value = response
                with self.assertRaises(ValueError):
                    receive_approved_video(URL, HOSTS)

    def test_unapproved_transport_host_and_credentials_never_send_request(self):
        for url in ("http://authorized.example/video", "https://127.0.0.1/video",
                    "https://authorized.example.evil/video", "https://user:password@authorized.example/video",
                    "https://authorized.example/video#fragment"):
            with patch("vision_ai.media.build_opener") as opener:
                with self.assertRaises(ValueError):
                    receive_approved_video(url, HOSTS)
                opener.assert_not_called()

    def test_redirect_cannot_leave_approved_source(self):
        with self.assertRaisesRegex(ValueError, "unapproved"):
            StrictRedirect(HOSTS).redirect_request(None, None, 302, "", {}, "https://other.example/video")


if __name__ == "__main__":
    unittest.main()
