"""Offline contract checks for a local-only browser/Chromebook smoke test.

These tests do NOT prove a real browser, camera or pose model works.
"""
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "tests" / "browser-device-smoke.html"
APP = ROOT / "index.html"


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.scripts = []
        self.forms = []
        self.video_tags = []
        self.external = []
    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if "id" in props:
            self.ids.add(props["id"])
        if tag == "script" and props.get("src"):
            self.scripts.append(props["src"])
        if tag == "form":
            self.forms.append(props)
        if tag == "video":
            self.video_tags.append(props)
        if tag in ("img", "iframe", "link") and props.get("src"):
            self.external.append(props["src"])


class DeviceSmokeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = PAGE.read_text(encoding="utf-8")
        cls.app = APP.read_text(encoding="utf-8")
        cls.parsed = PageParser()
        cls.parsed.feed(cls.page)

    def test_required_interactive_controls(self):
        self.assertTrue({
            "videoFile", "video", "play", "seek", "frame",
            "speed", "flip", "model", "infer", "copy", "reset", "report"
        }.issubset(self.parsed.ids))

    def test_original_application_unchanged_and_dependencies_match(self):
        original = re.findall(r'<script src="([^"]+)"', self.app)
        self.assertEqual(self.parsed.scripts, original)
        self.assertEqual(len(self.parsed.scripts), 2)

    def test_movenet_thunder_matches_original(self):
        for token in ("poseDetection.SupportedModels.MoveNet",
                      "poseDetection.movenet.modelType.SINGLEPOSE_THUNDER",
                      "detector.estimatePoses(video)"):
            self.assertIn(token, self.page)
        self.assertIn("poseDetection.movenet.modelType.SINGLEPOSE_THUNDER", self.app)

    def test_no_upload_or_network_reporting_code(self):
        for forbidden in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket(",
                          "RTCPeerConnection", "FormData(", "getUserMedia(",
                          "file.name", "file.lastModified", "file.arrayBuffer("):
            self.assertNotIn(forbidden, self.page)
        self.assertEqual(self.parsed.forms, [])
        self.assertEqual(self.parsed.external, [])

    def test_object_url_lifecycle(self):
        self.assertIn("URL.createObjectURL(file)", self.page)
        self.assertIn("URL.revokeObjectURL(objectUrl)", self.page)
        self.assertIn('window.addEventListener("pagehide"', self.page)

    def test_manual_accessibility_and_video(self):
        self.assertEqual(len(self.parsed.video_tags), 1)
        self.assertIn("playsinline", self.parsed.video_tags[0])
        self.assertIn("controls", self.parsed.video_tags[0])
        self.assertIn('role="status"', self.page)
        self.assertIn('aria-live="polite"', self.page)

    def test_seeking_and_frame_safe_fallbacks(self):
        for token in ('video.addEventListener("seeked"', "SeekTimeout",
                      "video.duration / 2", "before + 1 / 30", "video.pause()"):
            self.assertIn(token, self.page)

    def test_no_implied_real_world_success(self):
        self.assertIn("NOT_TESTED", self.page)
        self.assertIn("本番アプリ", self.page)
        self.assertIn("姿勢モデル", self.page)
        self.assertIn("アップロードしません", self.page)

    def test_diagnostics_exclude_user_identifiers_and_media(self):
        self.assertIn('JSON.stringify(outcome, null, 2)', self.page)
        self.assertNotIn("navigator.userAgent", self.page)
        self.assertNotIn("localStorage", self.page)
        self.assertNotIn("indexedDB", self.page)


if __name__ == "__main__":
    unittest.main()
