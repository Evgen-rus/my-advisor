"""Install or remove My Advisor in an explicitly selected project."""

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import tomllib


SOURCE = Path(__file__).resolve().parent
PACKAGE = SOURCE / "package"
FILES = {
    ".agents/skills/my-advisor/SKILL.md": PACKAGE / "my-advisor/SKILL.md",
    ".codex/agents/my-advisor.toml": PACKAGE / "my-advisor.toml",
}
DIRECTORIES = sorted(
    {path.as_posix() for name in FILES for path in Path(name).parents if path != Path(".")},
    key=lambda name: (name.count("/"), name),
)
STATE = ".my-advisor.json"
GUIDANCE = "AGENTS.md"
BEGIN = b"<!-- BEGIN my-advisor -->"
END = b"<!-- END my-advisor -->"


class Conflict(Exception):
    pass


def checked_path(root, name, *, directory=False):
    destination = root / name
    for path in (*reversed(destination.relative_to(root).parents), Path(name)):
        current = root / path
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        expected = stat.S_ISDIR if current != destination or directory else stat.S_ISREG
        reparse = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        if reparse or not expected(info.st_mode):
            raise Conflict(f"Unexpected file type at {current}. Kept it as is.")
    return destination


def read_file(root, name):
    try:
        return checked_path(root, name).read_bytes()
    except FileNotFoundError:
        return None


def digest(content):
    return None if content is None else hashlib.sha256(content).hexdigest()


def change_file(path, before, after):
    if before is None:
        with path.open("xb") as output:
            output.write(after)
        return
    if after is None:
        if path.read_bytes() != before:
            raise Conflict(f"{path} changed during the operation.")
        path.unlink()
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(after)
            output.close()
            shutil.copymode(path, temporary)
            if path.read_bytes() != before:
                raise Conflict(f"{path} changed during the operation.")
            os.replace(temporary, path)
        finally:
            output.close()
            temporary.unlink(missing_ok=True)


def state_bytes(state):
    return (json.dumps(state, indent=2) + "\n").encode()


def read_state(raw):
    try:
        state = json.loads(raw)
        if state["format"] != 1 or state["package"] != "my-advisor":
            raise ValueError
        files = state["files"]
        directories = state["directories"]
        guidance = state["guidance"]
        if not isinstance(files, dict) or not files.keys() <= FILES.keys():
            raise ValueError
        if not isinstance(directories, list) or not set(directories) <= set(DIRECTORIES):
            raise ValueError
        if guidance is not None:
            if guidance["newline"] not in ("\n", "\r\n") or guidance["padding"] not in (0, 1, 2):
                raise ValueError
            if not isinstance(guidance["block"], str):
                raise ValueError
            if guidance["original"] is not None and not isinstance(guidance["original"], str):
                raise ValueError
        if not all(isinstance(value, str) for value in files.values()):
            raise ValueError
        return state
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise Conflict(f"Unrecognized {STATE}. Kept it as is.") from error


def guidance_without_block(content, record):
    if content is None or digest(content) == record["original"]:
        return content
    if content.count(BEGIN) != 1 or content.count(END) != 1:
        raise Conflict(f"The My Advisor block in {GUIDANCE} changed. Kept it as is.")
    newline = record["newline"].encode()
    start = content.index(BEGIN)
    end = content.index(END) + len(END) + len(newline)
    if (start and content[start - 1:start] != b"\n") or digest(content[start:end]) != record["block"]:
        raise Conflict(f"The My Advisor block in {GUIDANCE} changed. Kept it as is.")
    prefix, suffix = content[:start], content[end:]
    padding = newline * record["padding"]
    if padding and prefix.endswith(padding):
        unpadded = prefix[:-len(padding)]
        if digest(unpadded) == record["original"]:
            if unpadded and suffix and not unpadded.endswith(b"\n") and not suffix.startswith(newline):
                unpadded += newline
            prefix = unpadded
    remainder = prefix + suffix
    if not remainder and record["original"] is None:
        return None
    return remainder


