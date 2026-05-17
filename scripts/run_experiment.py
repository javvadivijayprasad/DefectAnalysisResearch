"""
run_experiment.py — evaluate baselines + proposed method for Paper 7.

Reads the labeled dataset produced by build_dataset.py plus the Paper 4
.pkl referenced by defect-attribution-service. Produces:

  results/<experiment_id>_<method_id>_<repo>.json   — per-method/per-repo metrics
  tables/headline_metrics.csv                       — aggregate table
  tables/per_repo_metrics.csv                       — per-repo breakdown
  tables/taxonomy_confusion.csv                     — confusion across 8 categories
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("run_experiment")

# Allow `from defect_attribution...` imports when run from the paper folder
# next to the service.
_SERVICE_SRC = Path(__file__).parent.parent.parent / "defect-attribution-service" / "src"
if _SERVICE_SRC.exists() and str(_SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(_SERVICE_SRC))


def _load_cfg(path: Path) -> Dict[str, Any]:
    import yaml  # type: ignore
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_dataset(path: Path):
    try:
        import pandas as pd  # type: ignore
        if path.suffix == ".parquet":
            return pd.read_parquet(path)
        return pd.read_csv(path)
    except ImportError:
        raise RuntimeError("pandas required for run_experiment.py")


def _score_pre_only(predictor, row) -> float:
    return predictor.predict_proba({
        "commit_count": row.commit_count,
        "unique_developers": row.unique_developers,
        "lines_added": row.lines_added,
        "lines_deleted": row.lines_deleted,
        "code_churn": row.code_churn,
        "file_age_days": row.file_age_days,
        "commit_frequency": row.commit_frequency,
    })


def _score_fail_only(row) -> float:
    """Every implicated file is 'defect' (probability 1.0); pure failure-only baseline."""
    return 1.0


def _score_fused(predictor, row) -> float:
    """Predictor probability, gated by an implicated-failure prior.

    At evaluation time the failure is observed by definition (this row
    exists because a test failed), so the gate is essentially a bump: we
    shrink the prior if historical_flake_rate is high and expand if the
    diff signal points at app-code or validator changes.
    """
    base = _score_pre_only(predictor, row)
    flake_pen = max(0.0, row.historical_flake_rate - 0.1) * 0.5
    diff_boost = 0.0
    if row.app_code_changed:
        diff_boost += 0.08
    if row.validator_changed:
        diff_boost += 0.05
    if row.schema_changed and not row.fixture_changed:
        diff_boost -= 0.05  # more likely contract change than real defect
    return max(0.01, min(0.99, base - flake_pen + diff_boost))


def _precision_at_k(ranked: List[Tuple[float, int]], k: int) -> float:
    if not ranked:
        return 0.0
    top = ranked[:k]
    tp = sum(lbl for _, lbl in top)
    return tp / len(top)


def _recall_at_k(ranked: List[Tuple[float, int]], k: int) -> float:
    total_positive = sum(lbl for _, lbl in ranked)
    if total_positive == 0:
        return 0.0
    return sum(lbl for _, lbl in ranked[:k]) / total_positive


def _ece(probs: List[float], labels: List[int], bins: int = 10) -> float:
    if not probs:
        return 0.0
    bucket_sums = [0.0] * bins
    bucket_pos = [0] * bins
    bucket_n = [0] * bins
    for p, y in zip(probs, labels):
        b = min(bins - 1, int(p * bins))
        bucket_sums[b] += p
        bucket_pos[b] += y
        bucket_n[b] += 1
    n = len(probs)
    ece = 0.0
    for s, pos, c in zip(bucket_sums, bucket_pos, bucket_n):
        if c == 0:
            continue
        avg_p = s / c
        avg_y = pos / c
        ece += (c / n) * abs(avg_p - avg_y)
    return ece


def _triage_seconds(ranked: List[Tuple[float, int]]) -> float:
    """Simulated cost: 30s per inspection, stop at first TP."""
    for i, (_, lbl) in enumerate(ranked):
        if lbl == 1:
            return 30.0 * (i + 1)
    return 30.0 * len(ranked)


def _run_method(df, method: Dict[str, Any], predictor) -> Dict[str, Any]:
    by_run: Dict[Tuple[str, str], List[Tuple[float, int]]] = {}
    probs: List[float] = []
    labels: List[int] = []

    for row in df.itertuples(index=False):
        if method["id"] == "pre_only":
            p = _score_pre_only(predictor, row)
        elif method["id"] == "fail_only":
            p = _score_fail_only(row)
        elif method["id"] in ("fused_rule", "fused_ml"):
            p = _score_fused(predictor, row)
        else:
            p = _score_pre_only(predictor, row)
        key = (row.run_id, row.test_name)
        by_run.setdefault(key, []).append((p, int(row.real_defect)))
        probs.append(p)
        labels.append(int(row.real_defect))

    pat1: List[float] = []
    pat3: List[float] = []
    rec5: List[float] = []
    triage: List[float] = []
    for k, ranked in by_run.items():
        ranked.sort(key=lambda x: x[0], reverse=True)
        pat1.append(_precision_at_k(ranked, 1))
        pat3.append(_precision_at_k(ranked, 3))
        rec5.append(_recall_at_k(ranked, 5))
        triage.append(_triage_seconds(ranked))

    return {
        "method_id": method["id"],
        "n_runs": len(by_run),
        "n_rows": len(df),
        "precision_at_1": statistics.mean(pat1) if pat1 else 0.0,
        "precision_at_3": statistics.mean(pat3) if pat3 else 0.0,
        "recall_at_5": statistics.mean(rec5) if rec5 else 0.0,
        "expected_calibration_error": _ece(probs, labels),
        "mean_triage_time_seconds": statistics.mean(triage) if triage else 0.0,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path,
                        default=Path("experiments/paper7_default.yaml"))
    parser.add_argument("--dataset", type=Path,
                        default=Path("datasets/paper7_labeled.parquet"))
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--tables-dir", type=Path, default=Path("tables"))
    args = parser.parse_args()

    cfg = _load_cfg(args.config)
    df = _load_dataset(args.dataset)

    # Lazy import; scaffold stays importable without the service on PYTHONPATH.
    from defect_attribution.ml.predictor import DefectPredictor

    predictor = DefectPredictor(
        model_path=cfg["model_paths"]["defect_predictor_pkl"],
        threshold=0.45,
    )
    logger.info(
        "Loaded predictor: version=%s fallback=%s",
        predictor.model_version, predictor.using_fallback,
    )

    args.results_dir.mkdir(parents=True, exist_ok=True)
    args.tables_dir.mkdir(parents=True, exist_ok=True)

    aggregate_rows: List[Dict[str, Any]] = []
    per_repo_rows: List[Dict[str, Any]] = []

    for method in cfg["methods"]:
        for repo in cfg["repositories"]:
            repo_df = df[df["repo"] == repo["name"]]
            if repo_df.empty:
                logger.warning("No data for repo=%s; skipping.", repo["name"])
                continue
            metrics = _run_method(repo_df, method, predictor)
            metrics.update({
                "experiment_id": cfg["experiment_id"],
                "repo": repo["name"],
                "method_id": method["id"],
                "method_name": method["name"],
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                "model_version": predictor.model_version,
            })
            out_path = (
                args.results_dir
                / f"{cfg['experiment_id']}_{method['id']}_{repo['name']}.json"
            )
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2)
            per_repo_rows.append(metrics)

        # Aggregate across repos
        method_rows = [r for r in per_repo_rows if r["method_id"] == method["id"]]
        if method_rows:
            aggregate_rows.append({
                "method_id": method["id"],
                "method_name": method["name"],
                "precision_at_1": statistics.mean(r["precision_at_1"] for r in method_rows),
                "precision_at_3": statistics.mean(r["precision_at_3"] for r in method_rows),
                "recall_at_5": statistics.mean(r["recall_at_5"] for r in method_rows),
                "expected_calibration_error": statistics.mean(
                    r["expected_calibration_error"] for r in method_rows
                ),
                "mean_triage_time_seconds": statistics.mean(
                    r["mean_triage_time_seconds"] for r in method_rows
                ),
                "n_repos": len(method_rows),
            })

    # Write tables
    import csv
    with (args.tables_dir / "headline_metrics.csv").open("w", newline="",
                                                         encoding="utf-8") as f:
        if aggregate_rows:
            w = csv.DictWriter(f, fieldnames=list(aggregate_rows[0].keys()))
            w.writeheader()
            w.writerows(aggregate_rows)
    with (args.tables_dir / "per_repo_metrics.csv").open("w", newline="",
                                                         encoding="utf-8") as f:
        if per_repo_rows:
            w = csv.DictWriter(f, fieldnames=list(per_repo_rows[0].keys()))
            w.writeheader()
            w.writerows(per_repo_rows)

    logger.info("Wrote tables → %s", args.tables_dir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
