"""Security tests for untrusted ZIP extraction."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from vision_doctor.archive import (
    ArchiveLimitError,
    InvalidArchiveError,
    UnsafeArchiveError,
    extract_zip_safely,
)
from vision_doctor.config import UploadLimits


def write_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_valid_zip_extracts_to_random_temporary_directory(tmp_path: Path) -> None:
    archive_path = tmp_path / "dataset.zip"
    write_zip(archive_path, {"data.yaml": b"names: [cat]\n", "labels/a.txt": b""})

    with extract_zip_safely(archive_path, temp_root=tmp_path) as first:
        first_root = first.root
        assert first_root.name.startswith("vision-doctor-")
        assert (first_root / "data.yaml").read_bytes() == b"names: [cat]\n"
    assert not first_root.exists()

    with extract_zip_safely(archive_path, temp_root=tmp_path) as second:
        assert second.root != first_root


def test_non_zip_and_damaged_zip_are_rejected(tmp_path: Path) -> None:
    not_zip = tmp_path / "not-a-zip.zip"
    not_zip.write_bytes(b"not zip content")
    with pytest.raises(InvalidArchiveError, match="not a valid ZIP|damaged"):
        extract_zip_safely(not_zip, temp_root=tmp_path)

    damaged = tmp_path / "damaged.zip"
    write_zip(damaged, {"data.yaml": b"names: [cat]\n"})
    damaged.write_bytes(damaged.read_bytes()[:-12])
    with pytest.raises(InvalidArchiveError, match="not a valid ZIP|damaged"):
        extract_zip_safely(damaged, temp_root=tmp_path)


@pytest.mark.parametrize(
    "member_name",
    ["../escape.txt", "nested/../../escape.txt", "/absolute.txt", "C:/escape.txt"],
)
def test_unsafe_paths_are_rejected(tmp_path: Path, member_name: str) -> None:
    archive_path = tmp_path / "unsafe.zip"
    write_zip(archive_path, {member_name: b"unsafe"})

    with pytest.raises(UnsafeArchiveError):
        extract_zip_safely(archive_path, temp_root=tmp_path)


def test_symbolic_links_are_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(link, "target")

    with pytest.raises(UnsafeArchiveError, match="symbolic link"):
        extract_zip_safely(archive_path, temp_root=tmp_path)


def test_file_count_limit_is_enforced(tmp_path: Path) -> None:
    archive_path = tmp_path / "many.zip"
    write_zip(archive_path, {"one.txt": b"1", "two.txt": b"2"})
    limits = UploadLimits(max_entries=1)

    with pytest.raises(ArchiveLimitError, match="more than 1 files"):
        extract_zip_safely(archive_path, limits=limits, temp_root=tmp_path)


def test_single_file_and_total_size_limits_are_enforced(tmp_path: Path) -> None:
    single_archive = tmp_path / "single-large.zip"
    with zipfile.ZipFile(single_archive, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("large.bin", b"x" * (1024 * 1024 + 1))
    with pytest.raises(ArchiveLimitError, match="single-file limit"):
        extract_zip_safely(
            single_archive,
            limits=UploadLimits(max_single_file_size_mb=1),
            temp_root=tmp_path,
        )

    total_archive = tmp_path / "total-large.zip"
    with zipfile.ZipFile(total_archive, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("one.bin", b"x" * 600_000)
        archive.writestr("two.bin", b"y" * 600_000)
    with pytest.raises(ArchiveLimitError, match="total extraction limit"):
        extract_zip_safely(
            total_archive,
            limits=UploadLimits(max_extracted_size_mb=1),
            temp_root=tmp_path,
        )


def test_suspicious_compression_ratio_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "ratio.zip"
    write_zip(archive_path, {"repetitive.txt": b"a" * 100_000})
    limits = UploadLimits(max_compression_ratio=2.0)

    with pytest.raises(ArchiveLimitError, match="compression ratio"):
        extract_zip_safely(archive_path, limits=limits, temp_root=tmp_path)
