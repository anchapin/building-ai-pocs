# REPORT — media-qa-gate, POC #51 Phase 0 slice 1 (issue #57)

**Slice verdict: Proceed** — to the full 3-surface Phase 0 proposal.

* Surface: armored-archer gameplay / store screenshots (one surface only).
* Scope: a standalone, report-only pixel floor with five per-image checks,
  measured on 43 real artifacts plus 6 seeded defect copies.
* Not in this slice: Phase 1, CI wiring, workflow files, any change to
  armored-archer, any LLM/VLM in the pass/fail path, any new image
  generation for the corpus.
* Nothing here blocks a merge: `mediaqa` is report-only by construction.

---

## 1. Raw check × artifact table (first deliverable)

### 1.1 Clean corpus — 43 real artifacts, `python3 media-qa-gate/mediaqa.py media-qa-gate/corpus/` (exit 1)

```
artifact                                       | blank       | dimensions  | exposure    | sharpness   | duplicate   | runtime_s
--------------------------------------------------------------------------------------------------------------------------------
android/feature_graphic_1024x500.png           | ok          | ok          | ok          | ok          | ok          | 0.094
android/icon_1024x1024.png                     | ok          | ok          | ok          | ok          | ok          | 0.139
android/icon_512x512.png                       | ok          | ok          | ok          | ok          | ok          | 0.046
android/screenshots/campaign.png               | ok          | ok          | ok          | ok          | ok          | 0.227
android/screenshots/combat.png                 | ok          | ok          | ok          | ok          | ok          | 0.148
android/screenshots/gear_inventory.png         | ok          | ok          | ok          | ok          | ok          | 0.150
android/screenshots/leaderboard.png            | ok          | ok          | ok          | ok          | ok          | 0.148
android/screenshots/main_menu.png              | ok          | ok          | ok          | ok          | ok          | 0.149
android/screenshots/screenshot_1.png           | ok          | ok          | ok          | ok          | ok          | 0.147
android/screenshots/screenshot_2.png           | ok          | ok          | ok          | ok          | ok          | 0.078
android/screenshots/screenshot_3.png           | ok          | ok          | ok          | ok          | ok          | 0.392
android/screenshots/shop.png                   | ok          | ok          | ok          | ok          | ok          | 0.163
ios/feature_graphic_1200x600.png               | ok          | ok          | ok          | ok          | ok          | 0.068
ios/icon_1024x1024.png                         | ok          | ok          | ok          | ok          | warn        | 0.091
ios/screenshots/ipad/campaign.png              | ok          | ok          | ok          | ok          | ok          | 0.464
ios/screenshots/ipad/combat.png                | ok          | ok          | ok          | ok          | ok          | 0.417
ios/screenshots/ipad/gear_inventory.png        | ok          | ok          | ok          | ok          | ok          | 0.669
ios/screenshots/ipad/leaderboard.png           | ok          | ok          | ok          | ok          | ok          | 0.401
ios/screenshots/ipad/main_menu.png             | ok          | ok          | ok          | ok          | ok          | 0.402
ios/screenshots/ipad/screenshot_1.png          | ok          | ok          | ok          | ok          | ok          | 0.398
ios/screenshots/ipad/screenshot_2.png          | ok          | ok          | ok          | ok          | ERROR       | 0.669
ios/screenshots/ipad/screenshot_3.png          | ok          | ok          | ok          | ok          | ok          | 0.399
ios/screenshots/ipad/screenshot_4.png          | ok          | ok          | ok          | ok          | ERROR       | 0.398
ios/screenshots/ipad/shop.png                  | ok          | ok          | ok          | ok          | ok          | 0.403
ios/screenshots/iphone_5_5/campaign.png        | ok          | ok          | ok          | ok          | ok          | 0.192
ios/screenshots/iphone_5_5/combat.png          | ok          | ok          | ok          | ok          | ok          | 0.188
ios/screenshots/iphone_5_5/gear_inventory.png  | ok          | ok          | ok          | ok          | ok          | 0.190
ios/screenshots/iphone_5_5/leaderboard.png     | ok          | ok          | ok          | ok          | ok          | 0.191
ios/screenshots/iphone_5_5/main_menu.png       | ok          | ok          | ok          | ok          | ok          | 0.191
ios/screenshots/iphone_5_5/screenshot_1.png    | ok          | ok          | ok          | ok          | ok          | 0.191
ios/screenshots/iphone_5_5/screenshot_2.png    | ok          | ok          | ok          | ok          | ok          | 0.188
ios/screenshots/iphone_5_5/screenshot_3.png    | ok          | ok          | ok          | ok          | ERROR       | 0.190
ios/screenshots/iphone_5_5/shop.png            | ok          | ok          | ok          | ok          | ok          | 0.195
ios/screenshots/iphone_6_7/campaign.png        | ok          | ok          | ok          | ok          | ok          | 0.254
ios/screenshots/iphone_6_7/combat.png          | ok          | ok          | ok          | ok          | ok          | 0.241
ios/screenshots/iphone_6_7/gear_inventory.png  | ok          | ok          | ok          | ok          | ok          | 0.243
ios/screenshots/iphone_6_7/leaderboard.png     | ok          | ok          | ok          | ok          | ok          | 0.241
ios/screenshots/iphone_6_7/main_menu.png       | ok          | ok          | ok          | ok          | ok          | 0.418
ios/screenshots/iphone_6_7/screenshot_1.png    | ok          | ok          | ok          | ok          | ok          | 0.241
ios/screenshots/iphone_6_7/screenshot_2.png    | ok          | warn        | ok          | ok          | ok          | 0.224
ios/screenshots/iphone_6_7/screenshot_3.png    | ok          | ok          | ok          | ok          | ok          | 0.250
ios/screenshots/iphone_6_7/screenshot_4.png    | ok          | ok          | ok          | ok          | ERROR       | 0.243
ios/screenshots/iphone_6_7/shop.png            | ok          | ok          | ok          | ok          | ok          | 0.242

artifacts=43 errors=4 warned_artifacts=2
runtime_avg_s=0.255 runtime_max_s=0.669 (slowest=screenshot_2.png)
```

