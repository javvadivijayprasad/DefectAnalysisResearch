# Datasets

The three parquet files in this directory are the **primary experimental
corpus** used for the Paper F LOPO experiment.

| File                        | Events | Notes                              |
| --------------------------- | ------ | ---------------------------------- |
| `real_events.parquet`       | 1,323  | Full corpus (Defects4J + BugsInPy) |
| `real_events_d4j.parquet`   | 824    | Defects4J v2.0.1 subset            |
| `real_events_bip.parquet`   | 499    | BugsInPy subset                    |

Total rows across all events in the full corpus: **6,988** (one row per
(event, file) pair; mean ~5.28 files per event). Overall `real_defect`
fraction: **0.2311** — this is the class prior a ranker must beat.

## IMPORTANT: manual copy step

These files live in the author's WSL2 home at `~/paperF/datasets/`. They are
**not** committed to this bundle by the assembler because they are unreachable
from the sandbox filesystem. See `docs/FINALIZE_BUNDLE.md` — the author must
copy them here before uploading to Zenodo:

```bash
# From WSL2 Ubuntu:
cp ~/paperF/datasets/real_events*.parquet \
   /mnt/e/EB1A_Research/EB1_Master/06_Authorship/Research/PaperF_rebuild/zenodo_bundle_v1.0.0/datasets/
```

## Schema

One row = one (event, file) pair. `event_id` groups the rows produced by a
single defect; the row whose `real_defect == 1` is the buggy file that the
ranking methods try to lift to rank 1.

| Column                    | Type    | Description                                                       |
| ------------------------- | ------- | ----------------------------------------------------------------- |
| `event_id`                | string  | Unique identifier for the defect event (repo + bug id).           |
| `repo`                    | string  | Project name (33 unique values).                                  |
| `file_name`               | string  | Path of the candidate file within the repo.                       |
| `real_defect`             | int (0/1) | 1 iff the file is in the fix commit's diff — the label.         |
| `exception_type`          | string  | Exception class from the failing test (categorical).              |
| `exception_idx`           | int     | Position of the exception in the failure signal.                  |
| `http_status`             | int     | HTTP status if applicable (network-related tests), else 0.        |
| `app_code_changed`        | int (0/1) | Did production code change vs. the parent commit?               |
| `validator_changed`       | int (0/1) | Did a validator / schema-checker change?                        |
| `schema_changed`          | int (0/1) | Did a persisted schema (DB / JSON / proto) change?              |
| `fixture_changed`         | int (0/1) | Did a test fixture change?                                      |
| `config_changed`          | int (0/1) | Did a configuration file change?                                |
| `locator_healed`          | int (0/1) | Was a UI/element locator auto-repaired?                         |
| `historical_flake_rate`   | float   | Empirical flake rate for the failing test over last N runs.       |
| `commit_count`            | int     | Commits touching the file in the recent window.                   |
| `unique_developers`       | int     | Distinct authors of those commits.                                |
| `lines_added`             | int     | Lines added to the file in the recent window.                     |
| `lines_deleted`           | int     | Lines removed from the file in the recent window.                 |
| `code_churn`              | int     | `lines_added + lines_deleted`.                                    |
| `file_age_days`           | int     | Days since the file's first commit.                               |
| `commit_frequency`        | float   | `commit_count / file_age_days`.                                   |

## Label rule

`real_defect = 1` if and only if the file appears in the diff of the developer
fix commit for the corresponding defect event; otherwise 0. Defects4J labels
come from the framework's `bug.info`; BugsInPy labels come from the
`bug_patch.txt` metadata attached to each bug directory.

## Provenance

- **Defects4J v2.0.1**: <https://github.com/rjust/defects4j> (commit pin recorded
  in `docs/SETUP.md`).
- **BugsInPy**: <https://github.com/soarsmu/BugsInPy> (commit pin recorded in
  `docs/SETUP.md`).

The corpus was assembled by `scripts/build_real_events.py`. See
`docs/SCHEMA.md` for the exact feature list consumed by the fusion methods.
