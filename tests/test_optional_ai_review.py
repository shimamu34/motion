#!/usr/bin/env python3
"""All tests use mocks; no Claude or Cue API credentials or network access."""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

SRC = pathlib.Path(__file__).resolve().parents[1] / ".github/scripts"
sys.path.insert(0, str(SRC))
import optional_ai_review_gate as gate
import cue_review_via_manus as cue

SHA = "a" * 40
OTHER_SHA = "b" * 40
TASK = "A" * 22
ENV = {
    "GITHUB_EVENT_NAME": "issue_comment",
    "GITHUB_REPOSITORY": "shimamu34/motion",
    "GITHUB_REF": "refs/heads/main",
    "DIRECT_REVIEW_ENABLED": "true",
    "CLAUDE_CODE_OAUTH_TOKEN": "fake-oauth-only-for-mock",
    "MANUS_API_KEY": "fake-manus-key-only-for-mock",
    "CUE_AGENT_TASK_ID": TASK,
    "GH_TOKEN": "fake-github-token-only-for-mock",
}


def event(actor="shimamu34", command="/cue-review", number=7, pr=True):
    return {
        "action": "created",
        "repository": {"full_name": "shimamu34/motion"},
        "issue": {"number": number, "pull_request": {"url": "x"} if pr else None},
        "comment": {"user": {"login": actor}, "body": command},
    }


def pr(sha=SHA, number=7):
    return {
        "number": number,
        "state": "open",
        "merged": False,
        "user": {"login": "shimamu34"},
        "head": {"sha": sha},
        "base": {"ref": "main"},
        "title": "Test PR title",
    }


class GateValidation(unittest.TestCase):
    def test_only_owner_exact_command(self):
        self.assertTrue(gate.valid_event(event(), ENV, "cue"))
        self.assertFalse(gate.valid_event(event(actor="visitor"), ENV, "cue"))
        self.assertFalse(gate.valid_event(event(pr=False), ENV, "cue"))
        self.assertFalse(gate.valid_event(event(command="/cue-review again"), ENV, "cue"))
        self.assertTrue(gate.valid_event(event(command="/claude-review"), ENV, "claude"))
        self.assertFalse(gate.valid_event(event(command="/cue-review"), ENV, "claude"))

    def test_wrong_repository_or_event(self):
        self.assertFalse(gate.valid_event(event(), {**ENV, "GITHUB_REPOSITORY": "not-this-repo"}, "cue"))
        self.assertFalse(gate.valid_event(event(), {**ENV, "GITHUB_REF": "refs/heads/other"}, "cue"))
        self.assertFalse(gate.valid_event(event(), {**ENV, "GITHUB_EVENT_NAME": "pull_request"}, "cue"))

    def test_disabled_feature_flag_prevents_all_github_access(self):
        with patch.object(gate, "github") as gh:
            self.assertIsNone(gate.gate(event(), {**ENV, "DIRECT_REVIEW_ENABLED": ""}, "cue"))
            gh.assert_not_called()

    def test_missing_claude_credential_stops_before_access(self):
        with patch.object(gate, "github") as gh:
            self.assertIsNone(gate.gate(event(command="/claude-review"),
                                        {**ENV, "CLAUDE_CODE_OAUTH_TOKEN": ""}, "claude"))
            gh.assert_not_called()

    def test_missing_or_wrong_cue_agent_task_id_stops_before_access(self):
        with patch.object(gate, "github") as gh:
            for invalid in ["", "agent-default-main_task", "short"]:
                self.assertIsNone(gate.gate(event(), {**ENV, "CUE_AGENT_TASK_ID": invalid}, "cue"))
            gh.assert_not_called()

    def test_marker_is_sha_and_provider_specific(self):
        self.assertNotEqual(gate.marker("cue", 7, SHA), gate.marker("cue", 7, OTHER_SHA))
        self.assertNotEqual(gate.marker("cue", 7, SHA), gate.marker("claude", 7, SHA))
        with self.assertRaises(ValueError):
            gate.marker("cue", 7, "garbage")

    def test_duplicate_marker_blocks_second_paid_request(self):
        note = {"id": 1234, "user": {"login": "github-actions[bot]"},
                "body": gate.marker("cue", 7, SHA)}
        def api(path, method="GET", payload=None):
            if path == "/pulls/7":
                return pr()
            if path.startswith("/issues/7/comments?"):
                return [note]
            raise AssertionError((path, method))
        with patch.object(gate, "github", side_effect=api):
            self.assertIsNone(gate.gate(event(), ENV, "cue"))

    def test_new_head_between_reads_is_not_charged(self):
        reads = 0
        def api(path, method="GET", payload=None):
            nonlocal reads
            if path == "/pulls/7":
                reads += 1
                return pr(SHA if reads == 1 else OTHER_SHA)
            if path.startswith("/issues/7/comments?"):
                return []
            raise AssertionError("Should not reserve if HEAD moved")
        with patch.object(gate, "github", side_effect=api):
            self.assertIsNone(gate.gate(event(), ENV, "cue"))

    def test_one_reservation_before_dispatch(self):
        calls = []
        def api(path, method="GET", payload=None):
            if path == "/pulls/7":
                return pr()
            if path.startswith("/issues/7/comments?"):
                return []
            if path == "/issues/7/comments" and method == "POST":
                self.assertIn("RESERVED_BEFORE_AI_REQUEST", payload["body"])
                calls.append(payload["body"])
                return {"id": 200}
            raise AssertionError(path)
        with patch.object(gate, "github", side_effect=api):
            output = gate.gate(event(), ENV, "cue")
        self.assertEqual(output["pr"], 7)
        self.assertEqual(output["sha"], SHA)
        self.assertEqual(output["comment_id"], 200)
        self.assertEqual(len(calls), 1)


