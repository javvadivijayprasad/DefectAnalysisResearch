# Event schema

This document defines the parquet schema used across the corpus, the fusion
methods, and the reported metrics.

## Row grain

**One row = one (event, file) pair.** A single defect event contributes as
many rows as there are candidate files considered by the ranker (the buggy
file plus its sibling distractors). Grouping by `event_id` recovers the
per-event candidate set.

- Total events: **1,323**
- Total rows: **6,988**
- Mean files per event: **~5.28**
- Overall `real_defect` fraction: **0.2311**

## Columns

### Identifiers

| Column      | Type   | Notes                                                    |
| ----------- | ------ | -------------------------------------------------------- |
| `event_id`  | string | Unique defect id (`repo` + bug id).                      |
| `repo`      | string | Project name; 33 unique values (17 D4J + 16 BiP).        |
| `file_name` | string | File path within the repo for this candidate.            |

### Label

| Column        | Type      | Notes                                                          |
| ------------- | --------- | -------------------------------------------------------------- |
| `real_defect` | int (0/1) | **1 iff the file was in the fix commit's diff**, else **0**.   |

Ground truth for Defects4J comes from the framework's `bug.info` /
`modified.classes`; for BugsInPy it comes from `bug_patch.txt` in each bug
directory. Sibling files from the same package/directory serve as
distractors with `real_defect = 0`.

### Failure signal (pre-attribution priors from the failing test)

| Column                  | Type      | Notes                                                                |
| ----------------------- | --------- | -------------------------------------------------------------------- |
| `exception_type`        | string    | Categorical, drawn from `EXCEPTION_TYPES` (see below).               |
| `exception_idx`         | int       | Position within the failure signal.                                  |
| `http_status`           | int       | HTTP status if applicable (network tests), else 0.                   |

`EXCEPTION_TYPES = ["AssertionError", "TimeoutError", "ConnectionError",
"AttributeError", "ValueError", "KeyError", "TypeError", "RuntimeError",
"Other"]`

### Change-topology signals (pre-execution features)

| Column               | Type      | Notes                                                    |
| -------------------- | --------- | -------------------------------------------------------- |
| `app_code_changed`   | int (0/1) | Production code delta vs. parent commit.                 |
| `validator_changed`  | int (0/1) | Validator/schema-checker delta.                          |
| `schema_changed`     | int (0/1) | Persisted schema (DB / JSON / proto) delta.              |
| `fixture_changed`    | int (0/1) | Test fixture delta.                                      |
| `config_changed`     | int (0/1) | Configuration file delta.                                |
| `locator_healed`     | int (0/1) | UI/element locator auto-repaired.                        |
| `historical_flake_rate` | float  | Test-level flake rate over recent history.               |

### Repo-history features (consumed by `fused_ml`)

Exactly the list `FEATURES` in `scripts/build_real_events.py`:

```python
FEATURES = ["commit_count", "unique_developers", "lines_added",
            "lines_deleted", "code_churn", "file_age_days",
            "commit_frequency"]
```

| Column              | Type   | Notes                                                       |
| ------------------- | ------ | ----------------------------------------------------------- |
| `commit_count`      | int    | Commits touching the file in the recent window.             |
| `unique_developers` | int    | Distinct authors of those commits.                          |
| `lines_added`       | int    | Lines added to the file in the recent window.               |
| `lines_deleted`     | int    | Lines removed from the file in the recent window.           |
| `code_churn`        | int    | `lines_added + lines_deleted`.                              |
| `file_age_days`     | int    | Days since the file's first commit.                         |
| `commit_frequency`  | float  | `commit_count / max(file_age_days, 1)`.                     |

## Fusion methods (all consume the same rows)

| Method       | Consumes                                                                 | Notes                                                    |
| ------------ | ------------------------------------------------------------------------ | -------------------------------------------------------- |
| `pre_only`   | Change-topology + `historical_flake_rate`                                | Deterministic scoring; no training.                      |
| `fail_only`  | Failure signal only                                                      | Naive baseline; poor calibration.                        |
| `fused_rule` | Weighted sum of `pre_only` + `fail_only`                                 | Weights hand-tuned on a held-out development split.      |
| `fused_ml`   | All columns above + `FEATURES` list; logistic regression                 | Trained per LOPO fold; hyperparameters fixed by default. |

## Metrics reported in `results/summary_real.json`

- `p1_mean` — precision at rank 1 across events.
- `p3_mean` — precision at rank 3.
- `r5_mean` — recall at rank 5.
- `mrr_mean` — mean reciprocal rank of the first true positive.
- `triage_s_mean` — expected files a triager must inspect (lower is better).
- `ece_10bin` — Expected Calibration Error, 10 equal-width bins.