(The `runtime_s` column is per image; the run above is one representative
run of a deterministic checker — the runtimes vary by a few percent between
runs, the statuses do not.)

The six findings printed by that run, verbatim:

```
media-qa-gate/corpus/ios/icon_1024x1024.png: warn duplicate identical_pixels_of=icon_1024x1024.png other_group=android; same pixels as an artifact in another submission group; expected for shared icons, suspicious otherwise
media-qa-gate/corpus/ios/screenshots/ipad/screenshot_2.png: error duplicate identical_pixels_of=screenshot_1.png group=ios/screenshots/ipad; artifact is pixel-identical to another file in the same submission group; store reviewers reject duplicated slots - capture a distinct scene
media-qa-gate/corpus/ios/screenshots/ipad/screenshot_4.png: error duplicate identical_pixels_of=screenshot_3.png group=ios/screenshots/ipad; artifact is pixel-identical to another file in the same submission group; store reviewers reject duplicated slots - capture a distinct scene
media-qa-gate/corpus/ios/screenshots/iphone_5_5/screenshot_3.png: error duplicate identical_pixels_of=screenshot_2.png group=ios/screenshots/iphone_5_5; artifact is pixel-identical to another file in the same submission group; store reviewers reject duplicated slots - capture a distinct scene
media-qa-gate/corpus/ios/screenshots/iphone_6_7/screenshot_2.png: warn dimensions w=1242 h=2688 area=3338496 aspect=0.462 expected=1290x2796; geometry differs from the declared store spec; re-capture at the specified resolution
media-qa-gate/corpus/ios/screenshots/iphone_6_7/screenshot_4.png: error duplicate identical_pixels_of=screenshot_3.png group=ios/screenshots/iphone_6_7; artifact is pixel-identical to another file in the same submission group; store reviewers reject duplicated slots - capture a distinct scene
```

