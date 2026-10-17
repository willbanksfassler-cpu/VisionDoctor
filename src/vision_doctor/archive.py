"""Defensive ZIP validation and extraction for untrusted uploads."""

from __future__ import annotations

import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import TracebackType

from vision_doctor.config import UploadLimits

_MEBIBYTE = 1024 * 1024
_COPY_CHUNK_SIZE = 1024 * 1024


class ArchiveError(ValueError):
    """Base class for user-readable archive failures."""


class InvalidArchiveError(ArchiveError):
    """Raised when the input is absent, not ZIP content, or damaged."""


class UnsafeArchiveError(ArchiveError):
    """Raised when an entry could escape or create a non-regular file."""


class ArchiveLimitError(ArchiveError):
    """Raised when configured resource or compression limits are exceeded."""


@dataclass
class ExtractedArchive:
    """A temporary extraction directory with explicit cleanup semantics."""

    root: Path
    _temporary_directory: tempfile.TemporaryDirectory[str]

    def cleanup(self) -> None:
        """Remove every extracted file and the random temporary directory."""

        self._temporary_directory.cleanup()

    def __enter__(self) -> ExtractedArchive:  # noqa: PYI034 - Python 3.10 support
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.cleanup()


def _size_limit_in_bytes(mebibytes: int) -> int:
    return mebibytes * _MEBIBYTE


def _safe_member_path(info: zipfile.ZipInfo) -> PurePosixPath:
    raw_name = info.filename
    normalized_name = raw_name.replace("\\", "/")
    posix_path = PurePosixPath(normalized_name)
    windows_path = PureWindowsPath(raw_name)

    if not raw_name or "\x00" in raw_name:
        raise UnsafeArchiveError("ZIP contains an empty or invalid entry name.")
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise UnsafeArchiveError(f"ZIP entry uses an absolute path: {raw_name!r}.")
    if any(part == ".." for part in posix_path.parts):
        raise UnsafeArchiveError(f"ZIP entry attempts path traversal: {raw_name!r}.")
    if any(part in {"", "."} for part in posix_path.parts):
        raise UnsafeArchiveError(f"ZIP entry has an ambiguous path: {raw_name!r}.")
    return posix_path


def _validate_file_type(info: zipfile.ZipInfo) -> None:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    if file_type == stat.S_IFLNK:
        raise UnsafeArchiveError(f"ZIP entry is a symbolic link: {info.filename!r}.")
    allowed_types = {0, stat.S_IFREG, stat.S_IFDIR}
    if info.create_system == 3 and file_type not in allowed_types:
        raise UnsafeArchiveError(
            f"ZIP entry is not a regular file or directory: {info.filename!r}."
        )


def _validate_members(
    members: list[zipfile.ZipInfo], limits: UploadLimits
) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    validated: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    seen_destinations: set[str] = set()
    file_count = 0
    total_uncompressed = 0
    max_single_file = _size_limit_in_bytes(limits.max_single_file_size_mb)
    max_total = _size_limit_in_bytes(limits.max_extracted_size_mb)

    for info in members:
        member_path = _safe_member_path(info)
        _validate_file_type(info)
        destination_key = member_path.as_posix().rstrip("/").casefold()
        if destination_key in seen_destinations:
            raise UnsafeArchiveError(
                f"ZIP contains duplicate destination paths: {info.filename!r}."
            )
        seen_destinations.add(destination_key)

        if info.flag_bits & 0x1:
            raise UnsafeArchiveError(
                f"Encrypted ZIP entries are not supported: {info.filename!r}."
            )
        if not info.is_dir():
            file_count += 1
            if file_count > limits.max_entries:
                raise ArchiveLimitError(
                    f"ZIP contains more than {limits.max_entries} files."
                )
            if info.file_size > max_single_file:
                raise ArchiveLimitError(
                    f"ZIP entry exceeds the {limits.max_single_file_size_mb} MiB "
                    f"single-file limit: {info.filename!r}."
                )
            total_uncompressed += info.file_size
            if total_uncompressed > max_total:
                raise ArchiveLimitError(
                    f"ZIP exceeds the {limits.max_extracted_size_mb} MiB "
                    "total extraction limit."
                )
            if info.file_size > 0:
                if info.compress_size == 0:
                    raise ArchiveLimitError(
                        f"ZIP entry has a suspicious compression ratio: {info.filename!r}."
                    )
                ratio = info.file_size / info.compress_size
                if ratio > limits.max_compression_ratio:
                    raise ArchiveLimitError(
                        f"ZIP entry compression ratio {ratio:.1f}:1 exceeds the "
                        f"configured {limits.max_compression_ratio:.1f}:1 limit: "
                        f"{info.filename!r}."
                    )
        validated.append((info, member_path))
    return validated


