import errno
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch


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
        override = self.project / "AGENTS.override.md"
        for content in (b"Existing override.\n", b""):
            with self.subTest(content=content):
                override.write_bytes(content)
                original = self.snapshot()
                result = self.run_installer("install", expected=1)
                self.assertIn("takes precedence", result.stderr)
                self.assertEqual(self.snapshot(), original)

    def test_warns_if_added_block_exceeds_default_instruction_limit(self):
        guide = self.project / GUIDANCE
        block = (INSTALLER.parent / "package/agents-block.md").read_text(encoding="utf-8").encode()
        original = b"# " + b"a" * (32768 - len(block) - 4) + b"\n\n"
        guide.write_bytes(original)
        self.assertEqual(self.run_installer("install").stderr, "")
        self.assertEqual(guide.stat().st_size, 32768)
        self.run_installer("uninstall")

        guide.write_bytes(b"x" + original)
        for _ in range(2):
            result = self.run_installer("install")
            self.assertIn("exceeds Codex's default 32 KiB", result.stderr)
            self.assertIn("project_doc_max_bytes", result.stderr)
            self.assertEqual(guide.read_bytes().count(BEGIN), 1)

        self.run_installer("uninstall")
        self.assertEqual(guide.read_bytes(), b"x" + original)

    def test_rejects_utf16_guidance_before_making_changes(self):
        guide = self.project / GUIDANCE
        for encoding in ("utf-16", "utf-16-le"):
            with self.subTest(encoding=encoding):
                guide.write_bytes("# Existing guidance\r\n".encode(encoding))
                original = self.snapshot()
                result = self.run_installer("install", expected=1)
                self.assertIn("UTF-8", result.stderr)
                self.assertEqual(self.snapshot(), original)

    def test_uninstall_recovers_after_partial_write(self):
        installer = runpy.run_path(str(INSTALLER))
        globals_used_by_installer = installer["change_file"].__globals__
        (self.project / GUIDANCE).write_bytes(b"# Existing guidance\n")
        original = self.snapshot()
        for failed_write, path in enumerate((STATE, SKILL, AGENT, GUIDANCE), start=1):
            with self.subTest(path=path):
                writes = 0

                def open_output(file, *args, **kwargs):
                    nonlocal writes
                    staged = open(file, *args, **kwargs)
                    writes += 1
                    if writes != failed_write:
                        return staged

                    def fail_after_writing(content):
                        staged.write(content[:12])
                        staged.flush()
                        raise OSError(errno.ENOSPC, "simulated write failure")

                    output = MagicMock(wraps=staged)
                    output.__enter__.return_value = output
                    output.__exit__.side_effect = staged.__exit__
                    output.write.side_effect = fail_after_writing
                    return output

                with patch.dict(globals_used_by_installer, open=open_output):
                    with self.assertRaisesRegex(OSError, "simulated write failure"):
                        installer["install"](self.project)
                if path == GUIDANCE:
                    self.assertEqual((self.project / GUIDANCE).read_bytes(), original[GUIDANCE])
                else:
                    self.assertFalse((self.project / path).exists())
                self.run_installer("uninstall")
                self.assertEqual(self.snapshot(), original)

    def test_creation_never_overwrites_an_existing_file(self):
        installer = runpy.run_path(str(INSTALLER))
        path = self.project / STATE
        path.write_bytes(b"someone else's file")
        original = self.snapshot()
        with self.assertRaises(FileExistsError):
            installer["change_file"](path, None, b"My Advisor")
        self.assertEqual(self.snapshot(), original)


if __name__ == "__main__":
    unittest.main()