### 1.2 Seeded defects — `python3 media-qa-gate/mediaqa.py media-qa-gate/seeded/` (exit 1)

```
artifact                          | blank       | dimensions  | exposure    | sharpness   | duplicate   | runtime_s
-------------------------------------------------------------------------------------------------------------------
blurred_frame.png                 | ok          | ok          | ok          | ERROR       | ok          | 0.421
crushed_exposure.png              | ERROR       | ok          | ERROR       | ok          | ok          | 0.333
duplicate_slot/campaign.png       | ok          | ok          | ok          | ok          | ok          | 0.528
duplicate_slot/campaign_copy.png  | ok          | ok          | ok          | ok          | ERROR       | 0.472
placeholder_1x1.png               | ERROR       | ERROR       | ok          | ok          | ok          | 0.038
solid_colour_frame.png            | ERROR       | ok          | ok          | ok          | ok          | 0.198
wrong_dimensions.png              | ok          | ERROR       | ok          | ok          | ok          | 0.034

artifacts=7 errors=6 warned_artifacts=0
runtime_avg_s=0.289 runtime_max_s=0.528 (slowest=campaign.png)
```

---

## 2. Seeded catch count

**5 / 5 required defect kinds caught as `error` (100 %).** A sixth seed
(duplicate pair) is also caught. Each catch named by check + measurement:

| # | seeded kind | derived from | caught by | measurement (verbatim) |
| --- | --- | --- | --- | --- |
| 1 | 1×1 placeholder | `android/screenshots/combat.png` | `dimensions` | `w=1 h=1 area=1 aspect=1.000` (also `blank luma_std=0.000 luma_mean=32.00 modal_frac=1.0000`) |
| 2 | single-colour frame | `android/screenshots/campaign.png` | `blank` | `luma_std=0.000 luma_mean=26.00 modal_frac=1.0000` |
| 3 | wrong dimensions | `android/screenshots/main_menu.png` | `dimensions` | `w=160 h=120 area=19200 aspect=1.333` |
| 4 | blurred frame | `ios/screenshots/iphone_5_5/campaign.png` | `sharpness` | `laplacian_var=0.486 luma_std=14.597` |
| 5 | crushed exposure | `ios/screenshots/iphone_6_7/combat.png` | `exposure` | `luma_mean=1.11 dark_frac=0.9701 bright_frac=0.0000` (also `blank luma_std=0.661`) |
| 6 | duplicate frame (extra seed) | `ios/screenshots/ipad/campaign.png` | `duplicate` | `identical_pixels_of=campaign.png group=duplicate_slot` |

The seeded set is regenerated deterministically by
`python3 media-qa-gate/seed_defects.py` (no randomness, no network); the
seed index lives in `media-qa-gate/seeded/seeds.json`.

Co-firing is honest, not noise: the 1×1 placeholder and the crushed frame
are *also* blank frames, so `blank` fires on them too. `sharpness` is
suppressed on flat frames (luma std < 3.0) because "blurred" is not a
meaningful statement about a frame with no edges; that suppression is why
the crushed frame shows `sharpness ok`.

---

## 3. False-positive headline

**0 false errors on clean artifacts.** Of the 43 real artifacts, 39 are
clean and produce **zero** error findings. The remaining 4 produce errors
that are **true positives, provable by SHA-256 identity** — they are
byte-identical copies of a sibling slot in the same submission group, i.e.
real defects that exist in armored-archer's shipped store assets today:

| artifact | identical to | sha256 (first 12) |
| --- | --- | --- |
| `ios/screenshots/ipad/screenshot_2.png` | `ios/screenshots/ipad/screenshot_1.png` | `cfbf20b2115e` |
| `ios/screenshots/ipad/screenshot_4.png` | `ios/screenshots/ipad/screenshot_3.png` | `cd55f2510d4a` |
| `ios/screenshots/iphone_5_5/screenshot_3.png` | `ios/screenshots/iphone_5_5/screenshot_2.png` | `a895e005a210` |
| `ios/screenshots/iphone_6_7/screenshot_4.png` | `ios/screenshots/iphone_6_7/screenshot_3.png` | `7ace6a2a5321` |

