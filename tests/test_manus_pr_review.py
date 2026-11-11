#!/usr/bin/env python3
"""Offline regression checks: no real GitHub or Manus API calls."""
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

FILE = pathlib.Path(__file__).resolve().parents[1] / ".github/scripts/manus_pr_review.py"
spec = importlib.util.spec_from_file_location("approval_gated_review", FILE)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)

SHA_A = "a" * 40
SHA_B = "b" * 40
ENV = {
    "GITHUB_EVENT_NAME": "issue_comment",
    "GITHUB_REPOSITORY": "shimamu34/motion",
    "GITHUB_REF": "refs/heads/main",
    "GH_TOKEN": "test-github-token",
    "MANUS_API_KEY": "test-manus-token",
}


def event(actor="shimamu34", command="/manus-review", is_pr=True):
    return {
        "action": "created",
        "repository": {"full_name": "shimamu34/motion"},
        "issue": {"number": 6, "pull_request": {"url": "https://api.github.com/pr/6"} if is_pr else None},
        "comment": {"user": {"login": actor}, "body": command},
    }


def pr(sha=SHA_A):
    return {"state": "open", "merged": False,
            "base": {"ref": "main"}, "head": {"sha": sha, "ref": "topic"},
            "html_url": "https://github.com/shimamu34/motion/pull/6", "title": "Fix startup"}


class PermissionTests(unittest.TestCase):
    def test_owner_pr_comment_is_approved(self):
        self.assertTrue(review.approved(event(), ENV))

    def test_stranger_cannot_spend_credits(self):
        self.assertFalse(review.approved(event(actor="some-stranger"), ENV))

    def test_non_pr_issue_is_not_approved(self):
        self.assertFalse(review.approved(event(is_pr=False), ENV))

    def test_different_comment_does_not_dispatch(self):
        self.assertFalse(review.approved(event(command="please review"), ENV))
        self.assertFalse(review.approved(event(command="/manus-review again"), ENV))

    def test_wrong_event_or_branch_rejected(self):
        self.assertFalse(review.approved(event(), {**ENV, "GITHUB_EVENT_NAME": "pull_request"}))
        self.assertFalse(review.approved(event(), {**ENV, "GITHUB_REF": "refs/heads/feature"}))
        self.assertFalse(review.approved(event(), {**ENV, "GITHUB_REPOSITORY": "another/repo"}))


class PromptAndMarkerTests(unittest.TestCase):
    def test_long_pr_diff_is_capped_before_api(self):
        txt, truncated = review.prompt_for(pr()["html_url"], SHA_A, "title", "diff --git " + "x" * 60000)
        self.assertTrue(truncated)
        self.assertLessEqual(len(txt), review.MAX_PROMPT_CHARS)
        self.assertIn(SHA_A, txt)
        self.assertNotIn("x" * 6000, txt)

    def test_short_diff_not_truncated(self):
        msg, truncated = review.prompt_for(pr()["html_url"], SHA_A, "title", "diff --git " + "x" * 70)
        self.assertFalse(truncated)
        self.assertIn("末尾省略: なし", msg)

    def test_missing_diff_aborts(self):
        with self.assertRaises(ValueError):
            review.prompt_for(pr()["html_url"], SHA_A, "title", "")

    def test_duplicate_marker_scoped_by_sha(self):
        self.assertNotEqual(review.review_marker(6, SHA_A), review.review_marker(6, SHA_B))
        self.assertNotEqual(review.review_marker(6, SHA_A), review.review_marker(7, SHA_A))
        with self.assertRaises(ValueError):
            review.review_marker(6, "unverified")

    def test_workflow_is_not_triggered_by_pr_open_or_sync(self):
        wf = (FILE.parent.parent / "workflows/manus-pr-review.yml").read_text("utf-8")
        self.assertIn("issue_comment:", wf)
        self.assertIn("'/manus-review'", wf)
        self.assertNotIn("types: [opened, synchronize", wf)
        self.assertIn("cancel-in-progress: false", wf)

    def test_sanitized_http_errors_redact_credentials(self):
        import io
        import urllib.error
        sensitive = json.dumps({"error": {"code": "InvalidArgument",
                                           "message": "bad token test-manus-token"}}).encode()
        error = urllib.error.HTTPError("https://api.manus.ai/v2/task.create",
                                       400, "Bad request", {}, io.BytesIO(sensitive))
        with patch.dict(os.environ, ENV):
            summary = review.safe_error(error)
        self.assertIn("HTTP 400", summary)
        self.assertIn("InvalidArgument", summary)
        self.assertNotIn("test-manus-token", summary)


class DispatchGuardsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.event_path = pathlib.Path(self.tmp.name) / "event.json"
        self.event_path.write_text(json.dumps(event()), encoding="utf-8")
        self.env = {**ENV, "GITHUB_EVENT_PATH": str(self.event_path)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_nonowner_does_not_call_github_or_manus(self):
        self.event_path.write_text(json.dumps(event(actor="stranger")), encoding="utf-8")
        with patch.dict(os.environ, self.env), patch.object(review, "gh") as github, patch.object(review, "manuscript") as manus:
            review.main()
        github.assert_not_called()
        manus.assert_not_called()

    def test_existing_sha_marker_blocks_duplicate_paid_task(self):
        bot_record = {"id": 41, "user": {"login": "github-actions[bot]"},
                      "body": review.review_marker(6, SHA_A) + "\nAlready reviewed"}
        def fake_gh(path, method="GET", data=None, accept=None):
            if path == "/pulls/6":
                return pr()
            if path.startswith("/issues/6/comments?"):
                return [bot_record]
            raise AssertionError("Unexpected GitHub call " + path)
        with patch.dict(os.environ, self.env), patch.object(review, "gh", side_effect=fake_gh), patch.object(review, "manuscript") as manus:
            review.main()
        manus.assert_not_called()

    def test_reserve_comment_before_single_paid_api_call(self):
        sequence = []
        def fake_gh(path, method="GET", data=None, accept=None):
            if path == "/pulls/6" and accept is None:
                return pr()
            if path.startswith("/issues/6/comments?"):
                return []
            if path == "/pulls/6" and accept is not None:
                return "diff --git " + "x" * 200
            if path == "/issues/6/comments" and method == "POST":
                sequence.append("reserved")
                self.assertIn("REQUEST_RESERVED", data["body"])
                return {"id": 9}
            if path == "/issues/comments/9" and method == "PATCH":
                sequence.append("updated")
                return {"id": 9}
            raise AssertionError(f"Unexpected GitHub call {method} {path}")
        def fake_manus(path, data=None):
            if path == "task.create":
                sequence.append("created")
                return {"ok": True, "task_id": "test-task-id",
                        "task_url": "https://manus.im/app/test-task-id"}
            if path.startswith("task.detail?"):
                return {"task": {"status": "stopped", "has_running_background_jobs": False, "credit_usage": 11}}
            if path.startswith("task.listMessages?"):
                return {"messages": [{"assistant_message": {"content": "Test only: no issues", "delivery_kind": "result"}}]}
            raise AssertionError(f"Unexpected Manus call {path}")
        with patch.dict(os.environ, self.env), patch.object(review, "gh", side_effect=fake_gh), patch.object(review, "manuscript", side_effect=fake_manus):
            review.main()
        self.assertEqual(sequence.count("created"), 1)
        self.assertLess(sequence.index("reserved"), sequence.index("created"))
        self.assertEqual(sequence.count("updated"), 2)

    def test_failed_task_creation_never_retries(self):
        sequence = []
        def fake_gh(path, method="GET", data=None, accept=None):
            if path == "/pulls/6" and accept is None:
                return pr()
            if path == "/pulls/6" and accept:
                return "diff --git " + "z" * 150
            if path.startswith("/issues/6/comments?"):
                return []
            if path == "/issues/6/comments" and method == "POST":
                sequence.append("reserved")
                return {"id": 9}
            if path == "/issues/comments/9" and method == "PATCH":
                sequence.append("error-recorded")
                self.assertIn("TASK_CREATION_UNCONFIRMED", data["body"])
                return {}
            raise AssertionError(path)
        count = 0
        def fake_manus(path, data=None):
            nonlocal count
            count += 1
            raise RuntimeError("manus request failed: HTTP 400; code=InvalidArgument; message=too large")
        with patch.dict(os.environ, self.env), patch.object(review, "gh", side_effect=fake_gh), patch.object(review, "manuscript", side_effect=fake_manus):
            with self.assertRaises(RuntimeError):
                review.main()
        self.assertEqual(count, 1)
        self.assertEqual(sequence, ["reserved", "error-recorded"])


if __name__ == "__main__":
    unittest.main()
