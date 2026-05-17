"""
generate_tables.py — convert headline_metrics.csv into a LaTeX table snippet
that the paper \\input{}s directly. Keeps the paper build deterministic.
"""
from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

logger = logging.getLogger("tables")


def _fmt(v: str, digits: int = 3) -> str:
    try:
        return f"{float(v):.{digits}f}"
    except Exception:
        return v


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--tables", type=Path, default=Path("tables"))
    args = parser.parse_args()

    src = args.tables / "headline_metrics.csv"
    if not src.exists():
        logger.warning("No headline_metrics.csv found at %s", src)
        return 0

    out = args.tables / "headline_metrics.tex"
    with src.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    with out.open("w", encoding="utf-8") as f:
        f.write(
            "\\begin{tabular}{lccccc}\n\\hline\n"
            "Method & P@1 & P@3 & R@5 & ECE & Triage(s) \\\\\n\\hline\n"
        )
        for r in rows:
            f.write(
                f"{r['method_name']} & "
                f"{_fmt(r['precision_at_1'])} & "
                f"{_fmt(r['precision_at_3'])} & "
                f"{_fmt(r['recall_at_5'])} & "
                f"{_fmt(r['expected_calibration_error'])} & "
                f"{_fmt(r['mean_triage_time_seconds'], 1)} \\\\\n"
            )
        f.write("\\hline\n\\end{tabular}\n")
    logger.info("Wrote %s", out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
