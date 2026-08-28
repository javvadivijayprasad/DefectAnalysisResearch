#!/usr/bin/env python3
"""
llm_baseline.py — External LLM file-level attribution baseline for Paper F.

Adds a fifth, EXTERNAL method next to pre_only / fail_only / fused_rule /
fused_ml: a large language model ranks the candidate files of each failing
event and assigns each file a probability of being the defective one. The
output is scored with the IDENTICAL metric implementation used by the paper
(functions imported from scripts/run_real_experiment.py, with verbatim
fallback copies + a self-test).

Unit of prompting: ONE PROMPT PER EVENT (1,323 events), not per (event, file)
row (6,988 rows). Each prompt shows the event's full candidate list.

INFORMATION PARITY (critical for a fair baseline)
-------------------------------------------------
The LLM observes exactly the columns that fused_ml consumed, and nothing more:
  * event-level failure signal: exception_type, exception_idx, http_status,
    app_code_changed, validator_changed, schema_changed, fixture_changed,
    config_changed, locator_healed, historical_flake_rate
  * per-file repo-history features (the FEATURES list): commit_count,
    unique_developers, lines_added, lines_deleted, code_churn,
    file_age_days, commit_frequency
  * the candidate file paths (identifiers available to every method) and the
    project name / language.
The LLM does NOT see: real_defect labels, file contents, diffs, fix commits,
test source, or anything outside the parquet row. Note that in the real
corpus the failure signal is nearly degenerate (exception_type is always
AssertionError, http_status=0, flake=0), so the LLM's usable signal is
essentially file paths + history features — the same situation fused_ml faced.

ORDER-LEAK PROTECTION: build_real_events.py emits the fix file(s) before the
distractors, which is why the paper's evaluator breaks score ties randomly.
For the same reason this script presents candidates to the LLM in a
DETERMINISTICALLY SHUFFLED order (seeded per event_id), never in corpus order.
Parse-failure fallbacks use this shuffled order, not corpus order.

SCORING: per-row score = the LLM's stated confidence (used verbatim for ECE).
For the ranking metrics a tiny epsilon (1e-6 * rank position) is subtracted so
that the LLM's explicit ranking breaks ties among equal confidences; the
epsilon is far below any confidence granularity and does not affect ECE, which
is computed on the raw confidences. Both vectors go through the paper's own
evaluate_per_event / summarize functions.

LOPO: the LLM has no training phase and receives no data from any project,
so leave-one-project-out is satisfied by construction.

Usage (see scripts/LLM_BASELINE_README.md):
  python scripts/llm_baseline.py --dry-run --pilot 30        # sandbox test
  python scripts/llm_baseline.py --backend anthropic --model claude-sonnet-4-6 --pilot 30
  python scripts/llm_baseline.py --backend anthropic --model claude-sonnet-4-6
  python scripts/llm_baseline.py --backend openai --model gpt-4o-mini

Requires: pandas, numpy, pyarrow (already in requirements.txt). API access
uses stdlib urllib only — no SDK needed. Reads ANTHROPIC_API_KEY /
OPENAI_API_KEY from the environment.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent

# Same feature lists as run_real_experiment.py / SCHEMA.md
FEATURES = ["commit_count", "unique_developers", "lines_added",
            "lines_deleted", "code_churn", "file_age_days",
            "commit_frequency"]
EVENT_SIGNAL = ["exception_type", "exception_idx", "http_status",
                "app_code_changed", "validator_changed", "schema_changed",
                "fixture_changed", "config_changed", "locator_healed",
                "historical_flake_rate"]

RANK_EPS = 1e-6  # tie-break epsilon for the LLM's explicit ranking

# $ per 1M tokens (input, output) — for the pre-run cost estimate only.
PRICING = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}

# --------------------------------------------------------------------------
# Paper scoring functions — import the paper's own implementation; fall back
# to verbatim copies (kept byte-identical in logic) if the import fails
# (e.g. sklearn missing, since run_real_experiment.py imports it at top).
# --------------------------------------------------------------------------

def _load_paper_scoring():
    try:
        import importlib.util
        p = REPO_ROOT / "scripts" / "run_real_experiment.py"
        spec = importlib.util.spec_from_file_location("run_real_experiment", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return (mod.evaluate_per_event, mod.expected_calibration_error,
                mod.summarize, "imported from scripts/run_real_experiment.py")
    except Exception as e:  # pragma: no cover
        return (_evaluate_per_event_copy, _ece_copy, _summarize_copy,
                f"verbatim fallback copy (import failed: {e})")


# ---- verbatim copies from scripts/run_real_experiment.py -----------------

def _evaluate_per_event_copy(events: pd.DataFrame, scores: np.ndarray,
                             triage_seconds_per_file: float = 3.0,
                             tiebreak_seed: int = 42) -> pd.DataFrame:
    ev = events.copy()
    ev["score"] = scores
    rng = np.random.default_rng(tiebreak_seed)
    ev["_tiebreak"] = rng.random(len(ev))
    rows = []
    for eid, grp in ev.groupby("event_id", sort=False):
        n = len(grp)
        grp_sorted = grp.sort_values(
            ["score", "_tiebreak"], ascending=[False, True], kind="stable")
        labels = grp_sorted["real_defect"].values
        p1 = float(labels[:1].mean()) if n >= 1 else 0.0
        p3 = float(labels[:3].mean()) if n >= 3 else float(labels.mean())
        total_pos = int(labels.sum())
        r5 = (float(labels[:5].sum() / total_pos) if total_pos > 0 else 0.0)
        first_pos_rank = 0
        for i, v in enumerate(labels, start=1):
            if v == 1:
                first_pos_rank = i
                break
        mrr = 1.0 / first_pos_rank if first_pos_rank else 0.0
        triage = (first_pos_rank * triage_seconds_per_file if first_pos_rank
                  else n * triage_seconds_per_file)
        rows.append(dict(event_id=eid, n_files=n, n_defects=total_pos,
                         p1=p1, p3=p3, r5=r5, mrr=mrr, triage_s=triage))
    return pd.DataFrame(rows)


def _ece_copy(y_true: np.ndarray, y_prob: np.ndarray,
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


def _summarize_copy(name, per_event, y_true, y_prob):
    return dict(
        method=name,
        n_events=int(len(per_event)),
        n_rows=int(len(y_true)),
        p1_mean=round(float(per_event["p1"].mean()), 4),
        p3_mean=round(float(per_event["p3"].mean()), 4),
        r5_mean=round(float(per_event["r5"].mean()), 4),
        mrr_mean=round(float(per_event["mrr"].mean()), 4),
        triage_s_mean=round(float(per_event["triage_s"].mean()), 2),
        ece_10bin=round(_ece_copy(y_true, y_prob), 4),
    )


def self_test() -> None:
    """Verify ECE against a hand-computed example, and verify the fallback
    copy agrees with the imported paper implementation when available."""
    y = np.array([0, 1, 1, 0])
    p = np.array([0.1, 0.9, 0.6, 0.4])
    # Hand computation (10 equal-width bins, each sample alone in its bin):
    #   0.1 -> |0-0.1|*0.25 ; 0.9 -> |1-0.9|*0.25 ; 0.6 -> |1-0.6|*0.25 ;
    #   0.4 -> |0-0.4|*0.25  => 0.025+0.025+0.1+0.1 = 0.25
    got = _ece_copy(y, p)
    assert abs(got - 0.25) < 1e-12, f"ECE self-test failed: {got} != 0.25"
    _, ece_fn, _, src = _load_paper_scoring()
    rng = np.random.default_rng(0)
    yr = (rng.random(500) < 0.3).astype(int)
    pr = rng.random(500)
    a, b = ece_fn(yr, pr), _ece_copy(yr, pr)
    assert abs(a - b) < 1e-12, f"paper ECE != fallback copy: {a} vs {b}"
    print(f"[self-test] ECE hand-example OK (0.25); paper impl ({src}) "
          f"agrees with fallback copy on 500 random rows.")


# --------------------------------------------------------------------------
# Prompt construction
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert software-defect triage assistant.

You are given one failing-test event from a real open-source project, plus a
numbered list of candidate source files. Exactly one or a few of these files
were changed by the developer's fix commit (the "defective" files); the rest
are distractor files from the same package/directory. For each candidate you
see only its repository path and repository-history statistics (commits,
distinct authors, lines added/deleted, churn, file age in days, commit
frequency) — no file contents.

Your task:
1. Rank ALL candidate indices from most likely defective to least likely.
2. Assign each candidate a probability in [0,1] that it is a defective file
   (i.e., that it appears in the fix commit's diff). Probabilities need NOT
   sum to 1 (more than one file can be defective), but they must be honest,
   calibrated estimates — they will be scored with expected calibration error.

Respond with STRICT JSON only — no prose, no markdown fences:
{"ranking": [<all candidate indices, best first>],
 "confidence": {"<index>": <probability>, ...  (one entry per candidate)}}

Example. Given:
  Project: defects4j:Example (Java) | Exception: AssertionError
  Candidates:
    1. src/main/java/ex/Parser.java | commits=21 devs=6 +510/-300 churn=810 age_days=800 commit_freq=0.0262
    2. src/main/java/ex/ParserException.java | commits=4 devs=2 +60/-10 churn=70 age_days=900 commit_freq=0.0044
    3. src/main/java/ex/Util.java | commits=9 devs=3 +120/-80 churn=200 age_days=2100 commit_freq=0.0043
A valid response is:
{"ranking": [1, 3, 2], "confidence": {"1": 0.62, "3": 0.25, "2": 0.08}}"""


