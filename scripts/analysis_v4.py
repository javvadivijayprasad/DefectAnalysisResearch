#!/usr/bin/env python3
"""All manuscript numbers for Paper F v4 from results_v4/. Metric code imported from the harness so that
every number here is computed the same way as summary_real.json. Writes results_v4/paper_numbers_v4.json and
prints a readable trace."""
import json, sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_real_experiment import evaluate_per_event, expected_calibration_error as ece

# Layout: run from the repository root. results_v4/ holds the harness outputs; LLM outputs are either in
# results_v4/llm_baseline/<model>/ (repository layout) or flattened as results_v4/<model>__*.csv.
R = os.environ.get("PAPERF_RESULTS", "results_v4")
BUILD_LOG = next((p for p in ("datasets/real_events_v4.parquet.build_log.csv", "real_events_v4.parquet.build_log.csv") if os.path.exists(p)), None)
def llm_file(model, name):
    """name in {per_event_metrics.csv, summary.json, per_project.csv}; runs dir via llm_runs()."""
    for p in (f"{R}/llm_baseline/{model}/{name}", f"{R}/{model}__{name}"):
        if os.path.exists(p): return p
    raise FileNotFoundError(f"{model} {name}")
def llm_runs(model):
    for p in (f"{R}/llm_baseline/{model}/runs", f"llm_runs/{model}/runs"):
        if os.path.isdir(p): return p
    raise FileNotFoundError(f"{model} runs")
rows = pd.read_csv(f"{R}/per_row_scores_real.csv"); rows["corpus"] = rows["repo"].str.split(":").str[0]
METHODS = {"pre_only": "Cross-project predictor", "fused_rule": "Rule fusion", "fused_ml": "Learned fusion", "fail_only": "Flat prior"}
LLMS = {"claude-sonnet-4-6": "Claude Sonnet 4.6", "gpt-4o-mini": "GPT-4o-mini"}
out = {"corpus": {}, "pooled": {}, "per_corpus": {}, "pairwise": {}, "per_project": {}, "calibration": {}, "llm": {}}

# ---- corpus description
bl = pd.read_csv(BUILD_LOG)
ev = rows.groupby("event_id").agg(n=("file_name", "size"), k=("real_defect", "sum"), corpus=("corpus", "first"))
out["corpus"] = {"events": int(rows.event_id.nunique()), "rows": len(rows), "projects": int(rows.repo.nunique()),
                 "defect_fraction": round(rows.real_defect.mean(), 4), "mean_files_per_event": round(ev.n.mean(), 2),
                 "events_d4j": int((ev.corpus == "defects4j").sum()), "events_bip": int((ev.corpus == "bugsinpy").sum()),
                 "rows_d4j": int((rows.corpus == "defects4j").sum()), "rows_bip": int((rows.corpus == "bugsinpy").sum()),
                 "projects_d4j": int(rows[rows.corpus == "defects4j"].repo.nunique()), "projects_bip": int(rows[rows.corpus == "bugsinpy"].repo.nunique()),
                 "skipped": bl[bl.status == "skip"].reason.value_counts().to_dict(),
                 "skipped_by_corpus": bl[bl.status == "skip"].assign(c=bl.event_id.str[:3]).groupby(["c", "reason"]).size().to_dict(),
                 "fix_files_per_event_mean": round(ev.k.mean(), 2), "events_with_one_fix_file": int((ev.k == 1).sum())}
out["corpus"]["skipped_by_corpus"] = {f"{k[0]}|{k[1]}": int(v) for k, v in out["corpus"]["skipped_by_corpus"].items()}

# ---- per-event metrics for every method, computed by the harness code (random tie-break, seed 42)
pe = {}
for m in METHODS:
    pe[m] = evaluate_per_event(rows[["event_id", "real_defect"]].assign(corpus=rows.corpus.values), rows[f"score_{m}"].values)
    pe[m]["corpus"] = pe[m].event_id.map(ev.corpus)
for l in LLMS:
    d = pd.read_csv(llm_file(l, "per_event_metrics.csv")); d["corpus"] = d.event_id.map(ev.corpus); pe[l] = d
def summ(d, sub=None):
    if sub is not None: d = d[d.corpus == sub]
    return {"n_events": len(d), "p1": round(d.p1.mean(), 4), "p3": round(d.p3.mean(), 4), "r5": round(d.r5.mean(), 4), "mrr": round(d.mrr.mean(), 4), "triage_s": round(d.triage_s.mean(), 2)}
