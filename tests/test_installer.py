from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


INSTALLER = Path(__file__).resolve().parents[1] / "my_advisor.py"
SKILL = Path(".agents/skills/my-advisor/SKILL.md")
AGENT = Path(".codex/agents/my-advisor.toml")
STATE = Path(".my-advisor.json")
GUIDANCE = Path("AGENTS.md")
BEGIN = b"<!-- BEGIN my-advisor -->"


class InstallerTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix="My Advisor test ")
        self.addCleanup(workspace.cleanup)
        self.project = Path(workspace.name)

    def run_installer(self, action, expected=0):
        result = subprocess.run(
            [sys.executable, str(INSTALLER), action, str(self.project)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def snapshot(self):
        return {
            path.relative_to(self.project): path.read_bytes() if path.is_file() else None
            for path in self.project.rglob("*")
        }

    def test_round_trip_with_existing_guidance_and_files(self):
        (self.project / GUIDANCE).write_bytes(b"\xef\xbb\xbf# Existing\r\n\r\nKeep this instruction.")
        (self.project / ".codex").mkdir()
        (self.project / ".codex/config.toml").write_bytes(b'model = "gpt-6.1-terra"\r\n')
        (self.project / "keep.txt").write_bytes(b"existing data")
        original = self.snapshot()

        self.run_installer("install")
        installed = self.snapshot()
        self.assertEqual(installed[GUIDANCE].count(BEGIN), 1)
        self.assertIn(SKILL, installed)
        self.assertIn(AGENT, installed)
        self.assertIn(STATE, installed)
        self.assertEqual(installed[Path(".codex/config.toml")], original[Path(".codex/config.toml")])
        self.assertIn("already installed", self.run_installer("install").stdout)
        self.assertEqual(self.snapshot(), installed)

        self.run_installer("uninstall")
        self.assertEqual(self.snapshot(), original)
        self.assertIn("Nothing to uninstall", self.run_installer("uninstall").stdout)

    def test_does_not_overwrite_conflicting_skill_and_agent(self):
        for name in (SKILL, AGENT, AGENT.with_name("someone-elses-role.toml")):
            with self.subTest(name=name):
                path = self.project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'name = "my-advisor"\n')
                original = self.snapshot()
                self.run_installer("install", expected=1)
                self.assertEqual(self.snapshot(), original)
                path.unlink()
                if name == SKILL:
                    path.parent.rmdir()

    def test_preserves_edited_files_and_block_on_uninstall(self):
        self.run_installer("install")
        skill = self.project / SKILL
        guidance = self.project / GUIDANCE
        edited_skill = skill.read_bytes() + b"\nMy own rule\n"
        edited_block = guidance.read_bytes().replace(b"Use the project skill", b"Always use the project skill")
        skill.write_bytes(edited_skill)
        guidance.write_bytes(edited_block)

        failure = self.run_installer("uninstall", expected=1)
        self.assertIn("SKILL.md was modified", failure.stderr)
        self.assertIn("block in AGENTS.md changed", failure.stderr)
        self.assertEqual(skill.read_bytes(), edited_skill)
        self.assertEqual(guidance.read_bytes(), edited_block)
        self.assertFalse((self.project / AGENT).exists())

        agent = self.project / AGENT
        agent.parent.mkdir(parents=True)
        agent.write_bytes((INSTALLER.parent / "package/my-advisor.toml").read_bytes())
        self.run_installer("uninstall", expected=1)
        self.assertTrue(agent.is_file())

    def test_preserves_new_instructions_and_removes_generated_block(self):
        self.run_installer("install")
        guidance = self.project / GUIDANCE
        user_text = b"## New instructions\n\nKeep my work.\n"
        guidance.write_bytes(guidance.read_bytes() + user_text)
        self.run_installer("uninstall")
        self.assertEqual(self.snapshot(), {GUIDANCE: user_text})

    def test_removes_entire_install_from_empty_project(self):
        self.run_installer("install")
        self.run_installer("uninstall")
        self.assertEqual(self.snapshot(), {})

    def test_appended_instructions_stay_on_their_own_line(self):
        guidance = self.project / GUIDANCE
        guidance.write_bytes(b"Existing instructions")
        self.run_installer("install")
        guidance.write_bytes(guidance.read_bytes() + b"New instructions\n")
        self.run_installer("uninstall")
        self.assertEqual(guidance.read_bytes(), b"Existing instructions\nNew instructions\n")

    def test_preserves_original_trailing_blank_line(self):
        guidance = self.project / GUIDANCE
        original = b"Keep this instruction.\n\n"
        guidance.write_bytes(original)
        self.run_installer("install")
        self.run_installer("uninstall")
        self.assertEqual(guidance.read_bytes(), original)

    def test_existing_instruction_override_is_a_conflict(self):
        (self.project / "AGENTS.override.md").write_bytes(b"Existing override.\n")
        original = self.snapshot()
        self.run_installer("install", expected=1)
        self.assertEqual(self.snapshot(), original)


if __name__ == "__main__":
    unittest.main()
