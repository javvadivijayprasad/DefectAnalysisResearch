# Changelog

All notable changes to this reproducibility bundle are documented here.
Versions follow semantic versioning; the version is bumped on each Zenodo

## 4.0.0 — 2026-10-02 (corrected corpus; supersedes all 3.0.0 results)

A code audit before resubmission found three construction faults in the 3.0.0 corpus (`scripts/build_real_events.py`). All three are fixed in `scripts/build_real_events_v4.py`, and every result was rerun.

- Defects4J features were computed at the synthetic `BUGGY_VERSION` tag that `defects4j checkout` creates, whose history includes the fix, so the seven process metrics of fix files contained post-fix commits (a label leak; fix-file `commit_frequency` was 0.03 against 0.11 for distractors). Now computed at `revision.id.buggy` from `active-bugs.csv`.
- BugsInPy features were proxies derived from how often a file appears in the project's fix pool (`commit_count = freq`, `lines_added = freq*20`, and so on), not git history. Now the 17 upstream repositories are cloned from `github_url`, checked out at `buggy_commit_id`, and the same `git_features_for_file()` is used as for Java.
- Distractors used two schemes (same-directory siblings for Java, other bugs' fix files for Python). Now same-directory siblings at the pre-fix revision for both, with no `test` in the path, 3–8 candidates per event, MD5-seeded; events with no sibling are skipped rather than counted as a free top-1 hit.

Consequences: 1,267 events (was 1,323), 6,716 rows (was 6,988). Headline numbers change substantially: cross-project predictor Precision@1 0.541 (was 0.777), ECE 0.025 (was 0.021); rule fusion ranks identically to the predictor by construction (its inputs are event-level constants), ECE 0.091; learned fusion 0.496 / 0.082; Claude Sonnet 4.6 0.532 / 0.065 with the parity concentrated on Lang, Math and Time; GPT-4o-mini 0.461 / 0.065. The Discussion paragraph of the 3.0.0 manuscript that described exception-type, HTTP-status and flake-rate variation is withdrawn: those columns take a single value in both corpora. The 3.0.0 record remains on Zenodo for comparison and must not be cited for its numbers.

Added: `analysis_v4.py` (every manuscript number from the result files), `make_figures_v4.py`, `datasets/real_events_v4.parquet.build_log.csv`, README in the PeerJ layout, this changelog.


re-upload.

## v2.0.0 (2026-08-09) — Real-data rebuild (MAJOR)

**Breaking change from v1.0.0**: the entire evaluation is re-run on real
defects. The synthetic 6,000-event corpus of v1.0.0 has been removed and
replaced. Headline results are quantitatively and qualitatively different.
The manuscript targets *Journal of Systems and Software* (Elsevier) rather
than the EMSE submission that accompanied v1.0.0.

### Added
- **Real-defect corpus**: 1,323 events across 33 open-source projects
  - Defects4J v2.0.1: 824 events (17 Java projects)
  - BugsInPy: 499 events (16 Python projects)
  - 6,988 file-level rows (mean ~5.28 files per event)
  - `real_defect` fraction: 0.2311
- **Leave-one-project-out (LOPO)** cross-validation harness
- **Confirmatory ablation**: fused_ml retrained on pre-execution features
  only (0.7627), decomposing the fused_ml deficit into feature harm and
  ensemble over-fitting components
- **Per-repo precision figure** (`fig_per_repo_precision.png`)
- **Reliability diagrams** across all four methods
- **Manuscript LaTeX source** (elsarticle.cls, 27 pages, JSS-formatted)
- **JSS cover letter**, structured highlights, and CRediT statement

### Changed
- **Method ordering reversed**: on real data, `fused_rule` (p@1 = 0.7800)
  edges out `pre_only` (p@1 = 0.7770) and `fused_ml` (p@1 = 0.7475).
  On the v1.0.0 synthetic data, `fused_ml` had led. The paper's central
  claim now demonstrates that ML fusion does *not* automatically dominate
  rule-based fusion when the pre-execution prior is already strong.
- **Calibration numbers**: excellent for the three ranking methods
  (ECE 0.021 for `pre_only`, 0.033 for `fused_ml`, 0.063 for `fused_rule`)
  and catastrophic for `fail_only` (ECE 0.7689).
- **License documentation** clarified as CC-BY-4.0 for code + data (same
  as v1.0.0; the earlier draft README/CITATION incorrectly listed
  Apache-2.0 and has been corrected).

### Removed
- Synthetic 6,000-event generator and its output (superseded)
- All EMSE-oriented material (cover letter, formatting)

### Files added since v1.0.0
- `datasets/real_events.parquet`, `real_events_d4j.parquet`,
  `real_events_bip.parquet` (real bug schema)
- `results/summary_real.json`, `per_event_metrics_real.csv`,
  `per_row_scores_real.csv`
- `results/figures/fig_headline_bars.png`, `fig_ece_bars.png`,
  `fig_reliability.png`, `fig_per_repo_precision.png`
- `paper/paperF_JSS.pdf` and `.tex` (JSS submission)
- `scripts/build_real_events.py`, `run_real_experiment.py`,
  `generate_real_figures.py`
- `docs/REPRODUCIBILITY.md`, `SETUP.md`, `SCHEMA.md`, `FINALIZE_BUNDLE.md`,
  `QC_JSS_AUDIT.md`

## v1.0.0 (2026-06-16) — Initial synthetic-data release

- 6,000 synthetic failure events
- Four attribution methods evaluated (`pre_only`, `fail_only`,
  `fused_rule`, `fused_ml`)
- Submitted to EMSE (later withdrawn during transfer to
  Discover Applied Sciences, then rebuilt as v2.0.0)
- License: CC-BY-4.0