class CueProtocol(unittest.TestCase):
    def test_correlation_is_explicit_and_prompt_bounded(self):
        msg, correlation = cue.prompt_for(7, SHA, "Demo", "fake diff " * 999)
        self.assertEqual(correlation, "CUE_REVIEW:7:" + SHA)
        self.assertIn(correlation, msg)
        self.assertLessEqual(len(msg), cue.MAX_PROMPT)
        self.assertNotIn("fake diff " * 500, msg)

    def test_only_new_matching_reply_is_accepted(self):
        messages = [
            {"id": "old", "assistant_message": {"content": "CUE_REVIEW:7:" + SHA}},
            {"id": "another", "assistant_message": {"content": "Unrelated personal message"}},
            {"id": "new", "assistant_message": {"content": "CUE_REVIEW:7:" + SHA + "\nNo Critical issues"}},
        ]
        result = cue.scan_new_response(messages, {"old"}, "CUE_REVIEW:7:" + SHA)
        self.assertIn("No Critical issues", result)
        self.assertIsNone(cue.scan_new_response(messages[:2], {"old"}, "CUE_REVIEW:7:" + SHA))

    def test_public_output_is_off_by_default(self):
        note = cue.status_comment(7, SHA, "RECEIVED", "Safe status only")
        self.assertNotIn("## Cue by Manus 自動回答", note)
        self.assertIn("RECEIVED", note)

    def test_redaction_of_known_secrets(self):
        with patch.dict(os.environ, ENV):
            s = cue.mask("foo@example.com " + ENV["MANUS_API_KEY"] + " ghp_" + "X" * 30)
        self.assertNotIn("foo@example.com", s)
        self.assertNotIn(ENV["MANUS_API_KEY"], s)
        self.assertNotIn("ghp_", s)

    def test_invalid_target_rejected_before_manus_api(self):
        env = {
            "PR_NUMBER": "7",
            "PR_HEAD": SHA,
            "RESERVATION_COMMENT_ID": "101",
            "CUE_AGENT_TASK_ID": "agent-default-main_task",
        }
        with patch.dict(os.environ, env), patch.object(cue, "manus") as api:
            with self.assertRaises(ValueError):
                cue.main()
            api.assert_not_called()


class WorkflowChecks(unittest.TestCase):
    def test_both_provider_jobs_off_by_default(self):
        for name, flag, command in [
            ("cue-direct-review-opt-in.yml", "ENABLE_CUE_DIRECT_REVIEW", "/cue-review"),
            ("claude-code-review-opt-in.yml", "ENABLE_CLAUDE_DIRECT_REVIEW", "/claude-review"),
        ]:
            workflow = (SRC.parent / "workflows" / name).read_text("utf-8")
            self.assertIn("issue_comment:", workflow)
            self.assertNotIn("pull_request:\n", workflow)
            self.assertIn("vars." + flag + " == 'true'", workflow)
            self.assertIn("github.event.comment.body == '" + command + "'", workflow)
            self.assertIn("ref: main", workflow)
            self.assertIn("cancel-in-progress: false", workflow)

    def test_claude_uses_oauth_not_pay_as_you_go_api_key(self):
        workflow = (SRC.parent / "workflows/claude-code-review-opt-in.yml").read_text("utf-8")
        self.assertIn("claude_code_oauth_token", workflow)
        self.assertNotIn("ANTHROPIC_API_KEY", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn('--disallowedTools "Bash,Edit,Write', workflow)

    def test_cue_requires_explicit_persistent_task_secret(self):
        workflow = (SRC.parent / "workflows/cue-direct-review-opt-in.yml").read_text("utf-8")
        self.assertIn("secrets.CUE_AGENT_TASK_ID", workflow)
        self.assertIn("vars.PUBLISH_CUE_REVIEW_TEXT", workflow)
        self.assertNotIn("agent-default-main_task", workflow)


if __name__ == "__main__":
    unittest.main()
