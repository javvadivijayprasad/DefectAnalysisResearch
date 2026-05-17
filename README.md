# Paper 7 — Post-Execution Defect Attribution

Research repository for **"Post-Execution Defect Attribution: Fusing Test-Failure Signals with SHAP-Explained Repository Priors for Practitioner-Actionable Triage."**

Seventh paper in the AI-driven software quality engineering research series. Builds directly on Paper 4 (feature importance + SHAP integration) and forms the research foundation for `defect-attribution-service`.

## Research question

Given a test failure, which of the implicated files is a *real defect*, and which category of failure is it — real defect, validation failure, uncoordinated contract change, stale fixture, flake, environmental, or self-healed-hidden defect? Paper 4 proved repository features predict defect risk; this paper proves that fusing those features with post-execution failure signals collapses the false-positive rate and returns explanations developers can act on.

## Contributions

1. A **two-stage pipeline** (predict → confirm) in which the second stage conditions on observed failure signals rather than predicting in isolation.
2. A **failure-category taxonomy** (eight mutually exclusive categories) with a rule-cascade classifier that operates on exception type, HTTP status, schema/fixture/config diffs, historical flake rate, and the defect-probability prior.
3. **SHAP local attribution** per implicated file, producing per-prediction narratives (Paper 4 future-work item 4 operationalised).
4. A **governance-preserving feedback loop** (the `.pkl` matures with each user run without exfiltrating data) — the same pattern used by sibling services.
5. An evaluation against **SZZ-labeled ground truth** on five repositories (spring-boot, kafka, hadoop, elasticsearch, express) showing precision@1 improvements vs. pre-execution prediction and vs. failure-only triage.

## Directory layout

```
Defect analysis paper/
├── paper7_defect_attribution.tex      # canonical IEEE source
├── references.bib                     # bibliography (extends Paper 4)
├── compile_all.bat                    # Windows build
├── compile_all.sh                     # macOS / Linux build
├── datasets/                          # labeled SZZ + failure datasets (see datasets/README.md)
├── experiments/                       # experiment protocol docs + designs
├── scripts/
│   ├── build_dataset.py               # construct labeled dataset from repo history
│   ├── run_experiment.py              # run baselines + proposed method
│   ├── generate_figures.py            # figures referenced in the paper
│   └── generate_tables.py             # tables referenced in the paper
├── notebooks/                         # exploratory analysis
├── figures/                           # PNG outputs
├── tables/                            # CSV outputs → LaTeX tables
└── results/                           # per-run JSON outputs
```

## Reproducibility

The experiments consume the same five repositories used in Papers 1–6 and the same `defect_predictor.pkl` produced by Paper 4. No code under test is read at any point — all features derive from git history, test-reporter output, and schema/fixture diffs.

Build the paper:

```bash
pdflatex -interaction=nonstopmode paper7_defect_attribution.tex
bibtex    paper7_defect_attribution
pdflatex -interaction=nonstopmode paper7_defect_attribution.tex
pdflatex -interaction=nonstopmode paper7_defect_attribution.tex
```

Or run `compile_all.bat` (Windows) / `compile_all.sh` (macOS, Linux).

Run the experiment:

```bash
python scripts/build_dataset.py --repos spring-boot kafka hadoop elasticsearch express
python scripts/run_experiment.py --config experiments/paper7_default.yaml
python scripts/generate_figures.py
python scripts/generate_tables.py
```

## Paper 4 lineage

Paper 4 published global feature importance (commit count, churn, unique developers) at F1 ≈ 0.63 pre-execution. This paper preserves that model unchanged, adds a thin *local* SHAP layer on top, and evaluates a second-stage classifier that fuses its output with post-execution signals. The Paper 4 `.pkl` is loaded verbatim; no retraining is required to reproduce Paper 7's headline results.

## Service counterpart

The service implementation lives at `../defect-attribution-service/`. The paper documents the experimental justification; the service delivers the capability to practitioners.

Feedback from the service (`/report-outcome` → JSONL) can be folded back into the training set via `../defect-attribution-service/scripts/retrain.py`, producing a matured `.pkl` that the service picks up on restart. Longitudinal evaluation of that maturation is the subject of a planned follow-up (Paper 8).
