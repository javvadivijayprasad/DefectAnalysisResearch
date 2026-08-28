# Paper F Reproducibility Bundle v2.0.0

**Post-Execution Defect Attribution on Real-World Defects: An Empirical Comparison of Four Methods on Defects4J and BugsInPy**

This archive is the reproducibility bundle for the companion paper (submitted
to the *Journal of Systems and Software*, Elsevier). It ships every artifact
needed to reproduce the empirical results: the 1,323-defect event corpus
assembled from Defects4J v2.0.1 and BugsInPy, the leave-one-project-out (LOPO)
experiment harness, the four attribution methods evaluated (`pre_only`,
`fail_only`, `fused_rule`, `fused_ml`), the generated figures, and the compiled
manuscript.

**This is v2.0.0**, a major real-data rebuild of the v1.0.0 synthetic-only
release. See [`CHANGELOG.md`](CHANGELOG.md) for a full diff.

## Citation

If you use this bundle please cite both the archived artifact and the paper:

```bibtex
@dataset{javvadi2026paperF_bundle,
  author       = {Javvadi, Vijay Prasad},
  title        = {{Post-Execution Defect Attribution on Real-World
                   Defects — Reproducibility Bundle v2.0.0}},
  year         = {2026},
  publisher    = {Zenodo},
  version      = {v2.0.0},
  doi          = {[ZENODO-DOI-HERE]},
  url          = {https://doi.org/[ZENODO-DOI-HERE]}
}

@article{javvadi2026paperF,
  author  = {Javvadi, Vijay Prasad},
  title   = {Post-Execution Defect Attribution on Real-World Defects: An
             Empirical Comparison of Four Methods on Defects4J and BugsInPy},
  journal = {Journal of Systems and Software},
  year    = {2026},
  doi     = {[PAPER-DOI-HERE]}
}
```

The concept DOI (all versions) is `10.5281/zenodo.20723929`; the version DOI
for v2.0.0 is assigned upon publication and replaces `[ZENODO-DOI-HERE]` above.

## Directory tree

```
zenodo_bundle_v2.0.0/
├── README.md                    (this file)
├── LICENSE                      (CC-BY-4.0)
├── CITATION.cff                 (Zenodo citation metadata)
├── CHANGELOG.md
├── requirements.txt
├── paper/
│   ├── paperF_JSS.pdf
│   ├── paperF_JSS.tex
│   ├── paperF_references.bib
│   ├── cover_letter_JSS.pdf
│   └── highlights.txt
├── scripts/
│   ├── build_real_events.py
│   ├── run_real_experiment.py
│   └── generate_real_figures.py
├── datasets/
│   ├── README.md                (schema documentation)
│   ├── real_events.parquet      (1,323 events, 6,988 rows)
│   ├── real_events_d4j.parquet  (824 Defects4J events)
│   ├── real_events_bip.parquet  (499 BugsInPy events)
│   └── real_events_smoke.parquet (smoke-test sample)
├── results/
│   ├── summary_real.json
│   ├── per_event_metrics_real.csv
│   ├── per_row_scores_real.csv
│   └── figures/                 (fig_headline_bars, fig_ece_bars,
│                                 fig_reliability, fig_per_repo_precision)
└── docs/
    ├── REPRODUCIBILITY.md
    ├── SETUP.md
    ├── SCHEMA.md
    ├── QC_JSS_AUDIT.md
    └── FINALIZE_BUNDLE.md
```

## Quick reproduction

```bash
git clone https://github.com/javvadivijayprasad/DefectAnalysisReserch.git
cd DefectAnalysisReserch
git checkout paperF-jss-v1.0
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/run_real_experiment.py    # ~5 min with cached parquet
python3 scripts/generate_real_figures.py
```

This reproduces the four figures and `results/summary_real.json` from the
cached parquet corpus in ~15 minutes. To re-build the corpus from source
(Defects4J v2.0.1 + BugsInPy) takes ~2 hours.

## Detailed reproduction

See [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) for step-by-step
instructions, expected checksum-style outputs, and the fresh-install path.

## Headline results (real data, 1,323 events, LOPO CV)

| Method       | p@1    | p@3    | r@5    | MRR    | ECE (10-bin) |
|--------------|--------|--------|--------|--------|--------------|
| pre_only     | 0.7770 | 0.3627 | 0.9696 | 0.8556 | 0.0209       |
| fail_only    | 0.2494 | 0.2654 | 0.8872 | 0.4978 | 0.7689       |
| fused_rule   | 0.7800 | 0.3624 | 0.9691 | 0.8571 | 0.0626       |
| fused_ml     | 0.7475 | —      | —      | —      | 0.0330       |

**Ablation**: fused_ml retrained on pre-execution features only recovers
p@1 = 0.7627 (≈half the fused_ml deficit), confirming that the failure-side
features actively hurt on real data.

## License

Creative Commons Attribution 4.0 International (CC-BY-4.0) — see
[`LICENSE`](LICENSE). Same license as v1.0.0.

## Contact

Vijay Prasad Javvadi
Independent Researcher, Plainsboro, NJ, USA
ORCID: <https://orcid.org/0009-0004-1192-6906>
Email: <vijay@vijayjavvadiresearch.ai>
