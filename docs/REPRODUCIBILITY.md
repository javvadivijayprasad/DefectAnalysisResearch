# Reproducibility guide

This document walks you from a fresh WSL2 Ubuntu install to the exact
figures and JSON summary that appear in Paper F.

## Prerequisites

- **OS**: WSL2 Ubuntu 22.04 LTS (native Linux also fine). Native Windows
  works with the workarounds in `SETUP.md`, but WSL2 is strongly preferred.
- **JDK 11** (Adoptium Temurin recommended).
- **Python 3.10 or 3.11** with `venv`.
- **Perl 5.30+** with `cpanm` (for Defects4J `init.sh`).
- **Git 2.30+**.
- **~10 GB free disk**.

## Step 1 — Install Defects4J + BugsInPy

Follow [`SETUP.md`](SETUP.md). Verify both installs before proceeding:

```bash
defects4j info -p Lang        # prints project metadata
bugsinpy-info projects        # prints 17 subjects
```

## Step 2 — Create a Python environment for the bundle

```bash
cd zenodo_bundle_v1.0.0
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Step 3 — Build the event corpus (~90 min from scratch)

```bash
mkdir -p ~/paperF/datasets
python3 scripts/build_real_events.py
```

Expected terminal output (last lines):

```
Wrote ~/paperF/datasets/real_events.parquet
Total events : 1323
Total rows   : 6988
Total repos  : 33
Real-defect fraction: 0.231
```

Copy the parquet files into the bundle's `datasets/` directory (see
`FINALIZE_BUNDLE.md` step 1). Downstream steps read from there.

**Shortcut**: if `datasets/real_events.parquet` already ships with this
bundle (as it should after the author's finalize step), skip to Step 4.

## Step 4 — Run the LOPO experiment (~5 min)

```bash
python3 scripts/run_real_experiment.py
```

Writes `results/summary_real.json`, `results/per_event_metrics_real.csv`,
and `results/per_row_scores_real.csv`.

### Expected numbers (verification checklist)

| Field                                | Expected value              | Tolerance          |
| ------------------------------------ | --------------------------- | ------------------ |
| `corpus.total_events`                | 1323                        | exact              |
| `corpus.total_rows`                  | 6988                        | exact              |
| `corpus.total_repos`                 | 33                          | exact              |
| `corpus.real_defect_fraction`        | 0.2311                      | +/- 0.001          |
| `pre_only.p1_mean`                   | 0.7770                      | +/- 0.005          |
| `pre_only.ece_10bin`                 | 0.0209                      | +/- 0.005          |
| `fail_only.p1_mean`                  | 0.2494                      | +/- 0.005          |
| `fused_rule.p1_mean`                 | 0.7800                      | +/- 0.005          |
| `fused_rule.ece_10bin`               | 0.0626                      | +/- 0.005          |
| `fused_ml.p1_mean`                   | 0.7475                      | +/- 0.010          |
| `fused_ml.ece_10bin`                 | 0.0326                      | +/- 0.005          |

`fused_ml` has a small stochastic component (LOPO fold ordering, sklearn
solver tie-breaks) — the wider tolerance covers this. All other numbers
should reproduce exactly.

## Step 5 — Generate figures (~30 s)

```bash
python3 scripts/generate_real_figures.py
```

Writes four PNGs into `results/figures/` (also mirrored in `paper/figures/`):

1. `fig_headline_bars.png` — p@1 by method.
2. `fig_ece_bars.png` — ECE by method.
3. `fig_reliability.png` — reliability diagrams for the three ranking methods.
4. `fig_per_repo_precision.png` — per-repo p@1 heat/dot plot.

## Reproduction budgets

| Path                                                            | Wall-clock |
| --------------------------------------------------------------- | ---------- |
| Cached-artifacts-only verification (Steps 4-5, parquet shipped) | **~15 min** |
| Full-from-scratch reproduction (Steps 1-5)                      | **~2 hr**   |

## Compiling the manuscript

```bash
cd paper
pdflatex paperF_JSS.tex
bibtex   paperF_JSS
pdflatex paperF_JSS.tex
pdflatex paperF_JSS.tex
```

Requires `elsarticle` document class (part of a full TeX Live install).

## Troubleshooting

- **`defects4j: command not found`** — you did not `source ~/.bashrc` after
  the install; open a fresh shell.
- **`ModuleNotFoundError: pyarrow`** — the venv is not activated, or you
  installed globally. Re-activate and reinstall.
- **`fused_ml` p@1 is 0.0** — sklearn version mismatch; pin `>=1.4` per
  `requirements.txt`.
- **BugsInPy pandas bug fails to build wheels** — install pyenv and pin the
  interpreter version listed in that bug's `bug.info`.
