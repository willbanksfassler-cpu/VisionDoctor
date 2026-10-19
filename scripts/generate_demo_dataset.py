"""Generate a deterministic, fully local YOLO Detection demo archive."""

from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

SEED = 20261016
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "demo" / "visiondoctor_demo.zip"


def _png_bytes(pixels: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(pixels.astype(np.uint8), mode="RGB").save(
        buffer,
        format="PNG",
        optimize=False,
        compress_level=6,
    )
    return buffer.getvalue()


def _random_image(rng: np.random.Generator, size: int = 400) -> np.ndarray:
    return rng.integers(0, 256, size=(size, size, 3), dtype=np.uint8)


def _demo_members() -> dict[str, bytes]:
    rng = np.random.default_rng(SEED)
    members: dict[str, bytes] = {
        "dataset/data.yaml": b"name: visiondoctor-demo\nnames: [common, rare, unused]\n",
        "dataset/README.txt": b"Synthetic VisionDoctor demo dataset.\n",
        "packaging-note.md": b"Extra ZIP-root files are intentionally ignored.\n",
    }
    images: dict[str, np.ndarray] = {
        "normal": _random_image(rng),
        "missing": _random_image(rng),
        "empty": _random_image(rng),
        "parse_error": _random_image(rng),
        "invalid_class": _random_image(rng),
        "out_of_range": _random_image(rng),
        "tiny": _random_image(rng),
        "blurry": np.full((400, 400, 3), 128, dtype=np.uint8),
        "dark": np.full((400, 400, 3), 20, dtype=np.uint8),
        "bright": np.full((400, 400, 3), 240, dtype=np.uint8),
        "low_resolution": _random_image(rng, size=160),
    }
    exact = _random_image(rng)
    near = exact.copy()
    near[0, 0, 0] = (int(near[0, 0, 0]) + 1) % 256
    images.update({"exact_a": exact, "exact_b": exact.copy(), "near": near})
    val_stems = {"bright", "low_resolution"}
    test_stems = {"near"}
    for stem, pixels in images.items():
        split = "test" if stem in test_stems else "val" if stem in val_stems else "train"
        members[f"dataset/{split}/images/{stem}.png"] = _png_bytes(pixels)
    members["dataset/train/images/damaged.png"] = b"deterministic damaged image bytes"

    common_rows = "".join("0 0.5 0.5 0.2 0.2\n" for _ in range(12))
    labels = {
        "normal": common_rows,
        "empty": "\n",
        "parse_error": "0 0.5 0.5 0.2\n",
        "invalid_class": "9 0.5 0.5 0.2 0.2\n",
        "out_of_range": "0 1.2 0.5 0.2 0.2\n",
        "tiny": "0 0.5 0.5 0.001 0.001\n",
        "blurry": "0 0.5 0.5 0.2 0.2\n",
        "dark": "0 0.5 0.5 0.2 0.2\n",
        "bright": "0 0.5 0.5 0.2 0.2\n",
        "low_resolution": "0 0.5 0.5 0.2 0.2\n",
        "exact_a": "0 0.5 0.5 0.2 0.2\n",
        "exact_b": "0 0.5 0.5 0.2 0.2\n",
        "near": "1 0.5 0.5 0.2 0.2\n",
        "damaged": "0 0.5 0.5 0.2 0.2\n",
    }
    for stem, content in labels.items():
        split = "test" if stem in test_stems else "val" if stem in val_stems else "train"
        members[f"dataset/{split}/labels/{stem}.txt"] = content.encode("utf-8")
    members["dataset/train/labels/orphan.txt"] = b"0 0.5 0.5 0.2 0.2\n"
    return members


def generate_demo_zip(output_path: str | Path = DEFAULT_OUTPUT) -> Path:
    """Write byte-reproducible synthetic demo data and return its path."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, content in sorted(_demo_members().items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = generate_demo_zip(args.output)
    print(f"Generated deterministic demo ZIP: {output}")


if __name__ == "__main__":
    main()
