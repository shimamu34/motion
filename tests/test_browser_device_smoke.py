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
            "speed", "flip", "model", "infer", "copy", "reset", "report",
            "poseOverlay", "poseState", "follow", "syncFrame", "timeline", "timelineTime"
        }.issubset(self.parsed.ids))

    def test_original_application_unchanged_and_dependencies_match(self):
        original = re.findall(r'<script src="([^"]+)"', self.app)
        self.assertEqual(self.parsed.scripts, original)
        self.assertEqual(len(self.parsed.scripts), 2)

    def test_movenet_thunder_matches_original(self):
        for token in ("poseDetection.SupportedModels.MoveNet",
                      "poseDetection.movenet.modelType.SINGLEPOSE_THUNDER",
                      "detector.estimatePoses(manual ? video : snapshotCanvas)"):
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

    def test_pose_overlay_renders_on_video_with_confidence_and_bones(self):
        self.assertIn('<canvas id="poseOverlay"', self.page)
        self.assertIn('function drawPoseOverlay(poses, sourceWidth', self.page)
        self.assertIn('ctx.lineTo(', self.page)
        self.assertIn('ctx.stroke()', self.page)
        self.assertIn('ctx.arc(', self.page)
        self.assertIn('const minConfidence = 0.2', self.page)
        self.assertIn('video.clientWidth, height = video.clientHeight', self.page)
        self.assertIn('Math.min(width / sourceWidth, height / sourceHeight)', self.page)

    def test_reset_reason_and_paused_resize_redraw_are_explicit(self):
        for token in ('pose_visualization_last_result',
                      'pose_visualization_reset_reason',
                      'pose_visualization_points',
                      'pose_visualization_segments',
                      'lastManualPose',
                      'lastManualGeneration === currentGeneration',
                      'markVisualizationReset("RESIZE")',
                      'markVisualizationReset("SEEK")',
                      'markVisualizationReset("PAUSE")'):
            self.assertIn(token, self.page)

    def test_tracking_pause_refreshes_stopped_frame_without_parallel_inference(self):
        for token in ('function requestPausedRefresh()', 'pauseRefreshPending',
                      'video.addEventListener("pause"', 'void inferPose(true, true)',
                      'trackingSession !== trackingAtStart',
                      'suppressNextPauseRefresh'):
            self.assertIn(token, self.page)

    def test_visualization_does_not_claim_success_without_a_person(self):
        self.assertIn('pose_visualization: "NOT_TESTED"', self.page)
        self.assertIn('record("pose_visualization", "NO_POSE")', self.page)
        self.assertIn('segments > 0 ? "PASS" : "NO_VISIBLE_SKELETON"', self.page)
        self.assertIn('poses.length > 0 ? "PosesFound" : "NoPosesInFrame"', self.page)

    def test_flip_keeps_video_and_overlay_aligned(self):
        self.assertIn('video.style.transform = transform;', self.page)
        self.assertIn('overlay.style.transform = transform;', self.page)
        self.assertIn('syncFrame.style.transform = transform;', self.page)
        self.assertIn('pointer-events:none', self.page)

    def test_pose_overlay_tracks_frames_and_clears_on_navigation(self):
        for token in ('video.addEventListener("play"', 'video.addEventListener("seeked"',
                      'video.addEventListener("emptied"', 'clearOverlay()'):
            self.assertIn(token, self.page)
        self.assertIn('record("pose_visualization", "STALE_FRAME")', self.page)
        self.assertIn('generation !== currentGeneration || (!manual && !following)', self.page)

    def test_sensitive_movenet_diagnostic_is_separate_from_production(self):
        self.assertIn('minPoseScore = 0.10', self.page)
        self.assertIn('minPoseScore }', self.page)
        self.assertIn('pose_min_pose_score: 0.10', self.page)
        self.assertIn('既定値0.25', self.page)
        self.assertIn('誤検出も増えます', self.page)

    def test_continuous_pose_has_single_throttled_raf_loop(self):
        for token in ('function scheduleFollow()', 'requestAnimationFrame(async () => {',
                      'followMinIntervalMs = 50', 'if (inferenceBusy || !detector || !playable()) return;',
                      'await inferPose(false)', 'function stopFollowing()', 'cancelAnimationFrame(',
                      'pose_follow_updates', 'pose_follow_poses_found',
                      'captureVideoSnapshot()', 'showSynchronizedFrame()',
                      'pose_follow_last_inference_ms', 'pose_follow_video_lag_ms'):
            self.assertIn(token, self.page)

    def test_pose_and_rendered_frame_share_the_same_snapshot(self):
        self.assertIn('snapshotContext.drawImage(video, 0, 0, width, height)', self.page)
        self.assertIn('detector.estimatePoses(manual ? video : snapshotCanvas)', self.page)
        self.assertIn('drawPoseOverlay(poses, snapshotCanvas.width, snapshotCanvas.height)', self.page)
        self.assertIn('syncFrame.hidden = false;', self.page)
        self.assertIn('video.paused || video.seeking || lag > 1.5', self.page)
        self.assertIn('pose_follow_stale_drops', self.page)

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
