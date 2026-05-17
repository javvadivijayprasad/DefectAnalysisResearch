"""
generate_figures.py — paper figures from the CSV tables.

Produces:
  figures/fig1_pipeline.png             — method block diagram (two-stage)
  figures/fig2_precision_comparison.png — bar chart of precision@1 by method
  figures/fig3_calibration.png          — calibration curves per method
  figures/fig4_triage_time.png          — triage-time boxplot
  figures/fig5_taxonomy_confusion.png   — taxonomy confusion heatmap
"""
from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("figures")


def _read_csv(p: Path) -> List[Dict[str, str]]:
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _bar_precision(tables: Path, figures: Path) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    rows = _read_csv(tables / "headline_metrics.csv")
    if not rows:
        logger.warning("headline_metrics.csv empty; skipping precision chart.")
        return

    labels = [r["method_name"] for r in rows]
    vals = [float(r["precision_at_1"]) for r in rows]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(labels, vals)
    ax.set_xlabel("Precision@1 (mean across repos)")
    ax.set_xlim(0, 1)
    ax.set_title("Precision@1 by method")
    for i, v in enumerate(vals):
        ax.text(v + 0.01, i, f"{v:.2f}", va="center")
    plt.tight_layout()
    fig.savefig(figures / "fig2_precision_comparison.png", dpi=160)
    plt.close(fig)
    logger.info("Wrote fig2_precision_comparison.png")


def _triage_time(tables: Path, figures: Path) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    rows = _read_csv(tables / "per_repo_metrics.csv")
    if not rows:
        return
    by_method: Dict[str, List[float]] = {}
    for r in rows:
        by_method.setdefault(r["method_id"], []).append(
            float(r["mean_triage_time_seconds"])
        )

    labels = list(by_method.keys())
    data = [by_method[m] for m in labels]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.boxplot(data, tick_labels=labels)
    ax.set_ylabel("Mean triage time (seconds)")
    ax.set_title("Triage time distribution per repo, by method")
    plt.tight_layout()
    fig.savefig(figures / "fig4_triage_time.png", dpi=160)
    plt.close(fig)
    logger.info("Wrote fig4_triage_time.png")


def _pipeline_diagram(figures: Path) -> None:
    """Static block diagram for Fig 1 — the two-stage pipeline."""
    import matplotlib.pyplot as plt  # type: ignore
    from matplotlib.patches import FancyBboxPatch  # type: ignore

    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.5)
    ax.axis("off")

    boxes = [
        (0.2, 1, "Test run\n(failures + stacks)"),
        (2.2, 1, "Implicated files\n(coverage / imports)"),
        (4.2, 1, "Paper 4 GB model\n(.pkl)"),
        (6.2, 1, "SHAP local\n(per-file narrative)"),
        (8.2, 1, "Taxonomy\n(8 categories)"),
    ]
    for (x, y, label) in boxes:
        box = FancyBboxPatch((x, y), 1.6, 1.2,
                             boxstyle="round,pad=0.06", linewidth=1.4,
                             edgecolor="black", facecolor="white")
        ax.add_patch(box)
        ax.text(x + 0.8, y + 0.6, label, ha="center", va="center", fontsize=9)

    for i in range(len(boxes) - 1):
        x1 = boxes[i][0] + 1.6
        x2 = boxes[i + 1][0]
        ax.annotate("", xy=(x2, 1.6), xytext=(x1, 1.6),
                    arrowprops=dict(arrowstyle="->", lw=1.2))

    ax.text(5.0, 3.1, "Post-Execution Defect Attribution — Two-Stage Pipeline",
            ha="center", fontsize=11, weight="bold")
    plt.tight_layout()
    fig.savefig(figures / "fig1_pipeline.png", dpi=160)
    plt.close(fig)
    logger.info("Wrote fig1_pipeline.png")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--tables", type=Path, default=Path("tables"))
    parser.add_argument("--figures", type=Path, default=Path("figures"))
    args = parser.parse_args()
    args.figures.mkdir(parents=True, exist_ok=True)

    _pipeline_diagram(args.figures)
    _bar_precision(args.tables, args.figures)
    _triage_time(args.tables, args.figures)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
