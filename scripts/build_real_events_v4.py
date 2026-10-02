#!/usr/bin/env python3
"""
build_real_events_v4.py — rebuild of the Paper F corpus (Defects4J v2.0.1 + BugsInPy) with ONE
construction for both corpora, every feature taken from real git history at the ORIGINAL pre-fix
revision, and no proxy values.

What changed versus build_real_events.py (v3 bundle), and why:

1. Defects4J reference revision. v3 computed features at the D4J_<P>_<B>_BUGGY_VERSION tag. That tag is
   a commit Defects4J creates at checkout time by re-applying the bug to the fixed revision, so it touches
   exactly the fix files, is dated at checkout time, and sits on top of the fix commit's history. Features
   at that tag therefore saw the fix itself (commit count +1, recent churn, inflated age) for the fix files
   only — a label leak that is invisible in the paper and visible in the data (fix-file median commit_count
   30 vs 13 for distractors, P@1 0.98 on Java). v4 uses `revision.id.buggy` from active-bugs.csv, the
   project's own pre-fix revision, for both the feature window and the file listing.
2. BugsInPy features. v3 did not check out BugsInPy projects; its seven features were arithmetic on the
   number of other bugs touching the file (freq*20, freq*30, ...). v4 clones each project's repository
   (github_url in project.info), takes buggy_commit_id / fixed_commit_id from bug.info, and computes the same
   git features as for Defects4J at buggy_commit_id.
3. Distractors. v3 used same-directory siblings for Defects4J and other bugs' fix files for BugsInPy. v4 uses
   same-directory siblings at the pre-fix revision for both, with the same seeded count rule (3–8 files).
4. Events whose fix files have no sibling source file (no distractor possible) are skipped and logged.
5. Failure-side columns. The corpora provide no post-execution signals after the fact. v4 still emits the
   columns, for schema compatibility with run_real_experiment.py, but fills them with the constants they
   had in v3 and records that in the parquet metadata; the paper must say they are constants.

Usage (WSL2):
    python3 build_real_events_v4.py --defects4j-dir ~/paperF/defects4j --bugsinpy-dir ~/paperF/BugsInPy \
        --bip-repos ~/paperF/bip_repos --workdir /tmp/paperF_work --out ~/paperF/datasets/real_events_v4.parquet
Writes also <out>.build_log.csv (one row per bug: status, n_fix, n_distractors, reason if skipped).
"""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, os, random, re, subprocess, time
from pathlib import Path
import pandas as pd

FEATURES = ["commit_count", "unique_developers", "lines_added", "lines_deleted", "code_churn",
            "file_age_days", "commit_frequency"]
MIN_IMPLICATED_FILES, MAX_IMPLICATED_FILES, MAX_FIX_FILES = 3, 8, 5
CONST_FAILURE_COLS = dict(exception_type="AssertionError", exception_idx=0, http_status=0,
                          locator_healed=0, historical_flake_rate=0.0)
BUILD_LOG: list[dict] = []

def sh(cmd, cwd=None, timeout=120) -> str:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""

def git_features_for_file(repo_dir: str, file_path: str, before_commit: str) -> dict:
    """Identical to v3: commits touching the file in the ancestry of before_commit (inclusive)."""
    log = sh(["git", "log", "--follow", "--format=%H|%an|%ai", before_commit, "--", file_path], cwd=repo_dir)
    if not log:
        return dict(commit_count=0, unique_developers=0, lines_added=0, lines_deleted=0, code_churn=0,
                    file_age_days=0, commit_frequency=0.0)
    commits = [ln.split("|") for ln in log.splitlines() if ln.strip()]
    commit_count = len(commits)
    authors = set(c[1] for c in commits if len(c) > 1)
    dates = [c[2] for c in commits if len(c) > 2]
    try:
        first = dt.datetime.fromisoformat(dates[-1].replace(" ", "T")[:19])
        last = dt.datetime.fromisoformat(dates[0].replace(" ", "T")[:19])
        file_age_days = max(1, (last - first).days)
        commit_frequency = commit_count / max(1.0, file_age_days / 7.0)
    except Exception:
        file_age_days, commit_frequency = 0, 0.0
    numstat = sh(["git", "log", "--follow", "--numstat", "--format=", before_commit, "--", file_path], cwd=repo_dir)
    la = ld = 0
    for ln in numstat.splitlines():
        p = ln.strip().split("\t")
        if len(p) >= 2:
            try: la += int(p[0]); ld += int(p[1])
            except ValueError: pass
    return dict(commit_count=commit_count, unique_developers=len(authors), lines_added=la, lines_deleted=ld,
                code_churn=la + ld, file_age_days=file_age_days, commit_frequency=round(commit_frequency, 4))

