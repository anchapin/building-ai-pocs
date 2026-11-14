# media-qa-gate — a universal pixel floor for gameplay/store screenshots

**Status:** slice 1 of POC #51 (issue #57), Phase 0, one surface
(armored-archer store assets). Report-only: nothing here blocks a merge, a
build, or a store upload. Phase 1 is not authorised and nothing in this
folder is wired into CI.

This is a *floor*, not a judge: five cheap, deterministic, per-image checks
that catch the failure modes a screenshot pipeline produces when the
renderer did not actually draw the scene. It is deliberately **not** a
vision model and there is no LLM anywhere in the pass/fail path.

## What it checks

| check | error condition | warn condition |
| --- | --- | --- |
| `blank` | luma std-dev < 3.0 (no structure at all) | luma std-dev < 5.0, or one exact colour covers >= 99.5 % of pixels |
| `dimensions` | shortest side < 320 px, longest side > 3840 px, or aspect outside [0.2, 5.0] | differs from the store spec declared in the corpus manifest |
| `exposure` | crushed (>= 90 % of pixels at luma <= 3, or mean <= 8) or blown out (>= 90 % at luma >= 252, or mean >= 247) | dark/bright fraction >= 50 %, or mean <= 20 / >= 235 |
| `sharpness` | variance of the 3x3 Laplacian < 20 (no usable edges) | < 35 |
| `duplicate` | pixel-identical to another artifact **in the same submission group** (same platform/device folder) | pixel-identical to an artifact in another group (expected for the shared android/ios icon) |

Findings are emitted one per line:

```
error|warn <check> <measurement>; <fix hint>
```

The CLI exits **1** when at least one `error` finding exists, otherwise 0.

## Commands

```sh
# clean run over the real corpus (auto-loads corpus/manifest.json)
python3 media-qa-gate/mediaqa.py media-qa-gate/corpus/

# seeded-defect run
python3 media-qa-gate/mediaqa.py media-qa-gate/seeded/

# tests
python3 -m pytest media-qa-gate/ -q

# rebuild the corpus from armored-archer (read-only source)
python3 media-qa-gate/build_corpus.py

# re-seed the defect copies from the corpus
python3 media-qa-gate/seed_defects.py

# head-to-head against armored-archer's RMSE suite
python3 media-qa-gate/head_to_head.py
```

Useful flags: `--json` (machine-readable output), `--measurements` (per
check measurement dump), `--manifest PATH` (explicit manifest),
`--root PATH` (root for manifest keys and submission grouping).

## Layout

```
media-qa-gate/
  mediaqa.py         the checker (five checks, CLI, table + findings output)
  build_corpus.py    copies real armored-archer assets into corpus/ (read-only source)
  seed_defects.py    derives the seeded defect copies from corpus images
  head_to_head.py    head-to-head vs armored-archer's RMSE screenshot suite
  corpus/            43 REAL store artifacts + manifest.json (source path per artifact)
  seeded/            6 derived defect copies + seeds.json (kind, source, expected check)
  tests/             20 pytest tests
  REPORT.md          the measured report for this slice
```

## Corpus provenance

`corpus/` holds **only real artifacts**: the PNG files that armored-archer
ships under `app_store_assets/` (43 files, copied read-only).
`corpus/manifest.json` records, per artifact, the source path inside
armored-archer, the byte size, the SHA-256, the submission group and — where
armored-archer's `app_store_assets/SCREENSHOT_SPEC.md` declares one — the
expected store dimensions.

The in-repo visual-suite baseline directory
(`armored-archer/test/screenshots/baseline/`) contains only a `.gitkeep`,
i.e. **zero** gameplay baselines exist in that repository today; see
`REPORT.md` §"Corpus findings".

The `seeded/` folder holds *derived copies* of corpus images (blur, resize,
crush, placeholder, duplicate). They are defect seeds, not corpus content:
the corpus itself contains no generated images.

## Requirements

Python 3.12, Pillow 10.2.0, NumPy 1.26.4 (both already present on this VM).
No network access, no randomness in any pass/fail path, no wall-clock
dependence in any decision. Runtime is measured and reported, never gated
per image.
