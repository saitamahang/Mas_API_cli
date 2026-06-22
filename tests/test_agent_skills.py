import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pangu.agent.errors import AgentError
from pangu.agent import skills


class AgentSkillTests(unittest.TestCase):
    def test_bundled_skill_names_include_agent_and_legacy_pangu(self):
        self.assertIn("pangu-agent", skills.BUNDLED_SKILL_NAMES)
        self.assertIn("pangu", skills.BUNDLED_SKILL_NAMES)

    def test_skill_sources_exist_for_all_bundled_skills(self):
        for name in skills.BUNDLED_SKILL_NAMES:
            with self.subTest(name=name):
                text, source = skills.skill_source(name)

                self.assertIn("SKILL.md", source)
                self.assertIn("src/pangu/data/skills", source)
                self.assertNotIn(".claude/skills", source)
                self.assertTrue(text.startswith("---"))

    def test_install_skill_writes_selected_skill_to_matching_destination(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch.object(skills.Path, "home", return_value=home):
                result = skills.install_skill(force=False, name="pangu")

            dest = home / ".claude" / "skills" / "pangu" / "SKILL.md"
            self.assertEqual(result["name"], "pangu")
            self.assertEqual(result["installed_to"], str(dest))
            self.assertTrue(dest.exists())
            self.assertIn("Pangu Platform Operations", dest.read_text(encoding="utf-8"))

    def test_unknown_skill_is_rejected(self):
        with self.assertRaises(AgentError):
            skills.skill_source("../bad")


if __name__ == "__main__":
    unittest.main()