def check_agent_name(root):
    directory = checked_path(root, ".codex/agents", directory=True)
    for path in directory.glob("*.toml"):
        name = path.relative_to(root).as_posix()
        try:
            content = read_file(root, name)
            if content is None:
                continue
            config = tomllib.loads(content.decode("utf-8"))
        except (Conflict, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
        if config.get("name") == "my-advisor":
            raise Conflict(f"Agent name my-advisor is already defined in {name}.")


def install(root):
    raw = read_file(root, STATE)
    if read_file(root, "AGENTS.override.md"):
        raise Conflict(f"AGENTS.override.md takes precedence over {GUIDANCE} in this directory.")
    original = read_file(root, GUIDANCE)
    if raw is not None:
        state = read_state(raw)
        files_match = set(state["files"]) == set(FILES) and all(
            digest(read_file(root, name)) == expected for name, expected in state["files"].items()
        )
        record = state["guidance"]
        if files_match and record and guidance_without_block(original, record) != original:
            print("My Advisor is already installed.")
            return
        raise Conflict("An earlier installation is incomplete or changed. Run uninstall first.")

    for name in FILES:
        if read_file(root, name) is not None:
            raise Conflict(f"{name} already exists.")
    if checked_path(root, ".agents/skills/my-advisor", directory=True).exists():
        raise Conflict("The .agents/skills/my-advisor directory already exists.")
    check_agent_name(root)
    if original and (BEGIN in original or END in original):
        raise Conflict(f"{GUIDANCE} already contains a My Advisor marker.")

    assets = {name: source.read_bytes() for name, source in FILES.items()}
    directories = [
        name for name in DIRECTORIES if not checked_path(root, name, directory=True).exists()
    ]
    body = original or b""
    newline = b"\r\n" if b"\r\n" in body else b"\n"
    padding = 0
    if body and not body.endswith(newline * 2):
        padding = 1 if body.endswith(b"\n") else 2
    block = (PACKAGE / "agents-block.md").read_text(encoding="utf-8").encode().replace(b"\n", newline)
    state = {
        "format": 1,
        "package": "my-advisor",
        "files": {name: digest(content) for name, content in assets.items()},
        "directories": directories,
        "guidance": {
            "original": digest(original),
            "block": digest(block),
            "newline": newline.decode(),
            "padding": padding,
        },
    }
    # Record ownership first so an interrupted install can be removed safely.
    change_file(root / STATE, None, state_bytes(state))
    for name in directories:
        (root / name).mkdir()
    for name, content in assets.items():
        change_file(root / name, None, content)
    change_file(root / GUIDANCE, original, body + newline * padding + block)
    print(f"Installed My Advisor in {root}")


def uninstall(root):
    raw = read_file(root, STATE)
    if raw is None:
        print("Nothing to uninstall.")
        return True
    state = read_state(raw)
    conflicts = []
    for name, expected in state["files"].copy().items():
        try:
            before = read_file(root, name)
            if before is not None:
                if digest(before) != expected:
                    raise Conflict(f"{name} was modified. Kept it as is.")
                change_file(root / name, before, None)
            del state["files"][name]
        except (Conflict, OSError) as error:
            conflicts.append(str(error))
    if state["guidance"] is not None:
        try:
            before = read_file(root, GUIDANCE)
            after = guidance_without_block(before, state["guidance"])
            if after != before:
                change_file(root / GUIDANCE, before, after)
            state["guidance"] = None
        except (Conflict, OSError) as error:
            conflicts.append(str(error))
    for name in reversed(DIRECTORIES):
        if name not in state["directories"]:
            continue
        try:
            checked_path(root, name, directory=True).rmdir()
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                conflicts.append(str(error))
                continue
        except Conflict as error:
            conflicts.append(str(error))
            continue
        if not any(file.startswith(name + "/") for file in state["files"]):
            state["directories"].remove(name)
    change_file(root / STATE, raw, state_bytes(state) if conflicts else None)
    for message in conflicts:
        print(f"Conflict: {message}", file=sys.stderr)
    if not conflicts:
        print(f"Uninstalled My Advisor from {root}")
    return not conflicts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "uninstall"))
    parser.add_argument("project", type=Path, help="existing target project directory")
    args = parser.parse_args()
    try:
        root = args.project.resolve(strict=True)
        if not root.is_dir() or root.is_relative_to(SOURCE):
            raise Conflict("Select an existing project outside the My Advisor source tree.")
        lock = root / ".my-advisor.lock"
        try:
            lock.mkdir()
        except FileExistsError as error:
            raise Conflict(f"{lock} exists. Remove the empty lock only if no installer is running.") from error
        try:
            if args.action == "install":
                install(root)
                return 0
            return 0 if uninstall(root) else 1
        finally:
            lock.rmdir()
    except (Conflict, OSError, RuntimeError) as error:
        print(f"My Advisor: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
