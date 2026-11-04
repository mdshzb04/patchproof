"""Upload validation. Never executes uploaded code."""

from __future__ import annotations

import io
import zipfile

from app.diff_parser import DiffParseError

MAX_BYTES = 1_000_000
MAX_ZIP_FILES = 40
MAX_UNCOMPRESSED = 2_000_000


class UploadError(ValueError):
    pass


def decode_text(data: bytes, label: str) -> str:
    if len(data) > MAX_BYTES:
        raise UploadError(f"{label} is larger than 1 MB.")
    if b"\x00" in data:
        raise UploadError(f"{label} looks like a binary file.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadError(f"{label} is not valid UTF-8.") from exc


def safe_zip_paths(data: bytes) -> list[tuple[str, str]]:
    if len(data) > MAX_BYTES:
        raise UploadError("ZIP is larger than 1 MB.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UploadError("ZIP archive is malformed.") from exc
    files: list[tuple[str, str]] = []
    total = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/")
        parts = [part for part in name.split("/") if part not in ("", ".")]
        if name.startswith("/") or any(part == ".." for part in parts):
            raise UploadError(f"ZIP path is not allowed: {info.filename}")
        rel = "/".join(parts)
        if not rel.endswith(".py"):
            continue
        if info.file_size > MAX_BYTES:
            raise UploadError(f"{rel} is larger than 1 MB.")
        total += info.file_size
        if total > MAX_UNCOMPRESSED:
            raise UploadError("ZIP expands past 2 MB.")
        if len(files) >= MAX_ZIP_FILES:
            raise UploadError("ZIP contains more than 40 Python files.")
        files.append((rel, decode_text(archive.read(info), rel)))
    if not files:
        raise UploadError("ZIP has no Python files.")
    return files


def classify(filename: str, data: bytes) -> tuple[str, str | list[tuple[str, str]]]:
    name = (filename or "upload.txt").rsplit("/", 1)[-1].lower()
    if name.endswith(".zip"):
        return "zip", safe_zip_paths(data)
    text = decode_text(data, filename or "upload")
    if name.endswith((".diff", ".patch")):
        return "diff", text
    if name.endswith(".py"):
        rel = (filename or "upload.py").replace("\\", "/")
        parts = [part for part in rel.split("/") if part not in ("", ".")]
        if any(part == ".." for part in parts):
            raise UploadError("File path is not allowed.")
        return "py", [("/".join(parts), text)]
    if text.lstrip().startswith("diff ") or "\n@@ " in text or text.startswith("@@ "):
        return "diff", text
    raise UploadError("Upload a .diff, .patch, .py, or .zip of Python files.")


def reject_oversized_text(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise DiffParseError("Diff is larger than 1 MB.")
