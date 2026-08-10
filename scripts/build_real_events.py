#!/usr/bin/env python3
"""
build_real_events.py — Convert Defects4J + BugsInPy real bugs into the
(event, file) row schema expected by run_experiment_v2.py.

Output: ~/paperF/datasets/real_events.parquet

Schema (matches synthetic generate_events output exactly):
    event_id, repo, file_name, real_defect,
    exception_type, exception_idx, http_status,
    app_code_changed, validator_changed, schema_changed,
    fixture_changed, config_changed, locator_healed,
    historical_flake_rate,
    commit_count, unique_developers, lines_added, lines_deleted,
    code_churn, file_age_days, commit_frequency

Ground truth: files touched by the fix commit -> real_defect=1.
Distractors: sibling files from the same package/directory -> real_defect=0.
Per event we emit 3-8 (event, file) rows to match the original design.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

import pandas as pd

# --------------------------------------------------------------------------
# Schema constants -- MUST match run_experiment_v2.py
# --------------------------------------------------------------------------
FEATURES = ["commit_count", "unique_developers", "lines_added",
            "lines_deleted", "code_churn", "file_age_days",
            "commit_frequency"]

EXCEPTION_TYPES = ["AssertionError", "TimeoutError", "ConnectionError",
                   "AttributeError", "ValueError", "KeyError",
                   "TypeError", "RuntimeError", "Other"]

MIN_IMPLICATED_FILES = 3
MAX_IMPLICATED_FILES = 8

# --------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------

def sh(cmd: list[str], cwd: str | None = None, timeout: int = 60) -> str:
    """Run a shell command and return stdout. Silently returns '' on failure."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def git_features_for_file(repo_dir: str, file_path: str,
                          before_commit: str) -> dict:
    """Extract the 7 pre-execution features for one file, as of `before_commit`.

    Uses git log up to (not including) `before_commit`. Values are integers
    or floats; missing data -> 0.
    """
    # commit_count and dates
    log = sh(["git", "log", "--follow", "--format=%H|%an|%ai", before_commit,
              "--", file_path], cwd=repo_dir, timeout=30)
    if not log:
        return dict(commit_count=0, unique_developers=0, lines_added=0,
                    lines_deleted=0, code_churn=0, file_age_days=0,
                    commit_frequency=0.0)
    lines = [ln for ln in log.splitlines() if ln.strip()]
    commits = [ln.split("|") for ln in lines]
    commit_count = len(commits)
    authors = set(c[1] for c in commits if len(c) > 1)
    dates = [c[2] for c in commits if len(c) > 2]
    try:
        first = dt.datetime.fromisoformat(dates[-1].replace(" ", "T")[:19])
        last = dt.datetime.fromisoformat(dates[0].replace(" ", "T")[:19])
        file_age_days = max(1, (last - first).days)
        weeks = max(1.0, file_age_days / 7.0)
        commit_frequency = commit_count / weeks
    except Exception:
        file_age_days = 0
        commit_frequency = 0.0

    # lines_added / deleted
    numstat = sh(["git", "log", "--follow", "--numstat", "--format=",
                  before_commit, "--", file_path],
                 cwd=repo_dir, timeout=30)
    la = ld = 0
    for ln in numstat.splitlines():
        parts = ln.strip().split("\t")
        if len(parts) >= 2:
            try:
                la += int(parts[0])
                ld += int(parts[1])
            except ValueError:
                pass
    return dict(
        commit_count=commit_count,
        unique_developers=len(authors),
        lines_added=la,
        lines_deleted=ld,
        code_churn=la + ld,
        file_age_days=file_age_days,
        commit_frequency=round(commit_frequency, 4),
    )


def classify_exception(msg: str) -> tuple[str, int]:
    """Pick an exception type + index for the event row from a test message."""
    msg = msg or ""
    for i, t in enumerate(EXCEPTION_TYPES):
        if t.lower() in msg.lower():
            return t, i
    return "AssertionError", 0  # sensible default for real bugs


def infer_change_flags(file_paths: list[str]) -> dict:
    """Heuristic diff-signal flags from file path patterns."""
    paths = " ".join(file_paths).lower()
    return dict(
        app_code_changed=int(any(
            p.endswith((".java", ".py")) and "test" not in p.lower()
            and "fixture" not in p.lower() and "config" not in p.lower()
            for p in file_paths)),
        validator_changed=int("validate" in paths or "validation" in paths
                              or "check" in paths),
        schema_changed=int("schema" in paths or ".xsd" in paths
                           or ".json" in paths or ".yaml" in paths),
        fixture_changed=int("fixture" in paths or "conftest" in paths),
        config_changed=int("config" in paths or ".properties" in paths
                           or ".ini" in paths or ".toml" in paths),
        locator_healed=0,  # not applicable for Defects4J / BugsInPy
    )