If these four are judged "not clean", the false-error count on genuinely
clean artifacts is **0/39 = 0 %** and the *true-positive* count on the real
corpus is **4/43 = 9.3 %**.

Two warnings, zero errors, and both are deliberate:

* `ios/icon_1024x1024.png` — pixel-identical to `android/icon_1024x1024.png`
  but in a different submission group; the same icon legitimately ships to
  both stores, so cross-group identity is a **warning**, not an error.
* `ios/screenshots/iphone_6_7/screenshot_2.png` — 1242×2688 where
  `app_store_assets/SCREENSHOT_SPEC.md` declares 1290×2796 for that device
  class. A spec deviation is a **warning**; the `dimensions` error band is a
  universal floor (shortest side < 320 px, longest side > 3840 px, aspect
  outside [0.2, 5.0]), not a spec-exact match. Making it spec-exact would
  have produced false errors on real artifacts (the android landscape
  extras `screenshot_1/2/3.png` are 1920×1080 / 1280×720 / 2560×1440 while
  the android spec line says "phone portrait 1080×1920").

### Threshold margins (error threshold vs the observed real corpus)

| check | error threshold | worst real value | margin |
| --- | --- | --- | --- |
| `blank` (luma std) | < 3.0 | 7.48 (`android/screenshots/screenshot_3.png`) | 2.5× |
| `blank` (modal colour frac, warn only) | >= 0.995 | 0.9777 (`ios/screenshots/ipad/shop.png`) | 0.017 |
| `exposure` (dark frac) | >= 0.90 | 0.0851 (icons) | 10.6× |
| `exposure` (bright frac) | >= 0.90 | 0.0163 (`android/icon_512x512.png`) | 55× |
| `exposure` (luma mean band) | <= 8 / >= 247 | 34.13 … 71.85 | wide |
| `sharpness` (Laplacian var) | < 20 | 39.54 (`ios/screenshots/ipad/screenshot_1.png`) | 2.0× |
| `dimensions` (shortest side) | < 320 px | 500 px | 1.6× |
| `dimensions` (longest side) | > 3840 px | 2796 px | 1.4× |

No threshold had to be tuned to make a real artifact pass: the corpus
minima/maxima are all outside the error bands by the margins above, and the
thresholds are store-spec limits (320/3840 px, from
`app_store_assets/SCREENSHOT_SPEC.md`) or round numbers well clear of the
observed corpus.

---

## 4. Runtime per image

Reported for every artifact in the tables above (`runtime_s` column).

* clean corpus: `runtime_avg_s=0.255`, `runtime_max_s=0.669`
  (slowest: `ios/screenshots/ipad/screenshot_2.png`, 2048×2732).
* seeded set: `runtime_avg_s=0.289`, `runtime_max_s=0.528`.
* Slice bar is "≤ 5 s per image on this VM", measured as an average:
  **0.255 s/image average, 0.669 s worst case → the bar is met with a
  19× margin.** Runtime is reported, never gated per image; no decision
  anywhere in `mediaqa.py` depends on wall-clock time.

---

## 5. Head-to-head vs armored-archer's RMSE suite

The RMSE suite (`armored-archer/scripts/compare-screenshots.py`, read
read-only) is a **baseline-relative** comparator: it shells out to
ImageMagick `compare -metric RMSE -fuzz 1%`, parses the normalised RMSE
out of the parentheses, and fails when that value exceeds `--threshold`
(default 0.01 normalised).

