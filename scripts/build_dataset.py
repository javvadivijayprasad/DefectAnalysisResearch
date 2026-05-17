"""
build_dataset.py — construct the labeled dataset for Paper 7.

For every repository listed in experiments/paper7_default.yaml, we:

  1. Walk historical test runs (from CI logs or synthesised run manifests).
  2. For every failing test, resolve implicated source files via coverage or
     static imports.
  3. Extract the seven Paper 4 features for each implicated file AS OF the
     commit under test — never with future information.
  4. Apply SZZ labeling: mark each (run, file) row as real_defect iff a
     bug-labeled fix touches the file within `horizon_days`.
  5. Attach failure-level metadata (exception type, http status, schema error
     path, diff summary, historical flake rate).

Outputs a single parquet under datasets/paper7_labeled.parquet plus per-repo
JSON audit logs under datasets/audit/.

This script is intentionally IO-heavy and CPU-light; all ML happens later in
run_experiment.py.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

logger = logging.getLogger("build_dataset")


@dataclass
class Row:
    run_id: str
    repo: str
    commit_sha: str
    run_timestamp: str
    test_name: str
    test_file: str
    file_path: str
    # Paper 4 features
    commit_count: float
    unique_developers: float
    lines_added: float
    lines_deleted: float
    code_churn: float
    file_age_days: float
    commit_frequency: float
    # Failure signals
    exception_type: Optional[str]
    http_status: Optional[int]
    schema_error_path: Optional[str]
    historical_flake_rate: float
    # Diff summary (0/1 flags, caller-supplied)
    schema_changed: int
    fixture_changed: int
    validator_changed: int
    config_changed: int
    app_code_changed: int
    # Self-healing interlock
    locator_healed: int
    # Label
    real_defect: int


def _load_config(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("pyyaml required; install with 'pip install pyyaml'")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _iter_runs(repo_path: Path) -> Iterable[Dict[str, Any]]:
    """Enumerate test runs for a repository.

    Placeholder: in production this reads CI log archives. For local dev we
    look for datasets/runs/<repo>/*.json files that each describe one run.
    """
    runs_dir = repo_path.parent.parent / "runs" / repo_path.name
    if not runs_dir.exists():
        logger.warning("No runs directory at %s — skipping.", runs_dir)
        return []
    out: List[Dict[str, Any]] = []
    for p in sorted(runs_dir.glob("*.json")):
        with p.open("r", encoding="utf-8") as f:
            out.append(json.load(f))
    return out


def _extract_features(commit_sha: str, file_path: str, repo_path: Path) -> Dict[str, float]:
    """Compute Paper 4 features as of commit_sha. Placeholder; calls GitPython
    in production. Here we stub so the pipeline is runnable end-to-end on
    synthetic data during CI smoke tests."""
    # Deterministic stub keyed off commit_sha + file_path
    h = hash((commit_sha, file_path)) & 0xFFFFFFFF
    return {
        "commit_count": float(h % 200),
        "unique_developers": float((h >> 4) % 15 + 1),
        "lines_added": float((h >> 8) % 3000),
        "lines_deleted": float((h >> 12) % 2000),
        "code_churn": float((h >> 16) % 6000),
        "file_age_days": float((h >> 20) % 2000 + 30),
        "commit_frequency": round(((h >> 24) % 100) / 100.0, 4),
    }


def _szz_label(
    commit_sha: str, file_path: str, run_timestamp: str,
    horizon_days: int, repo_path: Path,
) -> int:
    """Stub: 1 iff a bug-labeled fix touches file_path within horizon.

    Production implementation uses `git log -- <file>` after run_timestamp
    joined against issue-tracker metadata.
    """
    h = hash((commit_sha, file_path, "szz")) & 0xFFFFFFFF
    return 1 if (h % 100) < 35 else 0  # ~35% positive rate, tunable for tests


def _historical_flake_rate(test_name: str) -> float:
    h = hash(("flake", test_name)) & 0xFFFFFFFF
    return round((h % 40) / 100.0, 3)  # 0.00–0.39


def _run_to_rows(
    run: Dict[str, Any], repo: str, repo_path: Path,
    horizon_days: int,
) -> List[Row]:
    rows: List[Row] = []
    run_id = run.get("run_id", "unknown")
    commit_sha = run.get("commit_sha", "0" * 40)
    run_ts = run.get("timestamp_iso", datetime.now(tz=timezone.utc).isoformat())
    diff = run.get("diff_summary", {})

    for failure in run.get("failures", []):
        implicated = failure.get("implicated_files") or [failure.get("test_file")]
        flake_rate = _historical_flake_rate(failure.get("test_name", ""))
        locator_healed = int(bool(failure.get("locator_healed")))
        for f in implicated:
            if not f:
                continue
            features = _extract_features(commit_sha, f, repo_path)
            label = _szz_label(commit_sha, f, run_ts, horizon_days, repo_path)
            rows.append(Row(
                run_id=run_id,
                repo=repo,
                commit_sha=commit_sha,
                run_timestamp=run_ts,
                test_name=failure.get("test_name", "unknown"),
                test_file=failure.get("test_file", "unknown"),
                file_path=f,
                commit_count=features["commit_count"],
                unique_developers=features["unique_developers"],
                lines_added=features["lines_added"],
                lines_deleted=features["lines_deleted"],
                code_churn=features["code_churn"],
                file_age_days=features["file_age_days"],
                commit_frequency=features["commit_frequency"],
                exception_type=failure.get("exception_type"),
                http_status=failure.get("http_status"),
                schema_error_path=failure.get("schema_error_path"),
                historical_flake_rate=flake_rate,
                schema_changed=int(bool(diff.get("schema_changed"))),
                fixture_changed=int(bool(diff.get("fixture_changed"))),
                validator_changed=int(bool(diff.get("validator_changed"))),
                config_changed=int(bool(diff.get("config_changed"))),
                app_code_changed=int(bool(diff.get("app_code_changed"))),
                locator_healed=locator_healed,
                real_defect=label,
            ))
    return rows


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path,
                        default=Path("experiments/paper7_default.yaml"))
    parser.add_argument("--out", type=Path,
                        default=Path("datasets/paper7_labeled.parquet"))
    parser.add_argument("--audit-dir", type=Path,
                        default=Path("datasets/audit"))
    args = parser.parse_args()

    cfg = _load_config(args.config)
    horizon = int(cfg["labeling"]["horizon_days"])
    all_rows: List[Row] = []

    for repo in cfg["repositories"]:
        repo_name = repo["name"]
        repo_path = Path(repo["path"])
        logger.info("Processing repo=%s path=%s", repo_name, repo_path)
        for run in _iter_runs(repo_path):
            all_rows.extend(_run_to_rows(run, repo_name, repo_path, horizon))

    logger.info("Assembled %d labeled rows across %d repos.",
                len(all_rows), len(cfg["repositories"]))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.audit_dir.mkdir(parents=True, exist_ok=True)

    try:
        import pandas as pd  # type: ignore
        df = pd.DataFrame([asdict(r) for r in all_rows])
        if args.out.suffix == ".parquet":
            df.to_parquet(args.out, index=False)
        else:
            df.to_csv(args.out, index=False)
        logger.info("Wrote dataset → %s  rows=%d", args.out, len(df))
    except ImportError:
        # Pandas not available — write CSV via stdlib.
        import csv
        csv_out = args.out.with_suffix(".csv")
        if all_rows:
            keys = list(asdict(all_rows[0]).keys())
            with csv_out.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                for r in all_rows:
                    writer.writerow(asdict(r))
            logger.info("Wrote dataset (CSV fallback) → %s", csv_out)

    audit = {
        "experiment_id": cfg["experiment_id"],
        "random_seed": cfg["random_seed"],
        "horizon_days": horizon,
        "n_rows": len(all_rows),
        "n_positive": sum(r.real_defect for r in all_rows),
        "n_repos": len(cfg["repositories"]),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    with (args.audit_dir / "build_summary.json").open("w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)
    logger.info("Audit → %s", args.audit_dir / "build_summary.json")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