def sample_distractors(repo_dir: str, fix_files: list[str],
                       n_wanted: int, seed: int) -> list[str]:
    """Return sibling files from the same directories, excluding fix files."""
    rng = random.Random(seed)
    candidate_pool: set[str] = set()
    for f in fix_files:
        d = os.path.dirname(f) or "."
        listing = sh(["git", "ls-tree", "--name-only", "HEAD", d + "/"],
                     cwd=repo_dir, timeout=15)
        for line in listing.splitlines():
            line = line.strip()
            if (line and line != f and line not in fix_files
                and line.endswith((".java", ".py"))):
                candidate_pool.add(line)
    pool = list(candidate_pool)
    rng.shuffle(pool)
    return pool[:n_wanted]


# --------------------------------------------------------------------------
# Defects4J loader
# --------------------------------------------------------------------------

def read_active_bugs(defects4j_dir: str, project: str) -> list[dict]:
    """Read framework/projects/<Project>/active-bugs.csv."""
    csv_path = os.path.join(defects4j_dir, "framework", "projects", project,
                            "active-bugs.csv")
    if not os.path.exists(csv_path):
        return []
    with open(csv_path) as f:
        return list(csv.DictReader(f))


def defects4j_projects(defects4j_dir: str) -> list[str]:
    return ["Chart", "Cli", "Closure", "Codec", "Collections", "Compress",
            "Csv", "Gson", "JacksonCore", "JacksonDatabind", "JacksonXml",
            "Jsoup", "JxPath", "Lang", "Math", "Mockito", "Time"]


def build_defects4j_events(defects4j_dir: str, workdir_root: str,
                           max_bugs_per_project: int | None = None) -> list[dict]:
    """Iterate all Defects4J bugs, emit one event per bug with 3-8 file rows."""
    events: list[dict] = []
    for proj in defects4j_projects(defects4j_dir):
        bugs = read_active_bugs(defects4j_dir, proj)
        if max_bugs_per_project:
            bugs = bugs[:max_bugs_per_project]
        print(f"[{time.strftime('%H:%M:%S')}] Defects4J {proj}: {len(bugs)} bugs")
        for b in bugs:
            bug_id = b.get("bug.id") or b.get("bugID")
            if not bug_id:
                continue
            wd = os.path.join(workdir_root, f"d4j-{proj}-{bug_id}b")
            # checkout buggy version
            if not os.path.exists(wd):
                r = subprocess.run(
                    ["defects4j", "checkout", "-p", proj, "-v", f"{bug_id}b",
                     "-w", wd],
                    capture_output=True, text=True, timeout=180)
                if r.returncode != 0:
                    print(f"  [skip] {proj}-{bug_id}: checkout failed")
                    continue
            # Defects4J tags: D4J_<Project>_<BugId>_BUGGY_VERSION / _FIXED_VERSION
            buggy_tag = f"D4J_{proj}_{bug_id}_BUGGY_VERSION"
            fixed_tag = f"D4J_{proj}_{bug_id}_FIXED_VERSION"
            fix_sha = sh(["git", "rev-parse", fixed_tag], cwd=wd).strip()
            parent_sha = sh(["git", "rev-parse", buggy_tag], cwd=wd).strip()
            if not fix_sha or not parent_sha:
                print(f"  [skip] {proj}-{bug_id}: tags not found "
                      f"({buggy_tag}, {fixed_tag})")
                continue
            # files modified by fix
            fix_files = [ln.strip() for ln in sh(
                ["git", "diff", "--name-only", parent_sha, fix_sha],
                cwd=wd).splitlines() if ln.strip()]
            fix_files = [f for f in fix_files if f.endswith((".java",))
                         and "test" not in f.lower()][:5]
            if not fix_files:
                continue
            # sample distractors
            n_dist = max(0, MIN_IMPLICATED_FILES - len(fix_files))
            n_max = MAX_IMPLICATED_FILES - len(fix_files)
            seed = int(hashlib.md5(f"{proj}-{bug_id}".encode()).hexdigest(), 16) % (2**32)
            rng = random.Random(seed)
            n_dist = rng.randint(n_dist, max(n_dist, n_max))
            distractors = sample_distractors(wd, fix_files, n_dist, seed)
            implicated = fix_files + distractors
            change_flags = infer_change_flags(fix_files)
            event_id = f"d4j-{proj}-{bug_id}"
            for f in implicated:
                feats = git_features_for_file(wd, f, parent_sha)
                row = {
                    "event_id": event_id,
                    "repo": f"defects4j:{proj}",
                    "file_name": f,
                    "real_defect": 1 if f in fix_files else 0,
                    "exception_type": "AssertionError",
                    "exception_idx": 0,
                    "http_status": 0,
                    **change_flags,
                    "historical_flake_rate": 0.0,
                    **feats,
                }
                events.append(row)
    return events


# --------------------------------------------------------------------------
# BugsInPy loader
# --------------------------------------------------------------------------

def bugsinpy_projects(bip_dir: str) -> list[str]:
    p = os.path.join(bip_dir, "projects")
    return sorted(os.listdir(p)) if os.path.exists(p) else []


def _extract_fix_files_bip(bug_dir: str) -> list[str]:
    """Parse bug_patch.txt to get changed .py files (non-test)."""
    info_path = os.path.join(bug_dir, "bug_patch.txt")
    if not os.path.exists(info_path):
        return []
    try:
        info = open(info_path).read()
    except Exception:
        return []
    fix_files = list(set(re.findall(r"^\+\+\+ b/(.+)$", info, re.MULTILINE)))
    return [f for f in fix_files if f.endswith(".py")
            and "test" not in f.lower()][:5]


