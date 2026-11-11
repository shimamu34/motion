#!/usr/bin/env python3
"""Offline tests. Never contact GitHub, Manus, Claude or Cue APIs."""
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).resolve().parents[1] / ".github/scripts/ai_handoff_packet.py"
spec = importlib.util.spec_from_file_location("packet_module", SOURCE)
packet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packet)

HEAD = "a" * 40
OTHER = "b" * 40
ENV = {"GITHUB_EVENT_NAME": "pull_request_target", "GITHUB_REPOSITORY": "shimamu34/motion",
       "GITHUB_REF": "refs/heads/main", "GH_TOKEN": "FAKE_TOKEN"}


def event(owner="shimamu34", action="opened", sha=HEAD):
    return {"action": action, "repository": {"full_name": "shimamu34/motion"},
            "pull_request": {"number": 8, "user": {"login": owner}, "head": {"sha": sha}}}


def pr(sha=HEAD):
    return {"number": 8, "state": "open", "merged": False, "title": "Fix video",
            "head": {"sha": sha, "ref": "feature/video"}, "base": {"ref": "main"}}


def files():
    return [{"filename": "index.html", "changes": 3, "status": "modified",
             "patch": "@@ -10 +10 @@\n+safe code change\n"}]


class PacketTests(unittest.TestCase):
    def test_owner_only(self):
        self.assertTrue(packet.allowed(event(), ENV))
        self.assertFalse(packet.allowed(event(owner="visitor"), ENV))

    def test_wrong_event_rejected(self):
        self.assertFalse(packet.allowed(event(action="edited"), ENV))
        self.assertFalse(packet.allowed(event(), {**ENV, "GITHUB_EVENT_NAME": "pull_request"}))
        self.assertFalse(packet.allowed(event(), {**ENV, "GITHUB_REF": "refs/heads/topic"}))

    def test_no_agent_launched_claims(self):
        txt = packet.make_packet(pr(), files(), False)
        for term in ["Claude未実行", "Cue未実行", "有料APIは呼んでいません", HEAD, "safe code change"]:
            self.assertIn(term, txt)

    def test_patch_is_bounded_and_masks_tokens(self):
        patch_text = "ghp_" + "X" * 30 + "\n" + "x" * 20000
        txt = packet.make_packet(pr(), [{"filename": "x.py", "patch": patch_text}], False)
        self.assertIn("[REDACTED_TOKEN]", txt)
        self.assertNotIn("ghp_" + "X" * 30, txt)
        self.assertLess(len(txt), 8000)

    def test_untrusted_code_fence_is_neutralized(self):
        source_fence = chr(96) * 3 + "python"
        txt = packet.make_packet(pr(), [{"filename":"x.py", "patch":source_fence}], False)
        self.assertNotIn(source_fence, txt)

    def test_invalid_sha_is_rejected(self):
        with self.assertRaises(ValueError):
            packet.make_packet(pr("bad-sha"), files(), False)

    def test_workflow_executes_only_trusted_main(self):
        wf = (SOURCE.parent.parent / "workflows/ai-review-handoff.yml").read_text("utf-8")
        self.assertIn("pull_request_target:", wf)
        self.assertIn("ref: main", wf)
        self.assertIn("persist-credentials: false", wf)
        self.assertNotIn("MANUS_API_KEY", wf)


class MockGitHub(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.temp.name) / "event.json"
        self.path.write_text(json.dumps(event()), encoding="utf-8")
        self.env = {**ENV, "GITHUB_EVENT_PATH": str(self.path)}

    def tearDown(self):
        self.temp.cleanup()

    def test_nonowner_no_api_calls(self):
        self.path.write_text(json.dumps(event(owner="visitor")), encoding="utf-8")
        with patch.dict(os.environ, self.env), patch.object(packet, "github") as api:
            packet.main()
            api.assert_not_called()

    def test_new_pr_creates_comment(self):
        created = []
        def fake(path, method="GET", payload=None):
            if path == "/pulls/8":
                return pr()
            if path.startswith("/pulls/8/files"):
                return files()
            if path.startswith("/issues/8/comments?"):
                return []
            if path == "/issues/8/comments" and method == "POST":
                created.append(payload["body"])
                return {"id": 98}
            raise AssertionError((path,method))
        with patch.dict(os.environ, self.env), patch.object(packet, "github", side_effect=fake):
            packet.main()
        self.assertEqual(len(created), 1)
        self.assertIn(packet.MARKER, created[0])

    def test_changed_commit_updates_existing_bot_comment(self):
        self.path.write_text(json.dumps(event(action="synchronize", sha=OTHER)), encoding="utf-8")
        results = []
        def fake(path, method="GET", payload=None):
            if path == "/pulls/8":
                return pr(OTHER)
            if path.startswith("/pulls/8/files"):
                return files()
            if path.startswith("/issues/8/comments?"):
                return [{"id": 98, "user": {"login": "github-actions[bot]"},
                         "body": packet.MARKER + "old"}]
            if path == "/issues/comments/98" and method == "PATCH":
                results.append(payload["body"])
                return {"id": 98}
            raise AssertionError((path,method))
        with patch.dict(os.environ, self.env), patch.object(packet, "github", side_effect=fake):
            packet.main()
        self.assertEqual(len(results), 1)
        self.assertIn(OTHER, results[0])

    def test_stale_event_does_not_post(self):
        def fake(path, method="GET", payload=None):
            if path == "/pulls/8":
                return pr(OTHER)
            raise AssertionError("Stale event should stop")
        with patch.dict(os.environ, self.env), patch.object(packet, "github", side_effect=fake):
            packet.main()


if __name__ == "__main__":
    unittest.main()
