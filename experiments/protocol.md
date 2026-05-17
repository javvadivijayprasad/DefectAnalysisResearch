# Experiment protocol — Paper 7

This document pins down exactly what the experiment does so that results are reproducible and robust to reviewer objections.

## Unit of analysis

**One test-run × file triple.** For every failing test in every historical run, we produce one row per implicated file. Each row is labeled with the observed outcome and the seven repository features at the commit under test.

## Temporal split

- Training window: everything up to `train_end_iso` in `paper7_default.yaml`.
- Evaluation window: the following `evaluation_window_months`.
- All features are computed as of the *commit under test* — never using information that would not be available at prediction time. This extends the Paper 4 leakage analysis: we exclude bug-fix commit counts by construction.

## SZZ labeling

For every row (`run_id`, `file_path`), we mark `real_defect = 1` iff within `horizon_days` after the run there exists a commit that:

1. Modifies `file_path`, **and**
2. Is referenced by an issue whose labels intersect `bug_label_aliases`.

Limitations acknowledged: SZZ under-counts defects that were never filed (false negatives) and over-counts "fix" commits that were actually refactors (false positives). We report both an SZZ-only and an SZZ+issue-text hybrid labeling to gauge sensitivity.

## Methods under evaluation

1. **pre_only** — Paper 4 baseline: score repo features, threshold at 0.45, no failure fusion.
2. **fail_only** — failure-only triage: a file is "defect" iff an implicated failure occurred. No ML.
3. **fused_rule** — proposed method with the rule-cascade taxonomy classifier.
4. **fused_ml** — proposed method with the gradient-boosting taxonomy classifier (trained on the failure × diff feature set described below).

## Taxonomy classifier features

For method `fused_ml`, each failure example is represented by:

- **Exception-type embedding**: one-hot over the top-30 exception types plus `other`.
- **HTTP status** (if any): integer, bucketized.
- **Schema-error-path present**: boolean.
- **Diff features**: schema-changed, fixture-changed, validator-changed, config-changed, app-code-changed (booleans per commit range).
- **Defect-probability prior**: max probability across implicated files.
- **Historical flake rate**: failure count / run count for this test over the last 40 runs.
- **Locator-heal event**: boolean, from `self-healing-service`.

## Metrics

- **Precision@1** — among implicated files ranked by real_defect_probability, was the top-1 a real defect?
- **Precision@3 / Recall@5** — standard ranking-quality metrics.
- **Expected Calibration Error (ECE)** — probabilities should match observed frequencies.
- **Mean triage time** — simulated via a cost model: developer inspects ranked implicated files in order, resolves on first real defect found, cost increases with each false-positive inspection.
- **Category-F1 macro** — over the eight taxonomy categories, evaluated on held-out manual labels.

## Statistical treatment

All headline claims are tested with:

- Paired bootstrap on repository means (10 000 resamples).
- Wilcoxon signed-rank across the per-repository metric differences.
- Effect sizes reported as Cliff's delta.

## Threats to validity

- **SZZ noise.** Mitigated by reporting hybrid labeling and by stratifying results by label confidence.
- **Tangled changes** (Herzig 2015). Mitigated by filtering commits with >5 files changed from the SZZ link set and reporting both filtered and unfiltered metrics.
- **Repository selection bias.** Five large projects; results may not generalise to small private codebases. We flag this explicitly and sketch what a replication at small-repo scale should look like.
- **Flake label leakage.** We define flaky tests from *held-out* run history only — never from the evaluation window.

## Reporting checklist

Every headline number in the paper must have:

- A row in `results/*.json` with `experiment_id`, `method_id`, `repo`, `metric`, `value`, `ci_low`, `ci_high`, `n`.
- A CSV table in `tables/` regenerable from `results/`.
- A figure in `figures/` regenerable from `tables/`.

This closes the experiment → result → table → figure → paper loop with no manual intermediate steps.
