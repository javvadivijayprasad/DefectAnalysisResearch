#!/usr/bin/env python3
"""
distractor_sensitivity.py — Sensitivity of calibration (and P@1) to the
number of distractors in each event's candidate set.

Motivation: the paper's headline ECE numbers are measured at one designed
base rate (~5.28 candidates/event -> row-level defect fraction ~0.23).
This script recomputes 10-bin ECE and Precision@1 at smaller candidate-set
sizes k in {2, 3, 4, all}: for each event we ALWAYS retain every true fix
file and add a deterministic subsample of (k-1) distractors, seeded by the
event id (md5), so the subsets are reproducible and nested across k.
Events with fewer than (k-1) available distractors are skipped for that k.

Methods covered:
  * pre_only, fused_rule, fused_ml — per-row LOPO probabilities read from
    results/per_row_scores_real.csv (produced by run_real_experiment.py).
  * llm_sonnet, llm_gpt4omini — per-row confidences read from the per-event
    run JSONs in results/llm_baseline/<model>/runs/. As in llm_baseline.py,
    ECE uses the raw stated confidence and ranking uses
    confidence - RANK_EPS * rankpos (the model's explicit ranking breaks
    ties among equal confidences).

Scoring uses the IDENTICAL implementation as the paper:
evaluate_per_event() and expected_calibration_error() are imported from
scripts/run_real_experiment.py.

Outputs:
  results/distractor_sensitivity.csv
  a printed table on stdout
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

from run_real_experiment import (  # noqa: E402  (paper's own scoring impl)
    evaluate_per_event,
    expected_calibration_error,
)

RANK_EPS = 1e-6  # identical to llm_baseline.py

LLM_MODELS = {
    "llm_sonnet": "claude-sonnet-4-6",
    "llm_gpt4omini": "gpt-4o-mini",
}
INTERNAL_METHODS = ["pre_only", "fused_rule", "fused_ml"]
K_VALUES = [2, 3, 4, "all"]


def load_rows() -> pd.DataFrame:
    p = REPO / "results" / "per_row_scores_real.csv"
    df = pd.read_csv(p)
    # Preserve corpus row order — LLM confidence_by_corpus_row aligns to it.
    df = df.reset_index(drop=True)
    return df


def attach_llm_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Add score_<llm>_raw (for ECE) and score_<llm>_adj (for ranking)."""
    for method, model in LLM_MODELS.items():
        run_dir = REPO / "results" / "llm_baseline" / model / "runs"
        raw = np.full(len(df), np.nan)
        adj = np.full(len(df), np.nan)
        n_loaded = 0
        for eid, grp in df.groupby("event_id", sort=False):
            p = run_dir / f"{eid}.json"
            if not p.exists():
                continue
            rec = json.loads(p.read_text(encoding="utf-8"))
            cbr = rec["confidence_by_corpus_row"]
            rbr = rec["rankpos_by_corpus_row"]
            if len(cbr) != len(grp):
                print(f"[warn] {method} {eid}: candidate-count mismatch, skipped")
                continue
            idx = grp.index.values
            raw[idx] = np.array(cbr, dtype=float)
            adj[idx] = np.array(cbr, dtype=float) - RANK_EPS * np.array(
                rbr, dtype=float)
            n_loaded += 1
        df[f"score_{method}_raw"] = raw
        df[f"score_{method}_adj"] = adj
        print(f"[load] {method}: run files for {n_loaded} events")
    return df


def subsample_event(grp: pd.DataFrame, k) -> np.ndarray | None:
    """Return the retained row indices for this event at candidate size k.

    Fix files are always retained; (k-1) distractors are drawn by a
    deterministic per-event shuffle (md5 of event id). Returns None if the
    event has fewer than (k-1) distractors.
    """
    if k == "all":
        return grp.index.values
    fix_idx = grp.index[grp["real_defect"] == 1].values
    dis_idx = grp.index[grp["real_defect"] == 0].values
    need = k - 1
    if len(dis_idx) < need:
        return None
    eid = grp["event_id"].iloc[0]
    seed = int(hashlib.md5(eid.encode()).hexdigest(), 16) % (2 ** 32)
    rng = random.Random(seed)
    order = sorted(dis_idx.tolist())
    rng.shuffle(order)
    keep = np.concatenate([fix_idx, np.array(order[:need], dtype=int)])
    return np.sort(keep)


def main() -> None:
    df = load_rows()
    print(f"[load] {len(df)} rows / {df['event_id'].nunique()} events")
    df = attach_llm_scores(df)

    records = []
    for k in K_VALUES:
        keep_idx = []
        for _, grp in df.groupby("event_id", sort=False):
            idx = subsample_event(grp, k)
            if idx is not None:
                keep_idx.append(idx)
        keep = np.concatenate(keep_idx)
        sub = df.loc[keep].reset_index(drop=True)
        n_events = sub["event_id"].nunique()
        base_rate = float(sub["real_defect"].mean())
        y_true = sub["real_defect"].values

        for method in INTERNAL_METHODS + list(LLM_MODELS):
            if method in INTERNAL_METHODS:
                ece_scores = sub[f"score_{method}"].values
                rank_scores = ece_scores
            else:
                ece_scores = sub[f"score_{method}_raw"].values
                rank_scores = sub[f"score_{method}_adj"].values
                if np.isnan(ece_scores).any():
                    mask_ev = sub.loc[~np.isnan(ece_scores), "event_id"]
                    print(f"[warn] {method}: NaN scores at k={k}")
            per_event = evaluate_per_event(sub, rank_scores)
            ece = expected_calibration_error(y_true, ece_scores)
            records.append(dict(
                k=str(k),
                method=method,
                n_events=int(n_events),
                n_rows=int(len(sub)),
                base_rate=round(base_rate, 4),
                ece_10bin=round(ece, 4),
                p1_mean=round(float(per_event["p1"].mean()), 4),
            ))

    out = pd.DataFrame(records)
    out_path = REPO / "results" / "distractor_sensitivity.csv"
    out.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}\n")

    print(f"{'k':>4} {'method':<14} {'events':>7} {'rows':>6} "
          f"{'base':>6} {'ECE':>7} {'p@1':>7}")
    for r in records:
        print(f"{r['k']:>4} {r['method']:<14} {r['n_events']:>7} "
              f"{r['n_rows']:>6} {r['base_rate']:>6.3f} "
              f"{r['ece_10bin']:>7.4f} {r['p1_mean']:>7.4f}")


if __name__ == "__main__":
    main()