def build_bugsinpy_events(bip_dir: str, workdir_root: str,
                          max_bugs_per_project: int | None = None) -> list[dict]:
    events: list[dict] = []
    for proj in bugsinpy_projects(bip_dir):
        bugs_dir = os.path.join(bip_dir, "projects", proj, "bugs")
        if not os.path.exists(bugs_dir):
            continue
        bug_ids = sorted([int(x) for x in os.listdir(bugs_dir) if x.isdigit()])
        if max_bugs_per_project:
            bug_ids = bug_ids[:max_bugs_per_project]
        print(f"[{time.strftime('%H:%M:%S')}] BugsInPy {proj}: {len(bug_ids)} bugs")

        # PASS 1: harvest all fix files across all bugs in this project.
        # These become the distractor pool for cross-bug ranking.
        project_fix_pool: set[str] = set()
        per_bug_fixes: dict[int, list[str]] = {}
        for bug_id in bug_ids:
            fx = _extract_fix_files_bip(os.path.join(bugs_dir, str(bug_id)))
            per_bug_fixes[bug_id] = fx
            project_fix_pool.update(fx)

        # PASS 2: emit events with distractors sampled from OTHER bugs
        for bug_id in bug_ids:
            fix_files = per_bug_fixes[bug_id]
            if not fix_files:
                continue
            # Distractor candidates = other bugs' fix files in same project
            candidate_pool = list(project_fix_pool - set(fix_files))
            seed = int(hashlib.md5(f"{proj}-{bug_id}".encode()).hexdigest(), 16) % (2**32)
            rng = random.Random(seed)
            n_dist_low = max(0, MIN_IMPLICATED_FILES - len(fix_files))
            n_dist_high = max(n_dist_low, MAX_IMPLICATED_FILES - len(fix_files))
            n_dist = rng.randint(n_dist_low, n_dist_high) if n_dist_high > 0 else 0
            rng.shuffle(candidate_pool)
            distractors = candidate_pool[:n_dist]
            implicated = fix_files + distractors
            change_flags = infer_change_flags(fix_files)
            event_id = f"bip-{proj}-{bug_id}"
            for f in implicated:
                # No repo checkout -> derive features from name only (file exists in
                # multiple bug patches). Use per-file frequency in the fix pool as a
                # weak proxy for churn/frequency signals.
                freq_in_pool = sum(1 for b in bug_ids if f in per_bug_fixes.get(b, []))
                feats = dict(
                    commit_count=freq_in_pool,
                    unique_developers=max(1, freq_in_pool // 3),
                    lines_added=freq_in_pool * 20,
                    lines_deleted=freq_in_pool * 15,
                    code_churn=freq_in_pool * 35,
                    file_age_days=freq_in_pool * 30,
                    commit_frequency=round(freq_in_pool / 12.0, 4),
                )
                row = {
                    "event_id": event_id,
                    "repo": f"bugsinpy:{proj}",
                    "file_name": f,
                    "real_defect": 1 if f in fix_files else 0,
                    "exception_type": "AssertionError",
                    "exception_idx": 0,
                    "http_status": 0,
                    **change_flags,
                    "historical_flake_rate": 0.0,
                    **feats,
                }
                events.append(row)
    return events


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--defects4j-dir", default=os.path.expanduser("~/paperF/defects4j"))
    ap.add_argument("--bugsinpy-dir", default=os.path.expanduser("~/paperF/BugsInPy"))
    ap.add_argument("--workdir", default="/tmp/paperF_work")
    ap.add_argument("--out", default=os.path.expanduser("~/paperF/datasets/real_events.parquet"))
    ap.add_argument("--max-bugs-per-project", type=int, default=None,
                    help="Cap bugs per project for quick smoke tests")
    ap.add_argument("--only", choices=["d4j", "bip", "both"], default="both")
    args = ap.parse_args()

    Path(args.workdir).mkdir(parents=True, exist_ok=True)
    Path(os.path.dirname(args.out)).mkdir(parents=True, exist_ok=True)

    all_events: list[dict] = []
    if args.only in ("d4j", "both"):
        print(f"=== Building Defects4J events ===")
        all_events.extend(build_defects4j_events(
            args.defects4j_dir, args.workdir, args.max_bugs_per_project))
    if args.only in ("bip", "both"):
        print(f"=== Building BugsInPy events ===")
        all_events.extend(build_bugsinpy_events(
            args.bugsinpy_dir, args.workdir, args.max_bugs_per_project))

    df = pd.DataFrame(all_events)
    print(f"\n=== Summary ===")
    print(f"Total (event,file) rows: {len(df)}")
    print(f"Unique events: {df['event_id'].nunique() if len(df) else 0}")
    print(f"Real-defect fraction: {df['real_defect'].mean():.3f}"
          if len(df) else "N/A")
    print(f"Repos: {df['repo'].nunique() if len(df) else 0}")

    df.to_parquet(args.out, index=False)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
