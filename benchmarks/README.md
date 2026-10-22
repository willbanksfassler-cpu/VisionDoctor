# VisionDoctor controlled-corruption benchmark

This benchmark measures the existing deterministic pipeline against synthetic,
explicitly injected ground truth. It does **not** change production detection
rules and must not be described as validation on real business data.

## Profiles

| Profile | Images | Intended use |
|---|---:|---|
| `quick` | 40 | Focused tests and CI-friendly local checks |
| `standard` | 160 | More representative local timing and memory measurement |
| `scale` | 800 | Opt-in scaling experiment; never run by ordinary pytest |

All profiles use a fixed seed by default, create a clean YOLO Detection dataset,
copy it, and then inject controlled corruptions into the copy. No network access
or external dataset is used.

## Covered ground truth

The truth file records the following product Issue codes with their relative
path and, where applicable, annotation line:

- `LABEL_MISSING`, `LABEL_EMPTY`, `LABEL_PARSE_ERROR`, `CLASS_ID_INVALID`
- `BBOX_NON_POSITIVE`, `BBOX_OUT_OF_RANGE`, `BBOX_CROSSES_BORDER`, `BBOX_TINY`
- `IMAGE_UNREADABLE`, `IMAGE_BLURRY`, `IMAGE_DARK`, `IMAGE_BRIGHT`
- `IMAGE_LOW_RESOLUTION`

Exact and near duplicates are matched separately using the complete sorted set
of group image IDs. Class imbalance is a benchmark-only derived signal checked
against the injected class counts, rare class IDs, zero-instance class IDs, and
minimum imbalance index. `DUPLICATE_EXACT`, `DUPLICATE_NEAR`, and
`CLASS_IMBALANCE` are evaluation signal names, not product `Issue.code` values.

## Matching and metrics

Product Issues match only when `issue code + normalized relative_path +
annotation_line` match. Duplicate groups match only when kind and full group
membership match. The benchmark reports TP, FP, FN, precision, recall, and F1
per code, plus micro and macro averages. It also records why each unmatched
finding failed to match; comparing counts alone is intentionally insufficient.

Zero denominators produce `0.0`, never an exception. Runtime uses wall-clock
`perf_counter`. Peak memory uses `tracemalloc`, which excludes some memory
allocated by native libraries such as NumPy, Pillow, and OpenCV.

## Run locally

From the repository root:

```powershell
python scripts/run_corruption_benchmark.py --profile quick
python scripts/run_corruption_benchmark.py --profile standard
```

The scale entry point is explicit and can take substantially longer because the
current pHash implementation is pairwise:

```powershell
python scripts/run_corruption_benchmark.py --profile scale
```

Generated clean/corrupted ZIPs, ground truth, JSON results, and Markdown results
are written under `benchmarks/generated/<profile>/`. That directory is ignored
by Git. JSON is the machine-readable artifact; Markdown is the stable human
summary.

## Interpretation limits

- These are controlled synthetic images and annotations, not real factory,
  retail, medical, or autonomous-driving data.
- High scores show that the current injected cases were recovered. They do not
  prove generalization to unseen corruption modes or domains.
- One injection can expose a correlated heuristic response. Unexpected findings
  are retained as false positives instead of being deleted to improve metrics.
- Results do not measure model training quality, mAP improvement, or the
  correctness of any future automatic repair.
