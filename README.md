# Trust, Augment, or Replace? Cross-project defect attribution on 1,267 real defects — reproducibility bundle v4.0.0

## Title

Trust, Augment, or Replace? What a Cross-Project Defect Predictor Is Worth on 1,267 Real Defects from Defects4J and BugsInPy.
Vijay Prasad Javvadi, Independent Researcher, Plainsboro, NJ, USA. ORCID 0009-0004-1192-6906. Submitted to PeerJ Computer Science (CS-2026:09:149817), AI Application article type.

## Description

This bundle contains everything needed to rebuild the evaluation corpus, rerun the leave-one-project-out experiment, rerun the two LLM baselines, and regenerate every number, table and figure in the manuscript. The study asks whether a file-level defect predictor trained on other projects can be trusted (calibration), whether adding failure-time signals helps (fusion), and whether a prompted frontier LLM given the same information replaces it. Version 4.0.0 is a corrected corpus construction; see CHANGELOG.md for what changed from 3.0.0 and why the earlier numbers are superseded.

## Dataset information

The corpus is derived from two public real-defect benchmarks, which are not redistributed here:

- Defects4J v2.0.1, https://github.com/rjust/defects4j (tag `v2.0.1`), licence as stated in that repository. Pre-fix and fix revisions come from each project's `active-bugs.csv` (`revision.id.buggy`, `revision.id.fixed`).
- BugsInPy, https://github.com/soarsmu/BugsInPy (default branch, snapshot of 2 October 2026), MIT licence. Pre-fix and fix revisions and the upstream repository URL come from each bug's `bug.info` and `project.info`.

Derived data in this bundle:

- `datasets/real_events_v4.parquet` — 6,716 rows (one per candidate file), 1,267 events, 33 projects (774 Defects4J events in 16 projects, 493 BugsInPy events in 17). Columns: `event_id`, `repo`, `file_name`, `real_defect` (label), nine failure-side columns (`exception_type`, `exception_idx`, `http_status`, `locator_healed`, `historical_flake_rate`, `app_code_changed`, `validator_changed`, `schema_changed`, `fixture_changed`, `config_changed`), and seven process-metric features (`commit_count`, `unique_developers`, `lines_added`, `lines_deleted`, `code_churn`, `file_age_days`, `commit_frequency`) computed at the pre-fix revision.
- `datasets/real_events_v4.parquet.build_log.csv` — one row per bug attempted (1,355), with status and skip reason (88 skipped).
- `results_v4/` — `per_row_scores_real.csv` (scores of the four internal methods per row), `per_event_metrics_real.csv`, `summary_real.json`, `distractor_sensitivity.csv`, `paper_numbers_v4.json` (every manuscript number), LLM outputs (`llm_baseline/<model>/runs/*.json`, one per event with prompt and raw response; `*__summary.json`, `*__per_event_metrics.csv`, `*__per_project.csv`).
- `figures_v4/` — the four manuscript figures (PDF and PNG).

## Code information

All scripts are Python 3 and live in `scripts/`:

- `build_real_events_v4.py` — corpus construction (checkout of the pre-fix revision, fix-file extraction, same-directory sibling distractors, git process metrics; writes the parquet and the build log).
- `run_real_experiment.py` — leave-one-project-out experiment for the four internal methods (cross-project predictor, flat prior, rule fusion, learned fusion), metric implementation (Precision@k, Recall@5, MRR, triage seconds, 10-bin ECE; random tie-break, seed 42).
- `llm_baseline.py` — the two LLM attribution baselines under information parity (one prompt per event, temperature 0, strict JSON, deterministic per-event candidate shuffle).
- `distractor_sensitivity.py` — rescoring at candidate-set sizes k ∈ {2, 3, 4, all}.
- `analysis_v4.py` — computes every number in the manuscript from the result files and writes `results_v4/paper_numbers_v4.json` (pooled and per-corpus metrics, paired event-level bootstrap with 10,000 resamples, per-project wins/ties/losses, reliability bins and threshold precision, the Lang/Math/Time split).
- `make_figures_v4.py` — the four figures from the JSON and CSVs.

## Usage

```bash
pip install -r requirements.txt
# 1. corpus (needs Defects4J and BugsInPy installed; ~3 h, ~10 GB of clones)
python scripts/build_real_events_v4.py --out datasets/real_events_v4.parquet
# 2. LOPO experiment and sensitivity (no API, a few minutes)
python scripts/run_real_experiment.py --events datasets/real_events_v4.parquet --out-dir results_v4
python scripts/distractor_sensitivity.py
# 3. LLM baselines (keys in the environment only; Claude run US$7.55; GPT-4o-mini run incurred no charge)
export ANTHROPIC_API_KEY=...   # never into a file
python scripts/llm_baseline.py --events datasets/real_events_v4.parquet --backend anthropic --model claude-sonnet-4-6 --out-root results_v4/llm_baseline
export OPENAI_API_KEY=...
python scripts/llm_baseline.py --events datasets/real_events_v4.parquet --backend openai --model gpt-4o-mini --out-root results_v4/llm_baseline
# 4. numbers and figures
python scripts/analysis_v4.py
python scripts/make_figures_v4.py
```

Steps 2 and 4 reproduce every manuscript number from the shipped parquet without rebuilding the corpus or calling any API; the shipped LLM run logs are what step 4 reads for the LLM rows.

## Requirements

Corpus build: Linux (tested on WSL2 Ubuntu 22.04 on a Windows 11 laptop, Intel Core i7-12700H, 40 GB RAM), git, OpenJDK 11 and the Defects4J framework on PATH, a BugsInPy checkout, Python 3.10 or later. Experiment and analysis: Python 3.10 or later with pandas ≥ 2.0, numpy, scikit-learn ≥ 1.4, pyarrow, matplotlib (`requirements.txt`). No GPU. LLM baselines: network access to the Anthropic and OpenAI HTTP APIs and the corresponding keys in environment variables.

## Methodology

Each bug becomes one failure event. Its candidate set is the non-test source files changed by the fix (at most five) plus source files from the same directories at the pre-fix revision, drawn with a per-bug MD5 seed so that the set has between 3 and 8 files; bugs with no sibling, no non-test source fix file, or a failed checkout are skipped and logged. Seven process metrics are computed per candidate from `git log --follow` in the ancestry of the pre-fix revision, identically for Java and Python. Four internal methods are evaluated under leave-one-project-out over 33 projects (train on 32, score the held-out one; no post-hoc recalibration). Two LLMs are prompted once per event with exactly the fused model's inputs (project name, event-level columns, per-candidate path and seven metrics) and scored by the same code. Metrics are Precision@1/@3, Recall@5, MRR, triage seconds and 10-bin expected calibration error; uncertainty is a paired event-level bootstrap (10,000 resamples, seed 42). Full detail is in the manuscript, Section 2.

## Citations

If you use this bundle, cite the artifact (version 4.0.0 DOI 10.5281/zenodo.23111801; concept DOI 10.5281/zenodo.20723929) and the manuscript once published. Cite Defects4J (Just, Jalali and Ernst, ISSTA 2014) and BugsInPy (Widyasari et al., FSE 2020) for the underlying benchmarks. `CITATION.cff` carries the machine-readable form.

## Licence

Code: MIT. Derived data, results, run logs and figures: CC BY 4.0. Defects4J and BugsInPy remain under their own licences and are not included.
