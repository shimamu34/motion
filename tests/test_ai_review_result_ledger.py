#!/usr/bin/env python3
"""Offline regression checks, no network calls, no AI usage."""
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

FILE = pathlib.Path(__file__).resolve().parents[1] / ".github/scripts/ai_review_result_ledger.py"
spec = importlib.util.spec_from_file_location("ai_review_ledger", FILE)
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)

SHA_A, SHA_B = "a" * 40, "b" * 40
ENV = {
    "GITHUB_EVENT_NAME": "issue_comment",
    "GITHUB_REPOSITORY": "shimamu34/motion",
    "GITHUB_REF": "refs/heads/main",
    "GH_TOKEN": "FAKE_TEST_TOKEN",
}


def submission(role="claude", sha=SHA_A, text="Detailed review with file references"):
    return "/ai-result " + role + " " + sha + "\n" + text


def comment_event(author="shimamu34", body=None):
    return {
        "action": "created", "repository": {"full_name": "shimamu34/motion"},
        "issue": {"number": 8, "pull_request": {"url": "https://api.github.com/test"}},
        "comment": {"user": {"login": author}, "body": body or submission()},
    }


def update_event(sha=SHA_A, author="shimamu34"):
    return {
        "action": "synchronize", "repository": {"full_name": "shimamu34/motion"},
        "pull_request": {"number": 8, "head": {"sha": sha},
                         "user": {"login": author}},
    }


def pr(head=SHA_A):
    return {
        "number": 8, "state": "open", "merged": False,
        "base": {"ref": "main"},
        "user": {"login": "shimamu34"},
        "head": {"sha": head},
    }


def review_comment(id_, role="claude", sha=SHA_A, author="shimamu34"):
    return {"id": id_, "user": {"login": author}, "body": submission(role, sha)}


class InputTests(unittest.TestCase):
    def test_correct_claude_result(self):
        role, sha, text = ledger.parse_submission(submission())
        self.assertEqual(role, "claude")
        self.assertEqual(sha, SHA_A)
        self.assertIn("Detailed review", text)

    def test_cue_case_insensitive_and_crlf(self):
        r = ledger.parse_submission(submission("CuE").replace("\n", "\r\n"))
        self.assertEqual(r[0], "cue")

    def test_missing_sha_and_unknown_role_rejected(self):
        for body in ["/ai-result claude\nreview text", submission("manus"),
                     "/ai-result claude invalidsha\nlong text",
                     "/ai-result cue " + SHA_A + "\nshort"]:
            with self.assertRaises(ValueError):
                ledger.parse_submission(body)

    def test_very_long_result_is_rejected(self):
        with self.assertRaises(ValueError):
            ledger.parse_submission(submission(text="x" * 30000))


class EventTests(unittest.TestCase):
    def test_owner_comment_is_approved(self):
        self.assertTrue(ledger.approved_event(comment_event(), ENV))

    def test_strangers_or_wrong_commands_are_ignored(self):
        self.assertFalse(ledger.approved_event(comment_event(author="stranger"), ENV))
        self.assertFalse(ledger.approved_event(comment_event(body="/manus-review"), ENV))

    def test_wrong_repo_branch_and_event_are_ignored(self):
        self.assertFalse(ledger.approved_event(comment_event(), {**ENV, "GITHUB_REPOSITORY": "other/repo"}))
        self.assertFalse(ledger.approved_event(comment_event(), {**ENV, "GITHUB_REF": "refs/heads/feature"}))
        self.assertFalse(ledger.approved_event(comment_event(), {**ENV, "GITHUB_EVENT_NAME": "pull_request"}))

    def test_owner_sync_is_approved(self):
        env = {**ENV, "GITHUB_EVENT_NAME": "pull_request_target"}
        self.assertTrue(ledger.approved_event(update_event(), env))
        self.assertFalse(ledger.approved_event(update_event(author="stranger"), env))

    def test_workflow_runs_trusted_main_without_secrets(self):
        wf = (FILE.parent.parent / "workflows/ai-review-result-ledger.yml").read_text("utf-8")
        for t in ["issue_comment:", "pull_request_target:", "ref: main",
                  "issues: write", "pull-requests: write", "cancel-in-progress: false"]:
            self.assertIn(t, wf)
        for t in ["MANUS_API_KEY", "ANTHROPIC_API_KEY", "checkout: " + chr(36) + "{{ github.event.pull_request.head.sha }}"]:
            self.assertNotIn(t, wf)


