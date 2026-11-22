# My Advisor

This repository contains the source package for a project-local Codex skill. Use this procedure when the user asks to install or remove My Advisor in an existing local project.

## Install

1. Use the open project root when the user says “here.” When working in the My Advisor source repository, use the local target the user named. Clarify the target only if it is ambiguous. If the user provided the My Advisor GitHub link, you can clone the package into a temporary directory and run the installer from there.
2. Run `python "<source>/my_advisor.py" install "<target>"` with both paths quoted. Use `python3` where that is the command for Python 3.11 or newer. Handle the terminal steps yourself. The installer adds the skill, the agent, the `AGENTS.md` block, and its local ownership file to the target. Keep the installation inside the target and preserve its Codex settings and selected model. Report any conflict the installer returns.
3. Check that `.agents/skills/my-advisor/SKILL.md` and `.codex/agents/my-advisor.toml` exist in the target and that its `AGENTS.md` contains one package block. For a requested functional check, use the installed skill to ask Astra one small, synthetic question without file changes. If the current chat started before installation, read the installed skill explicitly or use a fresh Codex session rooted in the target. Use the current ChatGPT sign-in and the native subagent tool. Confirm the separate session and `gpt-6.2-astra` at `high` from available runtime metadata. Report install success and the consultation result separately if live verification is unavailable.

## Uninstall

Run `python "<source>/my_advisor.py" uninstall "<target>"` with the same local target. The installer preserves manually modified files and blocks and reports conflicts. Report the outcome to the user.
