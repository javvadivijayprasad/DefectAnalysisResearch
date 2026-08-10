#!/usr/bin/env python3
"""
run_real_experiment.py — Score the four attribution methods on real defects.

Loads ~/paperF/datasets/real_events.parquet (produced by build_real_events.py).
Retrains pre_only using leave-one-project-out (LOPO) cross-validation so the
score for any given event never comes from a model that saw that project.
Runs fail_only, fused_rule, and fused_ml (trained on the same LOPO split).

Metrics per method:
    precision@1, precision@3, recall@5, MRR, ECE (10-bin), triage-mean-seconds.

Outputs:
    ~/paperF/results/summary_real.json
    ~/paperF/results/per_event_metrics_real.csv
    ~/paperF/results/per_row_scores_real.csv
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

# --------------------------------------------------------------------------
# Same 7 features as run_experiment_v2.py
# --------------------------------------------------------------------------
FEATURES = ["commit_count", "unique_developers", "lines_added",
            "lines_deleted", "code_churn", "file_age_days",
            "commit_frequency"]

FAILURE_FEATURES = ["exception_idx", "http_status",
                    "app_code_changed", "validator_changed",
                    "schema_changed", "fixture_changed",
                    "config_changed", "locator_healed",
                    "historical_flake_rate"]

FUSED_FEATURES = FEATURES + FAILURE_FEATURES


# --------------------------------------------------------------------------
# Scoring methods
# --------------------------------------------------------------------------

def score_pre_only(test_df: pd.DataFrame, train_df: pd.DataFrame) -> np.ndarray:
    """Gradient boosting on the 7 pre-execution features, trained on
    train_df (which excludes the test project)."""
    Xtr = train_df[FEATURES].values.astype(float)
    ytr = train_df["real_defect"].values.astype(int)
    Xte = test_df[FEATURES].values.astype(float)

    scaler = StandardScaler()
    Xtr_s = scaler.fit_transform(Xtr)
    Xte_s = scaler.transform(Xte)

    model = GradientBoostingClassifier(
        n_estimators=100, max_depth=3, random_state=42)
    model.fit(Xtr_s, ytr)
    return model.predict_proba(Xte_s)[:, 1]


def score_fail_only(test_df: pd.DataFrame) -> np.ndarray:
    """Flat unit prior --- every implicated file equally likely."""
    return np.ones(len(test_df), dtype=float)


def score_fused_rule(test_df: pd.DataFrame,
                     pre_score: np.ndarray) -> np.ndarray:
    """Rule-cascade fusion: shrink for flake, boost for app/validator/schema."""
    flake_pen = np.maximum(0.0, test_df["historical_flake_rate"].values - 0.10) * 0.5
    diff_boost = np.zeros(len(test_df))
    diff_boost += 0.08 * test_df["app_code_changed"].values
    diff_boost += 0.05 * test_df["validator_changed"].values
    diff_boost += 0.03 * test_df["schema_changed"].values
    diff_boost -= 0.05 * test_df["fixture_changed"].values
    return np.clip(pre_score + diff_boost - flake_pen, 0.0, 1.0)


def score_fused_ml(test_df: pd.DataFrame,
                   train_df: pd.DataFrame,
                   pre_train: np.ndarray) -> np.ndarray:
    """Gradient boosting on 7 pre-features + 9 failure features + pre_score."""
    Xtr = np.column_stack([
        train_df[FUSED_FEATURES].values.astype(float),
        pre_train.reshape(-1, 1),
    ])
    ytr = train_df["real_defect"].values.astype(int)

    scaler = StandardScaler()
    Xtr_s = scaler.fit_transform(Xtr)

    model = GradientBoostingClassifier(
        n_estimators=150, max_depth=3, random_state=42)
    model.fit(Xtr_s, ytr)

    # Also need pre_score on test -- pass it in via the caller
    pre_test = score_pre_only(test_df, train_df)
    Xte = np.column_stack([
        test_df[FUSED_FEATURES].values.astype(float),
        pre_test.reshape(-1, 1),
    ])
    Xte_s = scaler.transform(Xte)
    return model.predict_proba(Xte_s)[:, 1]


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def evaluate_per_event(events: pd.DataFrame, scores: np.ndarray,
                       triage_seconds_per_file: float = 3.0,
                       tiebreak_seed: int = 42) -> pd.DataFrame:
    """Compute per-event ranking metrics.

    NOTE: tied scores are broken RANDOMLY (per-event deterministic seed) rather
    than by input order. Otherwise fail_only trivially gets perfect ranking
    because build_real_events.py emits fix files before distractors."""
    ev = events.copy()
    ev["score"] = scores
    # Deterministic per-row jitter -- breaks ties in a reproducible, fair way
    rng = np.random.default_rng(tiebreak_seed)
    ev["_tiebreak"] = rng.random(len(ev))
    rows = []
    for eid, grp in ev.groupby("event_id", sort=False):
        n = len(grp)
        # Rank files by (score DESC, tiebreak ASC) -- ties resolved randomly
        grp_sorted = grp.sort_values(
            ["score", "_tiebreak"], ascending=[False, True], kind="stable")
        labels = grp_sorted["real_defect"].values
        # precision@k -- fraction of top-k that are real defects
        p1 = float(labels[:1].mean()) if n >= 1 else 0.0
        p3 = float(labels[:3].mean()) if n >= 3 else float(labels.mean())
        # recall@5 -- fraction of true defects retrieved in top-5
        total_pos = int(labels.sum())
        r5 = (float(labels[:5].sum() / total_pos)
              if total_pos > 0 else 0.0)
        # MRR -- reciprocal rank of first real defect
        first_pos_rank = 0
        for i, v in enumerate(labels, start=1):
            if v == 1:
                first_pos_rank = i
                break
        mrr = 1.0 / first_pos_rank if first_pos_rank else 0.0
        # Triage time -- seconds until the first real defect is inspected
        triage = first_pos_rank * triage_seconds_per_file if first_pos_rank else n * triage_seconds_per_file
        rows.append(dict(event_id=eid, n_files=n, n_defects=total_pos,
                         p1=p1, p3=p3, r5=r5, mrr=mrr, triage_s=triage))
    return pd.DataFrame(rows)


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray,
                                n_bins: int = 10) -> float:
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob)
    if len(y_true) == 0:
        return 0.0
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (y_prob >= bins[i]) & (y_prob < bins[i + 1])
        if i == n_bins - 1:
            mask = (y_prob >= bins[i]) & (y_prob <= bins[i + 1])
        if mask.sum() == 0:
            continue
        acc = y_true[mask].mean()
        conf = y_prob[mask].mean()
        ece += (mask.sum() / len(y_true)) * abs(acc - conf)
    return float(ece)


def summarize(name: str, per_event: pd.DataFrame,
              y_true: np.ndarray, y_prob: np.ndarray) -> dict:
    return dict(
        method=name,
        n_events=int(len(per_event)),
        n_rows=int(len(y_true)),
        p1_mean=round(float(per_event["p1"].mean()), 4),
        p3_mean=round(float(per_event["p3"].mean()), 4),
        r5_mean=round(float(per_event["r5"].mean()), 4),
        mrr_mean=round(float(per_event["mrr"].mean()), 4),
        triage_s_mean=round(float(per_event["triage_s"].mean()), 2),
        ece_10bin=round(expected_calibration_error(y_true, y_prob), 4),
    )


# --------------------------------------------------------------------------
# LOPO orchestrator
# --------------------------------------------------------------------------

def leave_one_project_out(events: pd.DataFrame) -> Dict[str, np.ndarray]:
    """For each row, produce a score under each of the 4 methods.
    Uses LOPO cross-validation for pre_only and fused_ml."""
    n = len(events)
    pre_scores = np.zeros(n)
    fail_scores = np.ones(n)
    rule_scores = np.zeros(n)
    ml_scores = np.zeros(n)

    projects = sorted(events["repo"].unique())
    print(f"Cross-validating across {len(projects)} projects...")

    for i, held_out in enumerate(projects, 1):
        test_mask = events["repo"] == held_out
        train_mask = ~test_mask
        train_df = events[train_mask].reset_index(drop=True)
        test_df = events[test_mask].reset_index(drop=True)
        test_idx = np.where(test_mask.values)[0]

        if train_df["real_defect"].sum() < 5 or train_df["real_defect"].sum() > len(train_df) - 5:
            # skewed training set -- fall back to constant score
            pre = np.full(len(test_df), 0.5)
            ml = np.full(len(test_df), 0.5)
        else:
            pre = score_pre_only(test_df, train_df)
            pre_train = score_pre_only(train_df, train_df)  # in-sample for ml fusion
            ml = score_fused_ml(test_df, train_df, pre_train)

        rule = score_fused_rule(test_df, pre)

        pre_scores[test_idx] = pre
        rule_scores[test_idx] = rule
        ml_scores[test_idx] = ml
        print(f"  [{i:2d}/{len(projects)}] {held_out}: {len(test_df)} rows, "
              f"pre_mean={pre.mean():.3f} ml_mean={ml.mean():.3f}")

    return dict(pre_only=pre_scores, fail_only=fail_scores,
                fused_rule=rule_scores, fused_ml=ml_scores)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=os.path.expanduser("~/paperF/datasets/real_events.parquet"))
    ap.add_argument("--out-dir", default=os.path.expanduser("~/paperF/results"))
    args = ap.parse_args()

    events = pd.read_parquet(args.events)
    print(f"Loaded {len(events)} rows / {events['event_id'].nunique()} events "
          f"/ {events['repo'].nunique()} repos")
    print(f"Real-defect fraction: {events['real_defect'].mean():.3f}")

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    print(f"\n[{time.strftime('%H:%M:%S')}] Scoring all 4 methods (LOPO cross-validation)")
    scores = leave_one_project_out(events)

    # Save per-row scores
    scored = events.copy()
    for name, sc in scores.items():
        scored[f"score_{name}"] = sc
    scored.to_csv(f"{args.out_dir}/per_row_scores_real.csv", index=False)

    # Evaluate + summarize each method
    y_true = events["real_defect"].values
    summary = []
    per_event_all = {}
    for name, sc in scores.items():
        pe = evaluate_per_event(events, sc)
        pe["method"] = name
        per_event_all[name] = pe
        summary.append(summarize(name, pe, y_true, sc))

    # Save per-event metrics (concat all methods)
    pe_all = pd.concat(list(per_event_all.values()), ignore_index=True)
    pe_all.to_csv(f"{args.out_dir}/per_event_metrics_real.csv", index=False)

    # Aggregate summary
    with open(f"{args.out_dir}/summary_real.json", "w") as f:
        json.dump(dict(
            corpus=dict(
                total_rows=int(len(events)),
                total_events=int(events["event_id"].nunique()),
                total_repos=int(events["repo"].nunique()),
                real_defect_fraction=round(float(events["real_defect"].mean()), 4),
            ),
            methods=summary,
        ), f, indent=2)

    print(f"\n=== Headline results ===")
    print(f"{'method':<12} {'p@1':>7} {'p@3':>7} {'r@5':>7} {'MRR':>7} "
          f"{'triage':>7} {'ECE':>7}")
    for s in summary:
        print(f"{s['method']:<12} {s['p1_mean']:>7.4f} {s['p3_mean']:>7.4f} "
              f"{s['r5_mean']:>7.4f} {s['mrr_mean']:>7.4f} "
              f"{s['triage_s_mean']:>7.2f} {s['ece_10bin']:>7.4f}")

    print(f"\nWrote: {args.out_dir}/summary_real.json")
    print(f"       {args.out_dir}/per_event_metrics_real.csv")
    print(f"       {args.out_dir}/per_row_scores_real.csv")


if __name__ == "__main__":
    main()
