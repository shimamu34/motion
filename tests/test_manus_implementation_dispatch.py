#!/usr/bin/env python3
"""All tests are offline and use fake GitHub/Manus clients; no AI credits."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
import manus_implementation_dispatch as m

SHA = "a" * 40
OTHER = "b" * 40
NUMBER = 17
BODY = """<!-- manus-implementation-request:v1 -->

## 実装内容
既存の運動分析アプリの表示メッセージを明確化し、モデル読込失敗時に利用者に分かるエラー表示を行う。

## 完了条件
既存の動画操作を維持し、新しく追加したエラー表示の表示条件をテストする。未実施のテストは明示する。
"""
ENV = {
    "GITHUB_EVENT_NAME": "issue_comment",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_REPOSITORY": "shimamu34/motion",
    "ENABLE_MANUS_IMPLEMENTATION": "true",
    "GH_TOKEN": "mock-github-token",
    "MANUS_API_KEY": "mock-manus-key",
}


def event(command="/manus-implement " + SHA, actor="shimamu34", with_pr=True):
    return {"action": "created", "repository": {"full_name": m.REPO},
            "issue": {"number": NUMBER, "pull_request": {"url": "safe"}
                      if with_pr else None},
            "comment": {"user": {"login": actor}, "body": command}}


def pr(**overrides):
    p = {
        "state": "open", "merged": False, "draft": True,
        "user": {"login": "shimamu34"}, "base": {"ref": "main"},
        "head": {"sha": SHA, "ref": "feature/message-fix",
                 "repo": {"full_name": "shimamu34/motion"}},
        "body": BODY, "html_url": "https://github.com/shimamu34/motion/pull/17",
    }
    p.update(overrides)
    return p


class FakeGitHub:
    def __init__(self, pr_versions=None, comments=None):
        self.pr_versions = pr_versions or [pr()]
        self.comments = comments if comments is not None else []
        self.calls = []
        self.pr_reads = 0

    def __call__(self, path, method="GET", payload=None):
        self.calls.append((path, method, payload))
        if path == f"/pulls/{NUMBER}" and method == "GET":
            idx = min(self.pr_reads, len(self.pr_versions) - 1)
            self.pr_reads += 1
            return copy.deepcopy(self.pr_versions[idx])
        if path.startswith(f"/issues/{NUMBER}/comments?") and method == "GET":
            return copy.deepcopy(self.comments)
        if path == f"/issues/{NUMBER}/comments" and method == "POST":
            return {"id": 12345}
        if path == "/issues/comments/12345" and method == "PATCH":
            return {"id": 12345}
        raise AssertionError((path, method))

    def writes(self):
        return [(path, method, payload) for path, method, payload in self.calls
                if method in ("POST", "PATCH")]


class ApprovalContractTests(unittest.TestCase):
    def test_owner_exact_command_with_sha_is_accepted(self):
        self.assertEqual(m.valid_event(event(), ENV), SHA)

    def test_wrong_owner_is_rejected(self):
        self.assertIsNone(m.valid_event(event(actor="stranger"), ENV))

    def test_no_plain_implement_or_extra_words(self):
        for command in ["/manus-implement", "/manus-implement " + SHA + " approve",
                        "/manus-review", "/manus-implement notsha"]:
            self.assertIsNone(m.valid_event(event(command=command), ENV))

    def test_issue_not_pr_is_rejected(self):
        self.assertIsNone(m.valid_event(event(with_pr=False), ENV))

    def test_event_from_other_repository_rejected(self):
        self.assertIsNone(m.valid_event(event(), {**ENV, "GITHUB_REPOSITORY": "someone/else"}))

    def test_pr_metadata_requires_draft_local_owner_and_main(self):
        for bad in [
            {"draft": False}, {"merged": True}, {"state": "closed"},
            {"user": {"login": "other"}}, {"base": {"ref": "not-main"}},
            {"head": {"sha": SHA, "ref": "feature/fix",
                      "repo": {"full_name": "fork/motion"}}},
            {"head": {"sha": SHA, "ref": "main",
                      "repo": {"full_name": m.REPO}}},
            {"head": {"sha": SHA, "ref": "test/cue",
                      "repo": {"full_name": m.REPO}}},
        ]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                m.validate_pr(pr(**bad), SHA)

    def test_explicit_head_match_required(self):
        with self.assertRaises(ValueError):
            m.validate_pr(pr(), OTHER)

    def test_bounded_pr_description_and_sections(self):
        for body in ["", "too short", BODY.replace(m.REQUEST_MARKER, ""),
                     BODY.replace("## 実装内容", "## 曖昧な見出し"),
                     BODY * 30]:
            with self.subTest(length=len(body)), self.assertRaises(ValueError):
                m.validate_pr(pr(body=body), SHA)

    def test_prompt_has_strict_boundaries(self):
        text = m.prompt_for(pr(), "feature/message-fix", BODY)
        self.assertIn("BEGIN UNTRUSTED PR DESCRIPTION", text)
        self.assertIn("main", text)
        self.assertIn("PR作成、マージ、デプロイ", text)
        self.assertNotIn("MANUS_API_KEY", text)

    def test_disabled_flag_calls_nothing(self):
        with patch.object(m, "github") as gh, patch.object(m, "create_manus_task") as ai:
            self.assertEqual(m.dispatch(event(), {**ENV, "ENABLE_MANUS_IMPLEMENTATION": ""}), "DISABLED")
        gh.assert_not_called()
        ai.assert_not_called()

    def test_nonowner_does_not_call_api(self):
        with patch.object(m, "github") as gh, patch.object(m, "create_manus_task") as ai:
            self.assertEqual(m.dispatch(event(actor="stranger"), ENV), "SKIPPED")
        gh.assert_not_called()
        ai.assert_not_called()

    def test_duplicate_sha_blocks_second_paid_task(self):
        comments = [{"user": {"login": "github-actions[bot]"},
                     "body": m.reservation_marker(NUMBER, SHA)}]
        gh = FakeGitHub(comments=comments)
        with patch.object(m, "github", side_effect=gh), patch.object(m, "create_manus_task") as ai:
            self.assertEqual(m.dispatch(event(), ENV), "ALREADY_RESERVED")
        ai.assert_not_called()
        self.assertFalse(gh.writes())

    def test_exact_one_task_after_reservation(self):
        gh = FakeGitHub()
        events = []
        def tracked_api(payload):
            events.append("manus")
            self.assertEqual(payload["agent_profile"], "lite")
            self.assertEqual(payload["share_visibility"], "private")
            self.assertIn("feature/message-fix", payload["message"]["content"])
            return {"ok": True, "task_id": "ABCDE12345"}
        with patch.object(m, "github", side_effect=lambda *a, **kw: self.track_gh(gh, events, *a, **kw)), \
             patch.object(m, "create_manus_task", side_effect=tracked_api):
            self.assertEqual(m.dispatch(event(), ENV), "DISPATCHED")
        self.assertEqual(events.count("manus"), 1)
        self.assertLess(events.index("reserve"), events.index("manus"))
        self.assertEqual(len([x for x in gh.writes() if x[1] == "POST"]), 1)
        self.assertEqual(len([x for x in gh.writes() if x[1] == "PATCH"]), 1)

    @staticmethod
    def track_gh(gh, events, path, method="GET", payload=None):
        if method == "POST":
            events.append("reserve")
        return gh(path, method, payload)

    def test_changed_head_before_reservation_is_not_charged(self):
        gh = FakeGitHub(pr_versions=[pr(), pr(head={"ref": "feature/message-fix",
                 "sha": OTHER, "repo": {"full_name": m.REPO}})])
        with patch.object(m, "github", side_effect=gh), patch.object(m, "create_manus_task") as ai:
            self.assertEqual(m.dispatch(event(), ENV), "STALE")
        ai.assert_not_called()
        self.assertFalse(gh.writes())

    def test_changed_head_after_reservation_is_not_charged(self):
        gh = FakeGitHub(pr_versions=[pr(), pr(), pr(head={"ref": "feature/message-fix",
                 "sha": OTHER, "repo": {"full_name": m.REPO}})])
        with patch.object(m, "github", side_effect=gh), patch.object(m, "create_manus_task") as ai:
            self.assertEqual(m.dispatch(event(), ENV), "STALE")
        ai.assert_not_called()
        self.assertEqual([method for _, method, _ in gh.writes()], ["POST", "PATCH"])

    def test_task_error_never_triggers_retry(self):
        gh = FakeGitHub()
        with patch.object(m, "github", side_effect=gh), \
             patch.object(m, "create_manus_task", side_effect=RuntimeError("mock failure")) as ai:
            with self.assertRaisesRegex(RuntimeError, "do not retry"):
                m.dispatch(event(), ENV)
        self.assertEqual(ai.call_count, 1)
        self.assertEqual([method for _, method, _ in gh.writes()], ["POST", "PATCH"])
        self.assertIn("TASK_CREATION_UNCONFIRMED", gh.writes()[-1][-1]["body"])

    def test_unapproved_spec_is_not_charged(self):
        gh = FakeGitHub(pr_versions=[pr(body="no details")])
        with patch.object(m, "github", side_effect=gh), patch.object(m, "create_manus_task") as ai:
            self.assertEqual(m.dispatch(event(), ENV), "BLOCKED")
        ai.assert_not_called()

    def test_unknown_comment_pagination_refuses_dispatch(self):
        gh = FakeGitHub(comments=[{"id": i} for i in range(100)])
        with patch.object(m, "github", side_effect=gh), patch.object(m, "create_manus_task") as ai:
            with self.assertRaisesRegex(RuntimeError, "pagination incomplete"):
                m.dispatch(event(), ENV)
        ai.assert_not_called()
        self.assertFalse(gh.writes())


if __name__ == "__main__":
    unittest.main()
