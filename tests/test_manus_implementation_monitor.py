#!/usr/bin/env python3
"""Offline monitor tests: no network, GitHub writes or Manus API calls."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
import manus_implementation_monitor as mon
import manus_implementation_dispatch as disp

SHA = "a" * 40
NEW = "b" * 40
TASK_ID = "MockTaskID123456789"
N = 23


def bot_comment(state="DISPATCHED_NOT_VERIFIED", task_id=TASK_ID, sha=SHA):
    marker = disp.reservation_marker(N, sha)
    return {"id": 787, "user": {"login": "github-actions[bot]"},
            "body": disp.status_note(marker, N, sha, state,
                                     "Manus task ID: " + task_id)}


class FakeGitHub:
    def __init__(self, comments=None, current_sha=SHA, prs=None):
        self.comments = [bot_comment()] if comments is None else comments
        self.current_sha = current_sha
        self.prs = ([{"number": N, "user": {"login": "shimamu34"},
                      "base": {"ref": "main"}}] if prs is None else prs)
        self.calls = []

    def __call__(self, path, method="GET", payload=None):
        self.calls.append((path, method, payload))
        if path == "/pulls?state=open&per_page=100":
            return self.prs
        if path.startswith(f"/issues/{N}/comments?"):
            return self.comments
        if path == f"/pulls/{N}":
            return {"head": {"sha": self.current_sha}}
        if path == "/issues/comments/787" and method == "PATCH":
            return {"id": 787}
        raise AssertionError((path, method))

    def writes(self):
        return [x for x in self.calls if x[1] != "GET"]


class MonitorTests(unittest.TestCase):
    def test_extract_authenticated_open_task(self):
        task = mon.extract_task(bot_comment(), N)
        self.assertEqual(task["task_id"], TASK_ID)
        self.assertEqual(task["sha"], SHA)

    def test_non_bot_comment_ignored(self):
        c = bot_comment()
        c["user"]["login"] = "anonymous"
        self.assertIsNone(mon.extract_task(c, N))

    def test_wrong_pr_and_terminal_comment_ignored(self):
        self.assertIsNone(mon.extract_task(bot_comment(), 24))
        self.assertIsNone(mon.extract_task(bot_comment(state="STOPPED_NO_CHANGE_NEEDS_REVIEW"), N))

    def test_no_open_pr_never_calls_manus(self):
        fake = FakeGitHub(prs=[])
        def forbidden(_):
            self.fail("Manus should not be called")
        self.assertEqual(mon.monitor(api=fake, detail_api=forbidden), (0, 0))
        self.assertEqual(fake.writes(), [])

    def test_running_task_is_not_mistaken_for_finished(self):
        fake = FakeGitHub()
        self.assertEqual(mon.monitor(api=fake, detail_api=lambda _: {"task": {"status": "running"}}), (1, 0))
        self.assertEqual(fake.writes(), [])

    def test_stopped_without_branch_change_needs_review(self):
        fake = FakeGitHub()
        data = {"task": {"status": "stopped", "has_running_background_jobs": False}}
        self.assertEqual(mon.monitor(api=fake, detail_api=lambda _: data), (1, 1))
        self.assertEqual(len(fake.writes()), 1)
        note = fake.writes()[0][2]["body"]
        self.assertIn("STOPPED_NO_CHANGE_NEEDS_REVIEW", note)
        self.assertIn("コード完成", note)
        self.assertIn("Manus task ID: " + TASK_ID, note)

    def test_stopped_with_branch_change_is_not_automatically_approved(self):
        fake = FakeGitHub(current_sha=NEW)
        data = {"task": {"status": "stopped", "has_running_background_jobs": False}}
        self.assertEqual(mon.monitor(api=fake, detail_api=lambda _: data), (1, 1))
        note = fake.writes()[0][2]["body"]
        self.assertIn("STOPPED_PR_CHANGED_NEEDS_REVIEW", note)
        self.assertIn(NEW, note)

    def test_background_jobs_prevent_terminal_marker(self):
        fake = FakeGitHub()
        data = {"task": {"status": "stopped", "has_running_background_jobs": True}}
        self.assertEqual(mon.monitor(api=fake, detail_api=lambda _: data), (1, 0))
        self.assertEqual(fake.writes(), [])

    def test_waiting_for_input_recorded(self):
        fake = FakeGitHub()
        self.assertEqual(mon.monitor(api=fake, detail_api=lambda _: {"task": {"status": "waiting"}}), (1, 1))
        self.assertIn("WAITING_NEEDS_ATTENTION", fake.writes()[0][2]["body"])

    def test_error_recorded_without_new_task(self):
        fake = FakeGitHub()
        self.assertEqual(mon.monitor(api=fake, detail_api=lambda _: {"task": {"status": "error"}}), (1, 1))
        self.assertIn("ERROR_NEEDS_ATTENTION", fake.writes()[0][2]["body"])

    def test_unknown_remote_status_not_marked_complete(self):
        fake = FakeGitHub()
        self.assertEqual(mon.monitor(api=fake, detail_api=lambda _: {"bad": "data"}), (1, 0))
        self.assertEqual(fake.writes(), [])

    def test_invalid_current_sha_does_not_update(self):
        fake = FakeGitHub(current_sha="not-a-real-sha")
        data = {"task": {"status": "stopped", "has_running_background_jobs": False}}
        self.assertEqual(mon.monitor(api=fake, detail_api=lambda _: data), (0, 0))
        self.assertEqual(fake.writes(), [])

    def test_comment_page_overflow_is_blocked(self):
        fake = FakeGitHub(comments=[{"id": j} for j in range(100)])
        with self.assertRaisesRegex(RuntimeError, "truncated"):
            mon.monitor(api=fake, detail_api=lambda _: {})
        self.assertEqual(fake.writes(), [])

    def test_open_prs_overflow_is_blocked(self):
        fake = FakeGitHub(prs=[{"number": i} for i in range(100)])
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            mon.monitor(api=fake, detail_api=lambda _: {})
        self.assertEqual(fake.writes(), [])

    def test_monitor_workflow_can_edit_pr_comments(self):
        wf = (ROOT / ".github" / "workflows" / "manus-implementation-monitor.yml").read_text("utf-8")
        self.assertIn("  issues: write\n  pull-requests: write\n", wf)
        self.assertIn("vars.ENABLE_MANUS_IMPLEMENTATION == 'true'", wf)
        self.assertIn("workflow_dispatch:", wf)
        self.assertIn("schedule:", wf)
        self.assertNotIn("task.create", wf)



if __name__ == "__main__":
    unittest.main()