def language_of(repo: str) -> str:
    return "Java" if repo.startswith("defects4j:") else "Python"


def stable_shuffle(event_id: str, n: int) -> list[int]:
    """Deterministic per-event permutation of range(n) (corpus-order leak guard)."""
    seed = int(hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:12], 16)
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    return idx


def build_user_prompt(event_id: str, grp: pd.DataFrame, perm: list[int]) -> str:
    r0 = grp.iloc[0]
    repo = r0["repo"]
    lines = [f"Failing-test event {event_id} in project {repo} "
             f"({language_of(repo)}).",
             f"Failure signal: exception={r0['exception_type']}, "
             f"exception_idx={int(r0['exception_idx'])}, "
             f"http_status={int(r0['http_status'])}, "
             f"historical_flake_rate={float(r0['historical_flake_rate']):.3f}."]
    flags = [c for c in ["app_code_changed", "validator_changed",
                         "schema_changed", "fixture_changed",
                         "config_changed", "locator_healed"]
             if int(r0[c]) == 1]
    lines.append("Change-topology flags set: " +
                 (", ".join(flags) if flags else "none") + ".")
    lines.append(f"Candidates ({len(grp)} files):")
    for disp, orig in enumerate(perm, start=1):
        r = grp.iloc[orig]
        lines.append(
            f"  {disp}. {r['file_name']} | commits={int(r['commit_count'])} "
            f"devs={int(r['unique_developers'])} +{int(r['lines_added'])}/"
            f"-{int(r['lines_deleted'])} churn={int(r['code_churn'])} "
            f"age_days={int(r['file_age_days'])} "
            f"commit_freq={float(r['commit_frequency']):.4f}")
    lines.append("Return the strict JSON object now.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# LLM backends (stdlib urllib; no SDK required)
# --------------------------------------------------------------------------

def _post_json(url: str, headers: dict, body: dict,
               timeout: int = 180) -> dict:
    data = json.dumps(body).encode("utf-8")
    last_err = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, data=data,
                                         headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8", "replace")[:500]
            last_err = f"HTTP {e.code}: {body_txt}"
            if e.code in (429, 500, 502, 503, 529):
                time.sleep(min(60, 2 ** attempt * 2))
                continue
            raise RuntimeError(last_err)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = str(e)
            time.sleep(min(60, 2 ** attempt * 2))
    raise RuntimeError(f"API call failed after 5 attempts: {last_err}")


def call_anthropic(model: str, system: str, user: str,
                   max_tokens: int) -> tuple[str, dict]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set in the environment.")
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    # Identity-linked API keys require the workspace id header.
    ws = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    if ws:
        headers["anthropic-workspace-id"] = ws
    out = _post_json(
        "https://api.anthropic.com/v1/messages",
        headers,
        {"model": model, "max_tokens": max_tokens, "temperature": 0,
         "system": system,
         "messages": [{"role": "user", "content": user}]})
    text = "".join(b.get("text", "") for b in out.get("content", [])
                   if b.get("type") == "text")
    return text, out.get("usage", {})


def call_openai(model: str, system: str, user: str,
                max_tokens: int) -> tuple[str, dict]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("ERROR: OPENAI_API_KEY is not set in the environment.")
    out = _post_json(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "content-type": "application/json"},
        {"model": model, "max_tokens": max_tokens, "temperature": 0,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]})
    text = out["choices"][0]["message"]["content"] or ""
    return text, out.get("usage", {})


