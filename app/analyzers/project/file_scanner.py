"""Bounded, non-executing scanners for local directories and ZIP uploads."""

from dataclasses import dataclass, field
import io
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile
import zlib


MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 20_000_000
MAX_ARCHIVE_BYTES = 25_000_000
MAX_FILES = 2_000
IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", ".venv", "venv",
    "env", "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build",
    "coverage", ".next", ".nuxt", "target",
}


class InvalidProjectArchive(ValueError):
    """The uploaded archive is malformed or contains unsafe paths."""


class ProjectTooLarge(ValueError):
    """The upload exceeds configured analysis limits."""


@dataclass
class ScannedProject:
    """Text files that passed size, binary, and secret-file filters."""

    files: dict[str, str] = field(default_factory=dict)
    skipped_binary_files: int = 0
    skipped_large_files: int = 0
    total_files_seen: int = 0
    file_types: dict[str, int] = field(default_factory=dict)


def _record_file(scanned: ScannedProject, path: str) -> None:
    scanned.total_files_seen += 1
    extension = Path(path).suffix.lower() or "[no extension]"
    scanned.file_types[extension] = scanned.file_types.get(extension, 0) + 1


def _is_sensitive_name(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.startswith(".env")
        or lowered in {"id_rsa", "id_ed25519", "credentials", "secrets.json"}
        or "private_key" in lowered
    )


def _decode_text(data: bytes) -> str | None:
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _store(scanned: ScannedProject, path: str, data: bytes) -> None:
    if len(data) > MAX_FILE_BYTES:
        scanned.skipped_large_files += 1
        return
    text = _decode_text(data)
    if text is None:
        scanned.skipped_binary_files += 1
        return
    scanned.files[path] = text


def scan_directory(root: str | Path) -> ScannedProject:
    """Read bounded UTF-8 files under a local directory without following symlinks."""
    root_path = Path(root).expanduser()
    if not root_path.is_dir() or root_path.is_symlink():
        raise ValueError("Project path must be an existing directory.")

    scanned = ScannedProject()
    total_bytes = 0
    for current, directories, filenames in os.walk(root_path, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name for name in directories
            if name.lower() not in IGNORED_DIRS
            and not (current_path / name).is_symlink()
        ]
        for filename in filenames:
            path = current_path / filename
            if path.is_symlink() or _is_sensitive_name(filename):
                continue
            relative_path = path.relative_to(root_path).as_posix()
            _record_file(scanned, relative_path)
            if scanned.total_files_seen > MAX_FILES:
                raise ProjectTooLarge(f"Project contains more than {MAX_FILES} files.")
            try:
                size = path.stat().st_size
                if size > MAX_FILE_BYTES:
                    scanned.skipped_large_files += 1
                    continue
                if total_bytes + size > MAX_TOTAL_BYTES:
                    raise ProjectTooLarge("Project text files exceed the total analysis size limit.")
                with path.open("rb") as source:
                    data = source.read(MAX_FILE_BYTES + 1)
            except OSError:
                continue
            if len(data) > MAX_FILE_BYTES:
                scanned.skipped_large_files += 1
                continue
            total_bytes += len(data)
            text = _decode_text(data)
            if text is None:
                scanned.skipped_binary_files += 1
                continue
            scanned.files[relative_path] = text
    return scanned


def _safe_zip_path(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or any(part in {"..", ""} for part in path.parts)
        or (path.parts and ":" in path.parts[0])
    ):
        raise InvalidProjectArchive("ZIP contains an unsafe file path.")
    return path


def scan_zip_bytes(archive_bytes: bytes) -> ScannedProject:
    """Read a ZIP in memory while rejecting traversal and limiting decompression."""
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ProjectTooLarge(f"ZIP upload exceeds {MAX_ARCHIVE_BYTES} bytes.")
    scanned = ScannedProject()
    total_uncompressed = 0
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES:
                raise ProjectTooLarge(f"ZIP contains more than {MAX_FILES} entries.")
            for info in entries:
                path = _safe_zip_path(info.filename)
                if info.is_dir():
                    continue
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise InvalidProjectArchive("ZIP contains a symbolic link.")
                if any(part.lower() in IGNORED_DIRS for part in path.parts[:-1]):
                    continue
                if _is_sensitive_name(path.name):
                    continue
                _record_file(scanned, path.as_posix())
                if info.file_size > MAX_FILE_BYTES:
                    scanned.skipped_large_files += 1
                    continue
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_TOTAL_BYTES:
                    raise ProjectTooLarge("ZIP contents exceed the total analysis size limit.")
                with archive.open(info) as source:
                    data = source.read(MAX_FILE_BYTES + 1)
                if len(data) > MAX_FILE_BYTES:
                    scanned.skipped_large_files += 1
                    continue
                _store(scanned, path.as_posix(), data)
    except (InvalidProjectArchive, ProjectTooLarge):
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError, EOFError, zlib.error, NotImplementedError) as exc:
        raise InvalidProjectArchive("The uploaded file is not a readable ZIP archive.") from exc
    return scanned