# LLM row-level probabilities are inside run JSONs (not staged); their ECE comes from summary.json (pooled) and per_project.csv
for m in list(METHODS) + list(LLMS):
    out["pooled"][m] = summ(pe[m])
    if m in METHODS: out["pooled"][m]["ece"] = round(ece(rows.real_defect.values, rows[f"score_{m}"].values), 4)
    else: out["pooled"][m]["ece"] = json.load(open(llm_file(m, "summary.json")))["ece_10bin"]
    out["per_corpus"][m] = {}
    for c in ("defects4j", "bugsinpy"):
        out["per_corpus"][m][c] = summ(pe[m], c)
        if m in METHODS:
            g = rows[rows.corpus == c]; out["per_corpus"][m][c]["ece"] = round(ece(g.real_defect.values, g[f"score_{m}"].values), 4)
# LLM per-corpus ECE from per_project.csv if it carries ece; otherwise mark unavailable
for l in LLMS:
    pp = pd.read_csv(llm_file(l, "per_project.csv"))
    out["llm"][l + "_per_project_columns"] = pp.columns.tolist()

# ---- paired bootstrap CIs of P@1 difference vs the predictor (event-level resampling, 10,000, seed 42)
rng = np.random.default_rng(42)
base = pe["pre_only"].set_index("event_id").p1
def boot_ci(diff, n=10000):
    diff = np.asarray(diff); idx = rng.integers(0, len(diff), (n, len(diff)))
    means = diff[idx].mean(axis=1); return round(diff.mean(), 4), round(np.percentile(means, 2.5), 4), round(np.percentile(means, 97.5), 4)
for m in list(METHODS)[1:] + list(LLMS):
    d = pe[m].set_index("event_id").p1.reindex(base.index) - base
    out["pairwise"][m + "_minus_pre_only_p1"] = dict(zip(("mean_diff", "ci_lo", "ci_hi"), boot_ci(d.values)))
    for c in ("defects4j", "bugsinpy"):
        ids = ev.index[ev.corpus == c]
        out["pairwise"][f"{m}_minus_pre_only_p1_{c}"] = dict(zip(("mean_diff", "ci_lo", "ci_hi"), boot_ci(d.reindex(ids).values)))
# MRR differences too
basem = pe["pre_only"].set_index("event_id").mrr
for m in list(METHODS)[1:] + list(LLMS):
    d = pe[m].set_index("event_id").mrr.reindex(basem.index) - basem
    out["pairwise"][m + "_minus_pre_only_mrr"] = dict(zip(("mean_diff", "ci_lo", "ci_hi"), boot_ci(d.values)))

# ---- per-project P@1 and wins/losses vs predictor (threshold ±1 pp), significance by per-project paired bootstrap
proj = {}
for m in list(METHODS) + list(LLMS):
    proj[m] = pe[m].assign(repo=pe[m].event_id.map(rows.groupby("event_id").repo.first())).groupby("repo").p1.mean()
tab = pd.DataFrame(proj); tab["n_events"] = pe["pre_only"].assign(repo=pe["pre_only"].event_id.map(rows.groupby("event_id").repo.first())).groupby("repo").size()
out["per_project"]["table"] = tab.round(3).reset_index().to_dict(orient="records")
rep = pe["pre_only"].event_id.map(rows.groupby("event_id").repo.first())
for m in list(METHODS)[1:] + list(LLMS):
    d = (pe[m].set_index("event_id").p1.reindex(base.index) - base)
    wins = losses = ties = sig = 0
    for r_, ids in rep.groupby(rep).groups.items():
        dd = d.loc[base.index[ids]].values if False else d.loc[pe["pre_only"].event_id[ids]].values
        mean = dd.mean(); wins += mean > 0.01; losses += mean < -0.01; ties += abs(mean) <= 0.01
        if len(dd) >= 2:
            idx = rng.integers(0, len(dd), (2000, len(dd))); ms = dd[idx].mean(axis=1)
            lo, hi = np.percentile(ms, [2.5, 97.5]); sig += (lo > 0) or (hi < 0)
    out["per_project"][m + "_vs_pre_only"] = {"wins": int(wins), "losses": int(losses), "ties": int(ties), "significant_95": int(sig), "projects": int(tab.shape[0])}