**Environment fact, reported rather than hidden:** the ImageMagick `compare`
binary is **not installed on this VM** (`which compare` → not found), so
the suite itself cannot be executed here. `media-qa-gate/head_to_head.py`
records that verbatim ("SKIPPED: ImageMagick 'compare' binary is not
installed on this VM") and computes an explicitly-labelled **RMSE-equivalent**
in NumPy using the same arithmetic ImageMagick uses for 8-bit images
(RMSE/255) and the suite's own 0.01 threshold. That emulation is a
measurement aid, not the suite.

| pair (current vs baseline) | RMSE-equivalent (normalised) | RMSE-suite verdict | mediaqa verdict |
| --- | --- | --- | --- |
| `placeholder_1x1` vs its source | n/a (size mismatch) | FAIL | **error** (`dimensions`, `blank`) |
| `solid_colour_frame` vs its source | 0.102962 | FAIL | **error** (`blank`) |
| `wrong_dimensions` vs its source | n/a (size mismatch) | FAIL | **error** (`dimensions`) |
| `blurred_frame` vs its source | 0.040351 | FAIL | **error** (`sharpness`) |
| `crushed_exposure` vs its source | 0.167275 | FAIL | **error** (`exposure`, `blank`) |
| **real duplicate pair** (`ipad/screenshot_1` vs `screenshot_2`) | **0.000000** | **PASS** | **error** (`duplicate`) |

**What the floor catches that the RMSE suite does not:**

1. **Duplicates — the decisive one.** The four real duplicated slots in
   armored-archer's shipped assets score RMSE exactly 0.0, so the RMSE
   suite **passes** them (identical is its definition of "no change"). The
   floor flags all four. This is the opposite of duplicating the suite.
2. **Single artifacts with no baseline.** The RMSE suite needs a stored
   baseline; a brand-new capture (the moment a placeholder gets written) has
   none. The floor is stateless and judges each artifact on its own.
3. **Semantic, not just "different".** The RMSE suite says "these two
   images differ"; it cannot say *why*. The floor names the defect kind
   (blank / crushed / blurred / wrong size / duplicate) and prints a fix
   hint, and it distinguishes a crushed frame from a legitimately dark one.
4. **Store-legality.** A 160×120 export is an error to the floor; to the
   RMSE suite it is merely "different" (or a size-mismatch crash).

**What the RMSE suite catches that the floor does not (and this is not a
weakness to be fixed here):** the suite detects *baseline-relative pixel
drift* — a scene that changed between two runs. The floor is deliberately
single-image and stateless; it cannot tell "the menu moved 3 px" from
"the menu is fine". The two tools are complementary, not substitutes.

**Why the RMSE suite cannot serve as the floor on this surface:** of the
132 comparable same-group real artifact pairs, **128 (97 %)** exceed the
0.01 RMSE threshold — i.e. the suite's verdict on this corpus is
"everything differs from everything", which is a regression signal, not a
quality floor. The 4 pairs it passes are exactly the 4 pairs the floor
catches.

---

## 6. Corpus findings (this surface's standing pain)

* **43 real artifacts** were available in `armored-archer/app_store_assets/`
  (all PNGs under that tree) — above the 10-artifact floor the issue asked
  for, so no replacements were needed and none were generated.
* **Zero in-repo gameplay baselines exist.** `armored-archer/test/screenshots/baseline/`
  contains only `.gitkeep`, and `armored-archer/test/suites/visual/` holds
  four GDScript suites, no images. So the visual-suite baseline surface
  named by the issue is **empty**; the corpus is the store-asset surface
  only. The 43 artifacts are copied into `media-qa-gate/corpus/` with a
  manifest naming each source path (`corpus/manifest.json`), so the slice
  is self-contained.
* **Real defect rate on this surface is not ~0:** 4/43 (9.3 %) artifacts are
  provable duplicate slots, plus 1/43 (2.3 %) that deviates from the
  declared store dimensions → 5/43 = 11.6 % of the shipped surface is
  defective by the floor's own (and the store's) definition. The standing
  pain is concrete: duplicated marketing slots in the App Store
  submission, i.e. wasted slots and reviewer risk.

---

## 7. Environment, commands, and reproducibility

* Python 3.12.3, **Pillow 10.2.0 and NumPy 1.26.4 are already installed**
  on this VM — no provisioning was needed or performed, no large installs.