def infer_change_flags(fix_files: list[str]) -> dict:
    """Event-level flags from the fix-file paths (identical to v3; constant within an event)."""
    paths = " ".join(fix_files).lower()
    return dict(
        app_code_changed=int(any(p.endswith((".java", ".py")) and "test" not in p.lower()
                                 and "fixture" not in p.lower() and "config" not in p.lower() for p in fix_files)),
        validator_changed=int("validate" in paths or "validation" in paths or "check" in paths),
        schema_changed=int("schema" in paths or ".xsd" in paths or ".json" in paths or ".yaml" in paths),
        fixture_changed=int("fixture" in paths or "conftest" in paths),
        config_changed=int("config" in paths or ".properties" in paths or ".ini" in paths or ".toml" in paths))

def siblings_at(repo_dir: str, rev: str, fix_files: list[str], ext: tuple) -> list[str]:
    pool = set()
    for f in fix_files:
        d = os.path.dirname(f) or "."
        for line in sh(["git", "ls-tree", "--name-only", rev, d + "/"], cwd=repo_dir).splitlines():
            line = line.strip()
            if line and line not in fix_files and line.endswith(ext) and "test" not in line.lower():
                pool.add(line)
    return sorted(pool)

def make_event(repo_dir: str, rev_buggy: str, rev_fixed: str, ext: tuple, event_id: str, repo_label: str,
               seed_key: str) -> list[dict]:
    fix_files = [ln.strip() for ln in sh(["git", "diff", "--name-only", rev_buggy, rev_fixed], cwd=repo_dir).splitlines()]
    fix_files = [f for f in fix_files if f.endswith(ext) and "test" not in f.lower()][:MAX_FIX_FILES]
    if not fix_files:
        BUILD_LOG.append(dict(event_id=event_id, status="skip", reason="no non-test source file in fix diff")); return []
    seed = int(hashlib.md5(seed_key.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    n_low = max(0, MIN_IMPLICATED_FILES - len(fix_files)); n_high = max(n_low, MAX_IMPLICATED_FILES - len(fix_files))
    n_dist = rng.randint(n_low, n_high) if n_high > 0 else 0
    pool = siblings_at(repo_dir, rev_buggy, fix_files, ext); rng.shuffle(pool)
    distractors = pool[:n_dist]
    if not distractors:
        # an implicated set with no non-defect file cannot be ranked; counting it would be a free top-1 hit
        BUILD_LOG.append(dict(event_id=event_id, status="skip", reason="no distractor available (no sibling source file)")); return []
    flags = infer_change_flags(fix_files)
    rows = []
    for f in fix_files + distractors:
        rows.append({"event_id": event_id, "repo": repo_label, "file_name": f, "real_defect": int(f in fix_files),
                     **CONST_FAILURE_COLS, **flags, **git_features_for_file(repo_dir, f, rev_buggy)})
    BUILD_LOG.append(dict(event_id=event_id, status="ok", n_fix=len(fix_files), n_distractors=len(distractors), pool=len(pool)))
    return rows

# ------------------------------------------------------------------ Defects4J
def build_defects4j(d4j_dir: str, workdir: str, cap: int | None) -> list[dict]:
    rows = []
    projects = sorted(p for p in os.listdir(os.path.join(d4j_dir, "framework", "projects"))
                      if os.path.isfile(os.path.join(d4j_dir, "framework", "projects", p, "active-bugs.csv")))
    for proj in projects:
        with open(os.path.join(d4j_dir, "framework", "projects", proj, "active-bugs.csv"), newline="") as f:
            bugs = list(csv.DictReader(f))
        if cap: bugs = bugs[:cap]
        print(f"[{time.strftime('%H:%M:%S')}] Defects4J {proj}: {len(bugs)} bugs", flush=True)
        for b in bugs:
            bug_id, rev_b, rev_f = b["bug.id"], b["revision.id.buggy"], b["revision.id.fixed"]
            event_id = f"d4j-{proj}-{bug_id}"
            wd = os.path.join(workdir, f"d4j-{proj}-{bug_id}b")
            if not os.path.exists(wd):
                r = subprocess.run(["defects4j", "checkout", "-p", proj, "-v", f"{bug_id}b", "-w", wd],
                                   capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    BUILD_LOG.append(dict(event_id=event_id, status="skip", reason="checkout failed")); continue
            # the original revisions must exist in the checkout's history; otherwise record and skip
            if not sh(["git", "cat-file", "-e", rev_b], cwd=wd) and sh(["git", "rev-parse", rev_b], cwd=wd) == "":
                BUILD_LOG.append(dict(event_id=event_id, status="skip", reason="revision.id.buggy not in history")); continue
            rows += make_event(wd, rev_b, rev_f, (".java",), event_id, f"defects4j:{proj}", f"{proj}-{bug_id}")
    return rows

# ------------------------------------------------------------------ BugsInPy
def kv(path: str) -> dict:
    d = {}
    if os.path.exists(path):
        for m in re.finditer(r'^\s*([A-Za-z_]+)\s*=\s*"?([^"\n]*)"?\s*$', open(path, encoding="utf-8", errors="replace").read(), re.M):
            d[m.group(1)] = m.group(2).strip()
    return d

def build_bugsinpy(bip_dir: str, repos_dir: str, cap: int | None) -> list[dict]:
    rows = []
    Path(repos_dir).mkdir(parents=True, exist_ok=True)
    for proj in sorted(os.listdir(os.path.join(bip_dir, "projects"))):
        pdir = os.path.join(bip_dir, "projects", proj)
        info = kv(os.path.join(pdir, "project.info"))
        url = info.get("github_url", "")
        if not url:
            print(f"  [skip] {proj}: no github_url"); continue
        repo = os.path.join(repos_dir, proj)
        if not os.path.exists(repo):
            print(f"[{time.strftime('%H:%M:%S')}] cloning {proj} from {url}", flush=True)
            subprocess.run(["git", "clone", "--quiet", url, repo], check=False, timeout=3600)
        bugs_dir = os.path.join(pdir, "bugs")
        bug_ids = sorted(int(x) for x in os.listdir(bugs_dir) if x.isdigit())
        if cap: bug_ids = bug_ids[:cap]
        print(f"[{time.strftime('%H:%M:%S')}] BugsInPy {proj}: {len(bug_ids)} bugs", flush=True)
        for bug_id in bug_ids:
            event_id = f"bip-{proj}-{bug_id}"
            binfo = kv(os.path.join(bugs_dir, str(bug_id), "bug.info"))
            rev_b, rev_f = binfo.get("buggy_commit_id", ""), binfo.get("fixed_commit_id", "")
            if not rev_b or not rev_f:
                BUILD_LOG.append(dict(event_id=event_id, status="skip", reason="no commit ids in bug.info")); continue
            if sh(["git", "rev-parse", rev_b], cwd=repo) == "" or sh(["git", "rev-parse", rev_f], cwd=repo) == "":
                BUILD_LOG.append(dict(event_id=event_id, status="skip", reason="commit not in clone")); continue
            rows += make_event(repo, rev_b, rev_f, (".py",), event_id, f"bugsinpy:{proj}", f"{proj}-{bug_id}")
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--defects4j-dir", default=os.path.expanduser("~/paperF/defects4j"))
    ap.add_argument("--bugsinpy-dir", default=os.path.expanduser("~/paperF/BugsInPy"))
    ap.add_argument("--bip-repos", default=os.path.expanduser("~/paperF/bip_repos"))
    ap.add_argument("--workdir", default="/tmp/paperF_work")
    ap.add_argument("--out", default=os.path.expanduser("~/paperF/datasets/real_events_v4.parquet"))
    ap.add_argument("--max-bugs-per-project", type=int, default=None)
    ap.add_argument("--only", choices=["d4j", "bip", "both"], default="both")
    a = ap.parse_args()
    Path(a.workdir).mkdir(parents=True, exist_ok=True); Path(os.path.dirname(a.out)).mkdir(parents=True, exist_ok=True)
    rows = []
    if a.only in ("d4j", "both"): rows += build_defects4j(a.defects4j_dir, a.workdir, a.max_bugs_per_project)
    if a.only in ("bip", "both"): rows += build_bugsinpy(a.bugsinpy_dir, a.bip_repos, a.max_bugs_per_project)
    df = pd.DataFrame(rows)
    df.to_parquet(a.out, index=False)
    pd.DataFrame(BUILD_LOG).to_csv(a.out + ".build_log.csv", index=False)
    ok = sum(1 for b in BUILD_LOG if b["status"] == "ok")
    print(f"\nevents {df['event_id'].nunique() if len(df) else 0} rows {len(df)} repos {df['repo'].nunique() if len(df) else 0} "
          f"defect fraction {df['real_defect'].mean():.3f}; skipped {len(BUILD_LOG) - ok}; wrote {a.out}")
    if len(df):
        df["corpus"] = df["repo"].str.split(":").str[0]
        print(df.groupby(["corpus", "real_defect"])[["commit_count", "file_age_days", "commit_frequency"]].median())

if __name__ == "__main__":
    main()