# ---- calibration detail for the predictor: reliability bins and the threshold-0.7 claim
p = rows.score_pre_only.values; y = rows.real_defect.values
bins = np.linspace(0, 1, 11); rel = []
for i in range(10):
    m_ = (p >= bins[i]) & ((p < bins[i + 1]) if i < 9 else (p <= bins[i + 1]))
    if m_.sum(): rel.append({"bin": f"[{bins[i]:.1f},{bins[i+1]:.1f}]", "n": int(m_.sum()), "mean_conf": round(p[m_].mean(), 3), "frac_pos": round(y[m_].mean(), 3)})
out["calibration"]["pre_only_reliability"] = rel
for t in (0.5, 0.6, 0.7, 0.8):
    m_ = p >= t; out["calibration"][f"precision_at_threshold_{t}"] = {"n_rows": int(m_.sum()), "share_of_rows": round(m_.mean(), 3), "fraction_defect": round(y[m_].mean(), 3) if m_.sum() else None}
    for c in ("defects4j", "bugsinpy"):
        mc = m_ & (rows.corpus == c).values
        out["calibration"][f"precision_at_threshold_{t}"][c] = {"n_rows": int(mc.sum()), "fraction_defect": round(y[mc].mean(), 3) if mc.sum() else None}

# ---- sensitivity table passthrough
out["sensitivity"] = pd.read_csv(f"{R}/distractor_sensitivity.csv").to_dict(orient="records")
out["llm"]["claude_tokens"] = {k: v for k, v in json.load(open(llm_file("claude-sonnet-4-6", "summary.json"))).items() if "tokens" in k}
json.dump(out, open(f"{R}/paper_numbers_v4.json", "w"), indent=1)

# ---- readable trace
print("CORPUS", json.dumps(out["corpus"], indent=1))
print("\nPOOLED"); [print(f"{m:20s}", out["pooled"][m]) for m in out["pooled"]]
print("\nPER CORPUS"); [print(f"{m:20s} {c:10s}", out["per_corpus"][m][c]) for m in out["per_corpus"] for c in out["per_corpus"][m]]
print("\nPAIRWISE vs predictor"); [print(f"{k:45s}", v) for k, v in out["pairwise"].items()]
print("\nPER PROJECT"); [print(f"{k:35s}", v) for k, v in out["per_project"].items() if k != "table"]
print("\nCALIBRATION"); print(json.dumps(out["calibration"], indent=1))

# ---- LLM row-level probabilities from run logs: per-corpus ECE and a contamination split of Defects4J
import ast, glob
rows_idx = rows.set_index("event_id")
for l in LLMS:
    recs = []
    for f in glob.glob(f"{llm_runs(l)}/*.json"):
        d = json.load(open(f)); conf = ast.literal_eval(d["confidence_by_corpus_row"]) if isinstance(d["confidence_by_corpus_row"], str) else d["confidence_by_corpus_row"]
        sub = rows[rows.event_id == d["event_id"]]
        if len(conf) != len(sub): continue
        for (_, r), c in zip(sub.iterrows(), conf): recs.append((d["event_id"], r.corpus, r.repo, int(r.real_defect), float(c)))
    lr = pd.DataFrame(recs, columns=["event_id", "corpus", "repo", "y", "p"])
    out["llm"][l + "_rows_matched"] = len(lr)
    out["llm"][l + "_ece_pooled_from_runs"] = round(ece(lr.y.values, lr.p.values), 4)
    for c in ("defects4j", "bugsinpy"):
        g = lr[lr.corpus == c]; out["per_corpus"][l][c]["ece"] = round(ece(g.y.values, g.p.values), 4)
# contamination split: the three Defects4J v1 projects most used in LLM program-repair work vs the rest
CLASSIC = {"defects4j:Lang", "defects4j:Math", "defects4j:Time"}
for m in ["pre_only"] + list(LLMS):
    d = pe[m].assign(repo=pe[m].event_id.map(rows.groupby("event_id").repo.first()))
    out["llm"][m + "_p1_d4j_LangMathTime"] = round(d[d.repo.isin(CLASSIC)].p1.mean(), 4)
    out["llm"][m + "_p1_d4j_other13"] = round(d[(d.repo.str.startswith("defects4j")) & (~d.repo.isin(CLASSIC))].p1.mean(), 4)
    out["llm"][m + "_n_LangMathTime"] = int(d.repo.isin(CLASSIC).sum())
json.dump(out, open(f"{R}/paper_numbers_v4.json", "w"), indent=1)
print("\nLLM", json.dumps({k: v for k, v in out["llm"].items() if "columns" not in k}, indent=1))
print("LLM per-corpus", {l: out["per_corpus"][l] for l in LLMS})