* `armored-archer` was **read only**: `build_corpus.py` copies files out of
  `app_store_assets/` and never writes, moves or modifies anything there;
  `scripts/compare-screenshots.py` was read, and the one attempt to invoke
  it writes its diff image to a temporary directory.

Verification commands (run from the worktree root):

```sh
$ python3 -m pytest media-qa-gate/ -q
....................                                                     [100%]
20 passed in 15.70s

$ python3 media-qa-gate/mediaqa.py media-qa-gate/corpus/ ; echo "exit=$?"
... (6 findings: 4 error duplicate, 1 warn duplicate, 1 warn dimensions) ...
artifacts=43 errors=4 warned_artifacts=2
runtime_avg_s=0.255 runtime_max_s=0.669 (slowest=screenshot_2.png)
exit=1

$ python3 media-qa-gate/mediaqa.py media-qa-gate/seeded/ ; echo "exit=$?"
... (8 error lines: 1 per seeded defect + 3 co-fires) ...
artifacts=7 errors=6 warned_artifacts=0
runtime_avg_s=0.289 runtime_max_s=0.528 (slowest=campaign.png)
exit=1
```

Exit code 1 on any error finding is the checker's contract; in this slice
that exit code is **reported, not enforced** by anything.

Test coverage (20 tests, `media-qa-gate/tests/test_mediaqa.py`): the
manifest names every copied artifact and its source; ≥ 10 real artifacts
present; **no** blank/dimensions/exposure/sharpness error on any real
artifact; the duplicate errors are exactly the four known real duplicates;
the spec deviation is a warning and not an error; the shared cross-store
icon is a warning and not an error; every seed is caught by its expected
check; ≥ 5 seed kinds present; the finding-line format matches
`^(error|warn) <check> <measurement>; <hint>$`; the seeded run exits 1 and
a clean directory exits 0; an unreadable file is an error; duplicate
detection is scoped per submission group; measurements are identical across
repeated runs; average runtime < 5 s/image.

---

## 8. Slice verdict against the gate

Gate for this slice (parent bars scaled to one surface): **Proceed** at
≥ 90 % of this surface's seeded defects caught as errors, 0 false errors on
clean artifacts, ≤ 5 s per image on this VM. **Kill** if false errors
cannot be tuned out without gutting a check, or if the floor merely
duplicates the RMSE suite. **Park** if catches work but this surface's real
corpus defect rate is ~0 and no standing pain maps to it.

| gate bar | measured | holds? |
| --- | --- | --- |
| ≥ 90 % of seeded defects caught as errors | 5/5 kinds = 100 % (6/6 seeds with an expected error) | **yes** |
| 0 false errors on clean artifacts | 0 errors on the 39 clean artifacts; the 4 errors are provable true positives (SHA-256-identical siblings) | **yes** |
| ≤ 5 s per image | 0.255 s average, 0.669 s worst case | **yes** |

* **Kill is not triggered.** False errors were tuned out *without* gutting
  a check — every check kept its error band; the two borderline real cases
  (shared icon, one spec deviation) were resolved by *scoping*
  (per-group duplicate detection; warn-not-error for spec deviations), not
  by weakening a threshold. And the floor demonstrably does **not** merely
  duplicate the RMSE suite: the 4 artifacts the RMSE suite passes
  (RMSE = 0.0) are exactly the 4 it catches.
* **Park is not triggered.** This surface's real corpus defect rate is
  11.6 % (5/43), driven by duplicated store slots — standing pain that
  maps directly to wasted App Store marketing slots and reviewer risk. The
  floor also produced one actionable spec finding
  (`iphone_6_7/screenshot_2.png`, 1242×2688 vs the declared 1290×2796).
* **Proceed** to the full 3-surface Phase 0 proposal, with the
  qualifications below.

**Qualifications carried into the Phase 0 proposal (not premises of this
verdict):**

1. The duplicate check is **group-scoped** by design; cross-group identity
   is a warning. A 3-surface proposal must agree on what a "submission
   group" is per surface, or the duplicate rule will differ per surface.