class CollectionTests(unittest.TestCase):
    def test_latest_owner_comment_per_role(self):
        comments = [review_comment(11), review_comment(12, "cue"), review_comment(13)]
        found, bot = ledger.review_entries(comments, SHA_A)
        self.assertEqual(found["claude"]["id"], 13)
        self.assertEqual(found["cue"]["id"], 12)
        self.assertIsNone(bot)

    def test_other_sha_does_not_count(self):
        found, _ = ledger.review_entries([review_comment(11, sha=SHA_B)], SHA_A)
        self.assertEqual(found, {})

    def test_stranger_cannot_spoof_review(self):
        found, _ = ledger.review_entries([review_comment(11, author="stranger")], SHA_A)
        self.assertEqual(found, {})

    def test_bot_ledger_is_reused(self):
        comment = {"id": 100, "user": {"login": "github-actions[bot]"},
                   "body": ledger.MARKER + "\nold content"}
        found, existing = ledger.review_entries([comment], SHA_A)
        self.assertEqual(found, {})
        self.assertEqual(existing["id"], 100)

    def test_ledger_has_links_not_copied_review_text(self):
        input_text = "SensitiveUnverifiedReviewContent"
        review = review_comment(11)
        review["body"] = submission(text=input_text)
        found, _ = ledger.review_entries([review], SHA_A)
        body = ledger.ledger_text(8, SHA_A, found)
        self.assertIn("#issuecomment-11", body)
        self.assertNotIn(input_text, body)
        self.assertIn("未検証", body)
        self.assertIn("公開", body)
        self.assertIn("/ai-result claude", body)


class MockFullFlow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.event_file = pathlib.Path(self.temp.name) / "event.json"
        self.event_file.write_text(json.dumps(comment_event()), encoding="utf-8")
        self.env = {**ENV, "GITHUB_EVENT_PATH": str(self.event_file)}

    def tearDown(self):
        self.temp.cleanup()

    def test_new_submission_creates_one_ledger(self):
        calls = []
        def api(path, method="GET", payload=None):
            if path == "/pulls/8":
                return pr()
            if path.startswith("/issues/8/comments?"):
                return [review_comment(11)]
            if path == "/issues/8/comments" and method == "POST":
                calls.append((path, payload["body"]))
                return {"id": 200}
            raise AssertionError((path, method))
        with patch.dict(os.environ, self.env), patch.object(ledger, "github", side_effect=api):
            ledger.main()
        self.assertEqual(len(calls), 1)
        self.assertIn("#issuecomment-11", calls[0][1])

    def test_existing_bot_ledger_is_updated(self):
        old = {"id": 100, "user": {"login": "github-actions[bot]"},
               "body": ledger.MARKER + "\nold"}
        calls = []
        def api(path, method="GET", payload=None):
            if path == "/pulls/8":
                return pr()
            if path.startswith("/issues/8/comments?"):
                return [old, review_comment(11), review_comment(12, "cue")]
            if path == "/issues/comments/100" and method == "PATCH":
                calls.append(payload["body"])
                return {"id": 100}
            raise AssertionError((path,method))
        with patch.dict(os.environ, self.env), patch.object(ledger, "github", side_effect=api):
            ledger.main()
        self.assertEqual(len(calls), 1)
        self.assertIn("#issuecomment-12", calls[0])

    def test_after_head_update_old_results_become_unregistered(self):
        old = {"id": 100, "user": {"login": "github-actions[bot]"},
               "body": ledger.MARKER + "\nold"}
        self.event_file.write_text(json.dumps(update_event(sha=SHA_B)), encoding="utf-8")
        env = {**self.env, "GITHUB_EVENT_NAME": "pull_request_target"}
        updates = []
        def api(path, method="GET", payload=None):
            if path == "/pulls/8":
                return pr(SHA_B)
            if path.startswith("/issues/8/comments?"):
                return [old, review_comment(11, sha=SHA_A)]
            if path == "/issues/comments/100" and method == "PATCH":
                updates.append(payload["body"])
                return {"id": 100}
            raise AssertionError(path)
        with patch.dict(os.environ, env), patch.object(ledger, "github", side_effect=api):
            ledger.main()
        self.assertEqual(len(updates), 1)
        self.assertIn(SHA_B, updates[0])
        self.assertIn("| Claude | 未登録・未確認", updates[0])

    def test_after_head_update_without_previous_ledger_no_post(self):
        self.event_file.write_text(json.dumps(update_event(sha=SHA_B)), encoding="utf-8")
        env = {**self.env, "GITHUB_EVENT_NAME": "pull_request_target"}
        def api(path, method="GET", payload=None):
            if path == "/pulls/8":
                return pr(SHA_B)
            if path.startswith("/issues/8/comments?"):
                return []
            raise AssertionError("No comment should be created when none previously existed")
        with patch.dict(os.environ, env), patch.object(ledger, "github", side_effect=api):
            ledger.main()

    def test_stale_comment_does_not_write_anything(self):
        with patch.dict(os.environ, self.env), patch.object(ledger, "github", return_value=pr(SHA_B)) as api:
            ledger.main()
        self.assertEqual(api.call_count, 1)

    def test_wrong_actor_does_not_access_github(self):
        self.event_file.write_text(json.dumps(comment_event(author="stranger")), encoding="utf-8")
        with patch.dict(os.environ, self.env), patch.object(ledger, "github") as api:
            ledger.main()
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
