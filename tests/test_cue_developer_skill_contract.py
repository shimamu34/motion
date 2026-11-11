#!/usr/bin/env python3
"""Static checks of Cue Skill, without invoking any AI/API."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/cue-developer-motion-pr-review/SKILL.md"
DOC = ROOT / "docs/CUE_DEVELOPER_PORTABLE_SKILL_SETUP.md"


class CueSkillContractTests(unittest.TestCase):
    def setUp(self):
        self.content = SKILL.read_text(encoding="utf-8")
        self.instructions = DOC.read_text(encoding="utf-8")

    def test_skill_exists_in_expected_path(self):
        self.assertTrue(SKILL.is_file())

    def test_front_matter_and_name(self):
        self.assertTrue(self.content.startswith("---\n"))
        self.assertRegex(self.content, r"(?m)^name: cue-developer-motion-pr-review$")
        self.assertRegex(self.content, r"(?m)^description:")

    def test_public_repository_restricted(self):
        self.assertIn("https://github.com/shimamu34/motion", self.content)
        self.assertIn("Cue by Manus", self.content)
        self.assertIn("developer", self.content)
        self.assertIn("Cue OS", self.content)

    def test_results_use_existing_owner_only_ledger_contract(self):
        self.assertIn("/ai-result cue <確認したHEADの40文字SHA>", self.content)
        self.assertIn("所有者本人のコメント", self.content)
        self.assertIn("HEAD SHA", self.content)

    def test_avoid_cross_account_api_keys_and_unapproved_writes(self):
        for term in ["APIキー", "コミット", "デプロイ", "有料API", "Manus"]:
            self.assertIn(term, self.content)
        self.assertIn("別アカウント", self.content)
        self.assertIn("明示承認", self.content)

    def test_public_data_safety_warnings(self):
        for term in ["生徒", "個人情報", "秘密", "公開"]:
            self.assertIn(term, self.content)

    def test_setup_is_honest_about_manual_steps(self):
        for term in ["未実装", "確認", "未設定", "Cue", "別"]:
            self.assertIn(term, self.instructions)
        self.assertNotIn("完全自動連携が完成", self.instructions)

    def test_no_tokens_embedded_in_skill(self):
        forbidden = [r"ghp_[A-Za-z0-9]{20,}", r"sk-[A-Za-z0-9]{16,}"]
        for pattern in forbidden:
            self.assertNotRegex(self.content, pattern)


if __name__ == "__main__":
    unittest.main()