2. The dimension check is a **universal floor**, not a spec-exact check.
   A per-surface spec table (like `corpus/manifest.json` here) should drive
   spec deviations as warnings, with the floor staying store-agnostic.
3. The RMSE comparison on this VM was **emulated** (ImageMagick absent).
   A Phase 0 proposal that wants a true head-to-head needs ImageMagick
   installed, or a NumPy re-implementation used for both sides.
4. The sharpness threshold has the thinnest margin (2.0× on
   `laplacian_var`); a second surface with softer renders should re-measure
   it before the threshold is frozen.
5. Report-only status must survive into Phase 0: nothing in this slice
   blocks a merge, and no CI wiring is included or proposed here.

---

## Claims

- [observed] 43 real artifacts were copied from `armored-archer/app_store_assets/` into `media-qa-gate/corpus/`, each with its source path recorded in `media-qa-gate/corpus/manifest.json` — source: `python3 media-qa-gate/build_corpus.py`, output `copied 43 artifacts into .../media-qa-gate/corpus`, manifest field `count: 43`.
- [observed] The in-repo visual-suite baseline directory holds no images (`test/screenshots/baseline/` contains only `.gitkeep`) — source: `ls -la ~/workspace/armored-archer/test/screenshots/baseline/`.
- [observed] The clean-corpus run reports 4 error findings and 2 warnings over 43 artifacts, exit code 1 — source: `python3 media-qa-gate/mediaqa.py media-qa-gate/corpus/`, output `artifacts=43 errors=4 warned_artifacts=2`.
- [observed] The four duplicate errors are byte-identical pairs (SHA-256 `cfbf20b2115e`, `cd55f2510d4a`, `a895e005a210`, `7ace6a2a5321`) — source: `media-qa-gate/corpus/manifest.json` `sha256` fields.
- [observed] All 5 seeded defect kinds are caught as errors, each named by check and measurement — source: `python3 media-qa-gate/mediaqa.py media-qa-gate/seeded/`, exit 1, table in §1.2.
- [observed] Average runtime on the corpus is 0.255 s/image, max 0.669 s — source: `python3 media-qa-gate/mediaqa.py media-qa-gate/corpus/`, output `runtime_avg_s=0.255 runtime_max_s=0.669`.
- [observed] ImageMagick's `compare` is not installed on this VM, so armored-archer's RMSE suite could not be executed; an RMSE-equivalent gives 0.000000 for the real duplicate pair (suite verdict PASS) and > 0.01 for every other seeded pair — source: `python3 media-qa-gate/head_to_head.py`, output table in §5.
- [observed] 128 of 132 comparable same-group real artifact pairs exceed the suite's 0.01 RMSE threshold, and the 4 pairs that do not are the 4 duplicate pairs — source: pairwise RMSE-equivalent over `media-qa-gate/corpus/` (method and command in §5).
- [inference] The floor catches a defect class on this surface that the RMSE suite structurally cannot catch (duplicates score RMSE 0.0), so it is not a duplicate of the RMSE suite — from the duplicate-pair RMSE (0.000000) and the four duplicate errors above.
- [inference] The floor is not tuned to this corpus: every error threshold sits outside the observed corpus range with a ≥ 1.4× margin and the thresholds derive from store specs, not from corpus statistics — from the threshold-margin table in §3.
- [inference] This surface's real defect rate is 11.6 % (5/43), so the Park condition (≈ 0 % defect rate, no standing pain) does not apply — from the 4 duplicate errors, the 1 spec warning, and the 43-artifact corpus count.
- [unsupported] That the other two surfaces (whatever they are) behave like this one — carried as an assumption for the Phase 0 proposal; NOT a premise of this verdict.
- [unsupported] That 5 s/image is representative of a slower CI runner — carried as an assumption; the measurement here is from this VM only and is not a premise of this verdict.
- [decision] Proceed to the full 3-surface Phase 0 proposal — worker-57 slice 1, 2026-11-14.