def call_dryrun(event_id: str, n_cand: int, attempt: int) -> tuple[str, dict]:
    """Deterministic fake backend — NO network, NO fabricated results kept:
    dry-run output lands in a separate *_dryrun directory and is clearly
    labeled. Every 13th event returns garbage on the first attempt (tests the
    retry path); every 39th returns garbage on both attempts (tests the
    unparsed-fallback path)."""
    h = int(hashlib.sha256(event_id.encode()).hexdigest()[:8], 16)
    if h % 39 == 0:
        return "NOT JSON AT ALL — permanent parse failure test", {}
    if h % 13 == 0 and attempt == 0:
        return "```json\n{broken", {}
    rng = random.Random(h)
    confs = {str(i): round(rng.uniform(0.02, 0.95), 2)
             for i in range(1, n_cand + 1)}
    ranking = sorted(range(1, n_cand + 1), key=lambda i: -float(confs[str(i)]))
    text = ("```json\n" +
            json.dumps({"ranking": ranking, "confidence": confs}) + "\n```")
    return text, {"input_tokens": 0, "output_tokens": 0}


# --------------------------------------------------------------------------
# Response parsing
# --------------------------------------------------------------------------

class ParseError(Exception):
    pass


def parse_response(text: str, n_cand: int) -> tuple[list[int], dict[int, float]]:
    """Extract {ranking, confidence}; tolerate markdown fences and prose
    around a JSON object. Raises ParseError if unusable."""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    obj = None
    try:
        obj = json.loads(t)
    except Exception:
        s, e = t.find("{"), t.rfind("}")
        if s != -1 and e > s:
            try:
                obj = json.loads(t[s:e + 1])
            except Exception:
                pass
    if not isinstance(obj, dict):
        raise ParseError("no JSON object found")
    raw_rank = obj.get("ranking")
    raw_conf = obj.get("confidence")
    if not isinstance(raw_rank, list) or not isinstance(raw_conf, dict):
        raise ParseError("missing ranking/confidence")
    ranking: list[int] = []
    for v in raw_rank:
        try:
            i = int(v)
        except (TypeError, ValueError):
            continue
        if 1 <= i <= n_cand and i not in ranking:
            ranking.append(i)
    if not ranking:
        raise ParseError("empty/invalid ranking")
    conf: dict[int, float] = {}
    for k, v in raw_conf.items():
        try:
            i, p = int(k), float(v)
        except (TypeError, ValueError):
            continue
        if 1 <= i <= n_cand and np.isfinite(p):
            conf[i] = min(1.0, max(0.0, p))
    if not conf:
        raise ParseError("empty/invalid confidence")
    # Complete any omissions deterministically (recorded as parse_status ok;
    # a fully missing section already raised above).
    for i in range(1, n_cand + 1):
        if i not in ranking:
            ranking.append(i)
        if i not in conf:
            conf[i] = 1.0 / n_cand
    return ranking, conf


