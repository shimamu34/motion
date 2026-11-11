"""Offline regression checks for the opt-in Claude GitHub workflow.

Compiles embedded Python without executing the workflow, GitHub APIs, or Claude.
"""
from pathlib import Path
import re
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "claude-code-review-opt-in.yml"


def inline_python():
    contents = WORKFLOW.read_text(encoding="utf-8")
    step_name = "      - name: Record completion of the approved Claude Code action\n"
    if contents.count(step_name) != 1:
        raise AssertionError("Expected exactly one Claude completion step")
    step = contents.split(step_name, 1)[1]
    match = re.search(r"(?m)^        run: \|\n((?:          .*(?:\n|$))+)", step)
    if match is None:
        raise AssertionError("No inline completion script found")
    block = textwrap.dedent(match.group(1))
    script = re.search(r"(?s)^python3 - <<'PY'\n(.*?)\nPY\s*$", block)
    if script is None:
        raise AssertionError("Completion script must use closed Python heredoc")
    return script.group(1)


class ClaudeOptInWorkflowTests(unittest.TestCase):
    def test_completion_inline_python_compiles(self):
        compile(inline_python(), str(WORKFLOW) + "::inline-python", "exec")

    def test_workflow_remains_explicitly_opt_in(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.event.comment.body == '/claude-review'", text)
        self.assertIn("vars.ENABLE_CLAUDE_DIRECT_REVIEW == 'true'", text)
        self.assertIn("github.event.comment.user.login == 'shimamu34'", text)
        self.assertIn("github.event.issue.pull_request != null", text)

    def test_completion_requires_review_gate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("if: always() && steps.gate.outputs.should_run == 'true'", text)
        self.assertIn("ACTION_FINISHED_NEEDS_INDEPENDENT_REVIEW", text)

    def test_does_not_run_paid_claude_in_test_suite(self):
        script = inline_python()
        self.assertIn("guard.format_note(", script)
        self.assertNotIn("task.create", script)


if __name__ == "__main__":
    unittest.main()
