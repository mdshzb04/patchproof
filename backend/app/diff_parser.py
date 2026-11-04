"""Unified diff parser. Line numbers follow the new file."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class DiffParseError(ValueError):
    pass


@dataclass
class DiffFile:
    path: str
    old_path: str | None = None
    is_new: bool = False
    is_deleted: bool = False
    added_lines: set[int] = field(default_factory=set)
    deleted_lines: set[int] = field(default_factory=set)
    new_lines: list[str] = field(default_factory=list)
    line_text: dict[int, str] = field(default_factory=dict)
    saw_hunk: bool = False
    gaps: bool = False
    new_content: str = ""


def normalize_path(path: str) -> str:
    path = path.strip().strip('"')
    if "\t" in path:
        path = path.split("\t", 1)[0].strip()
    if path == "/dev/null":
        return path
    for prefix in ("b/", "a/"):
        if path.startswith(prefix):
            path = path[len(prefix) :]
            break
    path = path.replace("\\", "/")
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts) or path.startswith("/"):
        raise DiffParseError(f"Refusing unsafe path: {path}")
    return "/".join(parts)


def parse_unified_diff(text: str) -> list[DiffFile]:
    if text is None or not str(text).strip():
        raise DiffParseError("Empty diff.")
    if "\x00" in text:
        raise DiffParseError("Diff contains NUL bytes.")

    current: DiffFile | None = None
    files: list[DiffFile] = []
    in_hunk = False
    new_n = 0
    old_n = 0

    def start(path: str) -> DiffFile:
        nonlocal current, in_hunk
        current = DiffFile(path=normalize_path(path) if path != "/dev/null" else path)
        files.append(current)
        in_hunk = False
        return current

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            parts = raw.split()
            if len(parts) < 4:
                raise DiffParseError("Unreadable diff --git header.")
            start(parts[-1])
            in_hunk = False
            continue

        if raw.startswith(("index ", "new file", "deleted file", "similarity ", "rename ", "old mode", "new mode", "Binary file", "GIT binary")):
            continue

        if raw.startswith("--- "):
            oldp = raw[4:].split("\t", 1)[0].strip()
            if current is None or current.saw_hunk:
                start(oldp if oldp != "/dev/null" else "unknown")
            assert current is not None
            current.old_path = oldp if oldp == "/dev/null" else normalize_path(oldp)
            current.is_new = oldp == "/dev/null"
            in_hunk = False
            continue

        if raw.startswith("+++ "):
            newp = raw[4:].split("\t", 1)[0].strip()
            if current is None:
                start(newp)
            assert current is not None
            if newp == "/dev/null":
                current.is_deleted = True
            else:
                current.path = normalize_path(newp)
            continue

        match = HUNK_RE.match(raw)
        if match:
            if current is None:
                raise DiffParseError("Hunk appears before a file header.")
            old_n = int(match.group(1))
            new_n = int(match.group(3))
            expected = len(current.new_lines) + 1
            if new_n != expected:
                current.gaps = True
            current.saw_hunk = True
            in_hunk = True
            continue

        if not in_hunk or current is None:
            continue

        if raw.startswith("\\"):
            continue
        if raw.startswith("+"):
            current.new_lines.append(raw[1:])
            current.line_text[new_n] = raw[1:]
            current.added_lines.add(new_n)
            new_n += 1
            continue
        if raw.startswith("-"):
            current.deleted_lines.add(old_n)
            old_n += 1
            continue
        if raw.startswith(" "):
            current.new_lines.append(raw[1:])
            current.line_text[new_n] = raw[1:]
            old_n += 1
            new_n += 1
            continue
        if raw == "":
            current.new_lines.append("")
            current.line_text[new_n] = ""
            old_n += 1
            new_n += 1
            continue
        in_hunk = False

    parsed = [f for f in files if f.saw_hunk and f.path and f.path != "/dev/null"]
    if not parsed:
        raise DiffParseError(
            "No unified diff hunks found. Upload a Git diff, a .patch, or a Python file."
        )
    for item in parsed:
        item.new_content = "\n".join(item.new_lines) + ("\n" if item.new_lines else "")
        if item.is_deleted:
            item.added_lines.clear()
    return parsed
