#!/usr/bin/env python3
"""
generate_real_figures.py — 4 publication figures from real-data results.

Reads:
  ~/paperF/results/summary_real.json
  ~/paperF/results/per_event_metrics_real.csv
  ~/paperF/results/per_row_scores_real.csv

Writes to ~/paperF/results/figures/:
  fig_headline_bars.png       — grouped bar chart of p@1/p@3/r@5/MRR by method
  fig_ece_bars.png            — ECE per method (headline calibration finding)
  fig_reliability.png         — reliability diagrams per method (calibration)
  fig_per_repo_precision.png  — boxplot of p@1 per repo, per method
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Colorblind-safe palette (Okabe-Ito)
PALETTE = {
    "pre_only":   "#0072B2",   # blue
    "fail_only":  "#D55E00",   # orange (weak baseline)
    "fused_rule": "#009E73",   # green
    "fused_ml":   "#CC79A7",   # magenta
}
METHOD_ORDER = ["pre_only", "fail_only", "fused_rule", "fused_ml"]
METHOD_LABEL = {
    "pre_only":   "pre_only",
    "fail_only":  "fail_only",
    "fused_rule": "fused_rule",
    "fused_ml":   "fused_ml",
}


def load_data(results_dir: Path):
    with open(results_dir / "summary_real.json") as f:
        summary = json.load(f)
    per_event = pd.read_csv(results_dir / "per_event_metrics_real.csv")
    per_row = pd.read_csv(results_dir / "per_row_scores_real.csv")
    return summary, per_event, per_row


def fig_headline_bars(summary, out: Path):
    methods = [m["method"] for m in summary["methods"]]
    p1 = [m["p1_mean"] for m in summary["methods"]]
    p3 = [m["p3_mean"] for m in summary["methods"]]
    r5 = [m["r5_mean"] for m in summary["methods"]]
    mrr = [m["mrr_mean"] for m in summary["methods"]]

    x = np.arange(len(methods))
    w = 0.20
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - 1.5 * w, p1, w, label="Precision@1", color="#0072B2")
    ax.bar(x - 0.5 * w, p3, w, label="Precision@3", color="#009E73")
    ax.bar(x + 0.5 * w, r5, w, label="Recall@5", color="#F0E442")
    ax.bar(x + 1.5 * w, mrr, w, label="MRR", color="#CC79A7")
    ax.set_xticks(x)
    ax.set_xticklabels(methods)
    ax.set_ylabel("Score")
    ax.set_ylim(0, 1.05)
    ax.set_title(
        f"Ranking metrics on {summary['corpus']['total_events']:,} real defects "
        f"(Defects4J + BugsInPy, LOPO CV)",
        fontsize=11,
    )
    ax.legend(loc="upper right", ncol=2)
    ax.grid(axis="y", alpha=0.3)
    # Annotate bar heights
    for xi, vals in zip(x, zip(p1, p3, r5, mrr)):
        offsets = [-1.5 * w, -0.5 * w, 0.5 * w, 1.5 * w]
        for off, v in zip(offsets, vals):
            ax.text(xi + off, v + 0.01, f"{v:.2f}",
                    ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    fig.savefig(out / "fig_headline_bars.png", dpi=180)
    plt.close(fig)
    print(f"Wrote {out}/fig_headline_bars.png")


def fig_ece_bars(summary, out: Path):
    methods = [m["method"] for m in summary["methods"]]
    ece = [m["ece_10bin"] for m in summary["methods"]]
    colors = [PALETTE.get(m, "#888") for m in methods]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(methods, ece, color=colors)
    ax.set_ylabel("Expected Calibration Error (10-bin)")
    ax.set_title(
        f"Calibration on {summary['corpus']['total_events']:,} real defects "
        "(lower is better)",
        fontsize=11,
    )
    ax.grid(axis="y", alpha=0.3)
    for bar, v in zip(bars, ece):
        ax.text(bar.get_x() + bar.get_width() / 2,
                v + 0.01, f"{v:.3f}",
                ha="center", va="bottom", fontsize=9)
    # Annotate the winning method
    best_idx = int(np.argmin(ece))
    ax.annotate(
        f"Best: {methods[best_idx]}  ECE = {ece[best_idx]:.3f}",
        xy=(best_idx, ece[best_idx]),
        xytext=(best_idx, max(ece) * 0.6),
        ha="center", fontsize=9,
        arrowprops=dict(arrowstyle="->", color="black", lw=1),
    )
    plt.tight_layout()
    fig.savefig(out / "fig_ece_bars.png", dpi=180)
    plt.close(fig)
    print(f"Wrote {out}/fig_ece_bars.png")


def fig_reliability(per_row: pd.DataFrame, out: Path, n_bins: int = 10):
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray",
            label="Perfect calibration", linewidth=1.4)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    for method in METHOD_ORDER:
        col = f"score_{method}"
        if col not in per_row.columns:
            continue
        probs = per_row[col].values
        y = per_row["real_defect"].values
        emp = []
        for i in range(n_bins):
            m = (probs >= bins[i]) & (probs < bins[i + 1])
            if i == n_bins - 1:
                m = (probs >= bins[i]) & (probs <= bins[i + 1])
            if m.sum() == 0:
                emp.append(np.nan)
            else:
                emp.append(float(y[m].mean()))
        ax.plot(bin_centers, emp, marker="o", label=method,
                color=PALETTE.get(method, "#888"), linewidth=1.8)
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Empirical defect rate")
    ax.set_title("Reliability diagram (real defects, all methods)", fontsize=11)
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    plt.tight_layout()
    fig.savefig(out / "fig_reliability.png", dpi=180)
    plt.close(fig)
    print(f"Wrote {out}/fig_reliability.png")


def fig_per_repo_precision(per_event: pd.DataFrame, per_row: pd.DataFrame,
                            out: Path):
    # Join per_event with the repo from per_row (via event_id)
    ev_repo = per_row[["event_id", "repo"]].drop_duplicates("event_id")
    pe = per_event.merge(ev_repo, on="event_id", how="left")
    # Aggregate p@1 per repo per method
    agg = pe.groupby(["repo", "method"])["p1"].mean().reset_index()
    # Wide format for grouped bars
    piv = agg.pivot(index="repo", columns="method", values="p1")
    # Only keep methods present
    methods = [m for m in METHOD_ORDER if m in piv.columns]
    # Sort repos alphabetically for a stable, readable order
    piv = piv.sort_index()

    fig, ax = plt.subplots(figsize=(12, 7))
    x = np.arange(len(piv.index))
    w = 0.20
    for i, method in enumerate(methods):
        offset = (i - (len(methods) - 1) / 2) * w
        ax.bar(x + offset, piv[method].values, w,
               label=method, color=PALETTE.get(method, "#888"))
    ax.set_xticks(x)
    ax.set_xticklabels(piv.index, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Precision@1")
    ax.set_title("Per-repo precision@1 by method (real defects)", fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.legend(loc="upper right", ncol=2)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    fig.savefig(out / "fig_per_repo_precision.png", dpi=180)
    plt.close(fig)
    print(f"Wrote {out}/fig_per_repo_precision.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir",
                    default=os.path.expanduser("~/paperF/results"))
    args = ap.parse_args()
    results_dir = Path(args.results_dir)
    out = results_dir / "figures"
    out.mkdir(parents=True, exist_ok=True)

    summary, per_event, per_row = load_data(results_dir)

    fig_headline_bars(summary, out)
    fig_ece_bars(summary, out)
    fig_reliability(per_row, out)
    fig_per_repo_precision(per_event, per_row, out)
    print(f"\nAll figures written to {out}")


if __name__ == "__main__":
    main()