# --------------------------------------------------------------------------
# Per-event run
# --------------------------------------------------------------------------

def run_event(event_id: str, grp: pd.DataFrame, args) -> dict:
    n = len(grp)
    perm = stable_shuffle(event_id, n)
    user_prompt = build_user_prompt(event_id, grp, perm)
    result = dict(event_id=event_id, repo=grp.iloc[0]["repo"],
                  backend=args.backend, model=args.model,
                  n_candidates=n,
                  presented_files=[grp.iloc[o]["file_name"] for o in perm],
                  timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"))
    parse_status, raw_texts, usage_total = "ok", [], {"input_tokens": 0,
                                                      "output_tokens": 0}
    ranking = conf = None
    for attempt in range(2):
        if args.dry_run:
            text, usage = call_dryrun(event_id, n, attempt)
        elif args.backend == "anthropic":
            text, usage = call_anthropic(args.model, SYSTEM_PROMPT,
                                         user_prompt, args.max_tokens)
        else:
            text, usage = call_openai(args.model, SYSTEM_PROMPT,
                                      user_prompt, args.max_tokens)
        raw_texts.append(text)
        usage_total["input_tokens"] += int(usage.get("input_tokens")
                                           or usage.get("prompt_tokens") or 0)
        usage_total["output_tokens"] += int(usage.get("output_tokens")
                                            or usage.get("completion_tokens")
                                            or 0)
        try:
            ranking, conf = parse_response(text, n)
            if attempt == 1:
                parse_status = "ok_after_retry"
            break
        except ParseError:
            continue
    if ranking is None:
        # Honest fallback: presented (shuffled) order, uniform 1/n confidence.
        parse_status = "unparsed_fallback"
        ranking = list(range(1, n + 1))
        conf = {i: 1.0 / n for i in range(1, n + 1)}
    # Map back to corpus row order: presented index d (1-based) = grp row perm[d-1]
    conf_by_row = [None] * n
    rankpos_by_row = [None] * n
    for pos, disp in enumerate(ranking):
        orig = perm[disp - 1]
        rankpos_by_row[orig] = pos
        conf_by_row[orig] = conf[disp]
    result.update(parse_status=parse_status,
                  llm_ranking_presented=ranking,
                  llm_confidence_presented={str(k): v for k, v in conf.items()},
                  confidence_by_corpus_row=conf_by_row,
                  rankpos_by_corpus_row=rankpos_by_row,
                  usage=usage_total,
                  raw_response=raw_texts[-1][:4000],
                  n_attempts=len(raw_texts))
    return result


def event_path(run_dir: Path, event_id: str) -> Path:
    return run_dir / f"{event_id}.json"


def write_atomic(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------
# Pilot sampling (stratified by repo, largest-remainder, seed 42)
# --------------------------------------------------------------------------

def stratified_pilot(events: pd.DataFrame, n_pilot: int) -> list[str]:
    per_repo = (events.drop_duplicates("event_id")
                .groupby("repo")["event_id"].apply(lambda s: sorted(s))
                .to_dict())
    total = sum(len(v) for v in per_repo.values())
    n_pilot = min(n_pilot, total)
    quotas = {r: n_pilot * len(v) / total for r, v in per_repo.items()}
    alloc = {r: int(q) for r, q in quotas.items()}
    remaining = n_pilot - sum(alloc.values())
    for r in sorted(quotas, key=lambda r: (-(quotas[r] - int(quotas[r])), r)):
        if remaining <= 0:
            break
        if alloc[r] < len(per_repo[r]):
            alloc[r] += 1
            remaining -= 1
    chosen: list[str] = []
    for r in sorted(per_repo):
        k = min(alloc.get(r, 0), len(per_repo[r]))
        if k > 0:
            chosen.extend(random.Random(42).sample(per_repo[r], k))
    return sorted(chosen)


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def score_runs(events: pd.DataFrame, run_dir: Path, out_dir: Path,
               method_name: str) -> None:
    evaluate_per_event, ece_fn, summarize, scoring_src = _load_paper_scoring()
    print(f"[score] metric implementation: {scoring_src}")

    runs = {}
    for p in sorted(run_dir.glob("*.json")):
        try:
            runs[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[score] WARNING: cannot read {p.name}: {e}")
    if not runs:
        sys.exit("No per-event run files found — nothing to score.")

    sub = events[events["event_id"].isin(runs)].reset_index(drop=True)
    n_events = sub["event_id"].nunique()
    print(f"[score] scoring {n_events} events / {len(sub)} rows "
          f"(runs found for {len(runs)} events)")

    raw = np.zeros(len(sub))
    adj = np.zeros(len(sub))
    bad = []
    for eid, grp in sub.groupby("event_id", sort=False):
        rec = runs[eid]
        cbr = rec["confidence_by_corpus_row"]
        rbr = rec["rankpos_by_corpus_row"]
        if len(cbr) != len(grp):
            bad.append(eid)
            continue
        idx = grp.index.values
        raw[idx] = np.array(cbr, dtype=float)
        adj[idx] = np.array(cbr, dtype=float) - RANK_EPS * np.array(rbr,
                                                                    dtype=float)
    if bad:
        print(f"[score] WARNING: {len(bad)} events had run files that do not "
              f"match the corpus candidate count and were scored as-is with "
              f"zeros: {bad[:5]}...")

    y_true = sub["real_defect"].values
    per_event = evaluate_per_event(sub, adj)          # ranking metrics
    summary = summarize(method_name, per_event, y_true, raw)  # ECE on raw conf

    statuses = pd.Series({e: r["parse_status"] for e, r in runs.items()})
    n_fallback = int((statuses == "unparsed_fallback").sum())
    n_retry = int((statuses == "ok_after_retry").sum())
    summary["n_unparsed_fallback"] = n_fallback
    summary["n_ok_after_retry"] = n_retry
    summary["parse_failure_rate"] = round(n_fallback / len(statuses), 4)
    tok_in = sum(r.get("usage", {}).get("input_tokens", 0) for r in runs.values())
    tok_out = sum(r.get("usage", {}).get("output_tokens", 0) for r in runs.values())
    summary["total_input_tokens"] = tok_in
    summary["total_output_tokens"] = tok_out

    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([summary]).to_csv(out_dir / "summary.csv", index=False)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2),
                                          encoding="utf-8")
    pe = per_event.copy()
    repo_of = sub.drop_duplicates("event_id").set_index("event_id")["repo"]
    pe["repo"] = pe["event_id"].map(repo_of)
    pe.to_csv(out_dir / "per_event_metrics.csv", index=False)

    proj_rows = []
    for repo, g in pe.groupby("repo"):
        mask = sub["repo"] == repo
        proj_rows.append(dict(
            repo=repo, n_events=len(g),
            p1_mean=round(float(g["p1"].mean()), 4),
            p3_mean=round(float(g["p3"].mean()), 4),
            r5_mean=round(float(g["r5"].mean()), 4),
            mrr_mean=round(float(g["mrr"].mean()), 4),
            triage_s_mean=round(float(g["triage_s"].mean()), 2),
            ece_10bin=round(ece_fn(y_true[mask.values], raw[mask.values]), 4)))
    pd.DataFrame(proj_rows).sort_values("repo").to_csv(
        out_dir / "per_project.csv", index=False)

    print(f"\n=== {method_name} ===")
    for k in ["n_events", "n_rows", "p1_mean", "p3_mean", "r5_mean",
              "mrr_mean", "triage_s_mean", "ece_10bin",
              "parse_failure_rate", "n_ok_after_retry"]:
        print(f"  {k:<20} {summary[k]}")
    print(f"\nWrote: {out_dir / 'summary.csv'}")
    print(f"       {out_dir / 'summary.json'}")
    print(f"       {out_dir / 'per_event_metrics.csv'}")
    print(f"       {out_dir / 'per_project.csv'}")


# --------------------------------------------------------------------------
# Cost estimate
# --------------------------------------------------------------------------

def estimate_cost(pending: list[tuple[str, pd.DataFrame]], model: str) -> None:
    sys_tok = len(SYSTEM_PROMPT) / 4.0
    tot_in = 0.0
    for eid, grp in pending:
        perm = stable_shuffle(eid, len(grp))
        tot_in += sys_tok + len(build_user_prompt(eid, grp, perm)) / 4.0 + 20
    tot_out = sum(25 * len(g) + 40 for _, g in pending)  # JSON reply estimate
    print(f"[estimate] {len(pending)} prompts (1 per event) | "
          f"~{tot_in / 1e3:.1f}K input tokens, ~{tot_out / 1e3:.1f}K output "
          f"tokens (chars/4 heuristic)")
    if model in PRICING:
        ci, co = PRICING[model]
        cost = tot_in / 1e6 * ci + tot_out / 1e6 * co
        print(f"[estimate] approx cost at ${ci}/M in, ${co}/M out: "
              f"~${cost:.2f} (estimate only — check your provider's pricing)")
    else:
        print(f"[estimate] no pricing table entry for '{model}' — "
              f"multiply token counts by your provider's rates.")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--events", default=str(REPO_ROOT / "datasets" /
                                            "real_events.parquet"))
    ap.add_argument("--backend", choices=["anthropic", "openai"],
                    default="anthropic")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--dry-run", action="store_true",
                    help="No API calls; deterministic fake backend to verify "
                         "the pipeline. Output goes to a separate *_dryrun "
                         "directory and must never be reported as results.")
    ap.add_argument("--pilot", type=int, default=0, metavar="N",
                    help="Run only a stratified sample of N events (seed 42).")
    ap.add_argument("--limit", type=int, default=0,
                    help="Debug: process at most N pending events.")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-tokens", type=int, default=1500)
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="Seconds to sleep between requests per worker.")
    ap.add_argument("--out-root", default=str(REPO_ROOT / "results" /
                                              "llm_baseline"))
    ap.add_argument("--estimate-only", action="store_true")
    ap.add_argument("--score-only", action="store_true",
                    help="Skip the run phase; just (re)score existing runs.")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    events = pd.read_parquet(args.events)
    print(f"Loaded {len(events)} rows / {events['event_id'].nunique()} events "
          f"/ {events['repo'].nunique()} repos from {args.events}")

    model_slug = re.sub(r"[^A-Za-z0-9._-]", "_", args.model)
    if args.dry_run:
        model_slug += "_dryrun"
    out_dir = Path(args.out_root) / model_slug
    run_dir = out_dir / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.pilot:
        keep = set(stratified_pilot(events, args.pilot))
        events_run = events[events["event_id"].isin(keep)].reset_index(drop=True)
        print(f"[pilot] stratified sample: {len(keep)} events "
              f"({events_run['repo'].nunique()} repos represented)")
    else:
        events_run = events

    groups = [(eid, grp.reset_index(drop=True))
              for eid, grp in events_run.groupby("event_id", sort=False)]

    if not args.score_only:
        pending = [(e, g) for e, g in groups
                   if not event_path(run_dir, e).exists()]
        done = len(groups) - len(pending)
        if args.limit:
            pending = pending[:args.limit]
        print(f"[run] {done} events already on disk (resume), "
              f"{len(pending)} to run")
        estimate_cost(pending, args.model)
        if args.estimate_only:
            return
        if pending:
            mode = "DRY-RUN (fake deterministic backend)" if args.dry_run \
                else f"{args.backend} / {args.model} (temperature 0)"
            print(f"[run] mode: {mode}; workers={args.workers}")
            t0 = time.time()
            n_done = 0

            def _one(item):
                eid, grp = item
                rec = run_event(eid, grp, args)
                write_atomic(event_path(run_dir, eid), rec)
                if args.sleep:
                    time.sleep(args.sleep)
                return eid, rec["parse_status"]

            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max(1, args.workers)) as ex:
                for eid, st in ex.map(_one, pending):
                    n_done += 1
                    if n_done % 25 == 0 or n_done == len(pending):
                        rate = n_done / max(1e-9, time.time() - t0)
                        eta = (len(pending) - n_done) / max(rate, 1e-9)
                        print(f"  [{n_done}/{len(pending)}] last={eid} "
                              f"({st}) | {rate:.2f} ev/s | ETA {eta/60:.1f} min")
            print(f"[run] finished {len(pending)} events in "
                  f"{(time.time() - t0)/60:.1f} min")

    method_name = f"llm_{model_slug}"
    score_runs(events_run, run_dir, out_dir, method_name)
    if args.dry_run:
        print("\nNOTE: this was a --dry-run with a fake backend. The numbers "
              "above validate the PIPELINE ONLY and must not be reported.")


if __name__ == "__main__":
    main()