def _extract_members(
    archive: zipfile.ZipFile,
    members: list[tuple[zipfile.ZipInfo, PurePosixPath]],
    destination_root: Path,
    limits: UploadLimits,
) -> None:
    resolved_root = destination_root.resolve()
    max_single_file = _size_limit_in_bytes(limits.max_single_file_size_mb)
    max_total = _size_limit_in_bytes(limits.max_extracted_size_mb)
    actual_total = 0

    for info, member_path in members:
        destination = destination_root.joinpath(*member_path.parts)
        resolved_destination = destination.resolve()
        try:
            resolved_destination.relative_to(resolved_root)
        except ValueError as error:
            raise UnsafeArchiveError(
                f"ZIP entry escapes the extraction directory: {info.filename!r}."
            ) from error

        if info.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        written_for_file = 0
        try:
            with archive.open(info, "r") as source, destination.open("xb") as target:
                while chunk := source.read(_COPY_CHUNK_SIZE):
                    written_for_file += len(chunk)
                    actual_total += len(chunk)
                    if written_for_file > max_single_file:
                        raise ArchiveLimitError(
                            f"ZIP entry expanded beyond its allowed size: {info.filename!r}."
                        )
                    if actual_total > max_total:
                        raise ArchiveLimitError(
                            "ZIP expanded beyond the configured total size limit."
                        )
                    target.write(chunk)
        except (RuntimeError, NotImplementedError, zipfile.BadZipFile) as error:
            raise InvalidArchiveError(
                f"ZIP entry could not be read safely: {info.filename!r}."
            ) from error


def extract_zip_safely(
    archive_path: str | Path,
    *,
    limits: UploadLimits | None = None,
    temp_root: str | Path | None = None,
) -> ExtractedArchive:
    """Validate and extract ZIP content into a random temporary directory.

    The caller owns the returned context manager and must either use ``with`` or
    call :meth:`ExtractedArchive.cleanup` when parsing is complete.
    """

    source_path = Path(archive_path)
    active_limits = limits or UploadLimits()
    if not source_path.is_file():
        raise InvalidArchiveError("Uploaded archive does not exist or is not a file.")
    if source_path.stat().st_size > _size_limit_in_bytes(
        active_limits.max_archive_size_mb
    ):
        raise ArchiveLimitError(
            f"ZIP upload exceeds the {active_limits.max_archive_size_mb} MiB limit."
        )
    if not zipfile.is_zipfile(source_path):
        raise InvalidArchiveError("Uploaded file is not a valid ZIP or is damaged.")

    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    try:
        with zipfile.ZipFile(source_path, "r") as archive:
            validated_members = _validate_members(archive.infolist(), active_limits)
            temporary_directory = tempfile.TemporaryDirectory(
                prefix="vision-doctor-",
                dir=Path(temp_root) if temp_root is not None else None,
            )
            destination_root = Path(temporary_directory.name)
            _extract_members(
                archive,
                validated_members,
                destination_root,
                active_limits,
            )
    except ArchiveError:
        if temporary_directory is not None:
            temporary_directory.cleanup()
        raise
    except zipfile.BadZipFile as error:
        if temporary_directory is not None:
            temporary_directory.cleanup()
        raise InvalidArchiveError("ZIP is damaged or could not be read safely.") from error
    except (OSError, EOFError) as error:
        if temporary_directory is not None:
            temporary_directory.cleanup()
        raise InvalidArchiveError("ZIP is damaged or could not be read safely.") from error

    if temporary_directory is None:
        raise InvalidArchiveError("ZIP could not be extracted.")
    return ExtractedArchive(Path(temporary_directory.name), temporary_directory)
