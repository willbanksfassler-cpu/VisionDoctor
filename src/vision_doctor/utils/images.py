"""Safe, reusable image decoding and measurement helpers."""

from __future__ import annotations

import io
import math
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError


@dataclass(frozen=True)
class ImageMeasurements:
    """Measured image facts used by quality checks."""

    width: int
    height: int
    grayscale_mean: float
    laplacian_variance: float


def decode_image(path: str | Path) -> np.ndarray | None:
    """Decode an image to RGB while isolating file and codec failures."""

    image_path = Path(path)
    try:
        with Image.open(image_path) as source:
            return np.asarray(source.convert("RGB"), dtype=np.uint8)
    except (OSError, UnidentifiedImageError, ValueError):
        return None


def _grayscale(image: np.ndarray) -> np.ndarray:
    return np.tensordot(
        image.astype(np.float64),
        np.array([0.299, 0.587, 0.114]),
        axes=([2], [0]),
    )


def measure_image(image: np.ndarray) -> ImageMeasurements:
    """Return deterministic dimensions, brightness, and sharpness facts."""

    grayscale = _grayscale(image)
    height, width = grayscale.shape
    padded = np.pad(grayscale, 1, mode="edge")
    laplacian = (
        padded[:-2, 1:-1]
        + padded[2:, 1:-1]
        + padded[1:-1, :-2]
        + padded[1:-1, 2:]
        - 4.0 * grayscale
    )
    return ImageMeasurements(
        width=int(width),
        height=int(height),
        grayscale_mean=float(np.mean(grayscale)),
        laplacian_variance=float(np.var(laplacian)),
    )


def perceptual_hash(image: np.ndarray, *, hash_size: int = 8) -> int:
    """Compute a compact DCT perceptual hash as an integer bit field."""

    grayscale = _grayscale(image)
    sample_size = hash_size * 4
    resized = np.asarray(
        Image.fromarray(grayscale.astype(np.uint8), mode="L").resize(
            (sample_size, sample_size),
            Image.Resampling.LANCZOS,
        ),
        dtype=np.float64,
    )
    positions = np.arange(sample_size, dtype=np.float64)
    frequencies = positions[:, None]
    transform = np.cos(
        math.pi * (2.0 * positions[None, :] + 1.0) * frequencies
        / (2.0 * sample_size)
    )
    transform[0, :] *= math.sqrt(1.0 / sample_size)
    transform[1:, :] *= math.sqrt(2.0 / sample_size)
    low_frequencies = (transform @ resized @ transform.T)[:hash_size, :hash_size]
    comparison_values = low_frequencies.flatten()[1:]
    median = float(np.median(comparison_values))
    bits = low_frequencies.flatten() > median
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def hamming_distance(first: int, second: int) -> int:
    """Return the number of different bits between two hashes."""

    return (first ^ second).bit_count()


def _safe_archive_member(relative_path: str) -> PurePosixPath | None:
    normalized = relative_path.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if (
        not normalized
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        return None
    return candidate


def render_archive_preview(
    archive_path: str | Path,
    relative_path: str,
    *,
    bboxes: Iterable[tuple[float, float, float, float]] = (),
    max_dimension: int = 900,
    max_file_size_bytes: int = 50 * 1024 * 1024,
) -> bytes | None:
    """Return a bounded PNG preview from a ZIP, optionally drawing YOLO boxes.

    Dataset-relative paths may sit below one wrapper directory in the ZIP. An
    ambiguous suffix match is rejected instead of guessing which file to show.
    """

    requested = _safe_archive_member(relative_path)
    if requested is None or max_dimension <= 0 or max_file_size_bytes <= 0:
        return None
    try:
        with zipfile.ZipFile(Path(archive_path), "r") as archive:
            files = [item for item in archive.infolist() if not item.is_dir()]
            exact = [
                item
                for item in files
                if item.filename.replace("\\", "/") == requested.as_posix()
            ]
            suffix = f"/{requested.as_posix()}"
            matches = exact or [
                item
                for item in files
                if item.filename.replace("\\", "/").endswith(suffix)
            ]
            if len(matches) != 1 or matches[0].file_size > max_file_size_bytes:
                return None
            payload = archive.read(matches[0])
        if len(payload) > max_file_size_bytes:
            return None
        with Image.open(io.BytesIO(payload)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            original_width, original_height = image.size
            overlay = ImageDraw.Draw(image)
            line_width = max(2, round(min(original_width, original_height) / 180))
            for x_center, y_center, width, height in bboxes:
                left = (x_center - width / 2) * original_width
                top = (y_center - height / 2) * original_height
                right = (x_center + width / 2) * original_width
                bottom = (y_center + height / 2) * original_height
                overlay.rectangle(
                    (left, top, right, bottom),
                    outline=(229, 57, 53),
                    width=line_width,
                )
            image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except (
        OSError,
        ValueError,
        RuntimeError,
        zipfile.BadZipFile,
        KeyError,
        Image.DecompressionBombError,
        UnidentifiedImageError,
    ):
        return None
