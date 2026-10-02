#!/usr/bin/env python3
"""Paper figures for Paper F v4, plain method names, Okabe-Ito palette (validated with the dataviz validator:
passes lightness/chroma/CVD/normal-vision checks; contrast warnings handled by direct labels).
Reads results_v4/paper_numbers_v4.json (written by analysis_v4.py) and the raw CSVs / LLM run logs.
Writes figures_v4/fig1_headline.{pdf,png} ... fig4_sensitivity.{pdf,png}."""
import json, os, ast, glob, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt

R = os.environ.get("PAPERF_RESULTS", "results_v4"); OUT = "figures_v4"; os.makedirs(OUT, exist_ok=True)
def llm_runs(model):
    for p in (f"{R}/llm_baseline/{model}/runs", f"llm_runs/{model}/runs"):
        if os.path.isdir(p): return p
    raise FileNotFoundError(model)
D = json.load(open(f"{R}/paper_numbers_v4.json"))
rows = pd.read_csv(f"{R}/per_row_scores_real.csv"); rows["corpus"] = rows.repo.str.split(":").str[0]
NAMES = {"pre_only": "Cross-project predictor", "fused_rule": "Rule fusion", "fused_ml": "Learned fusion",
         "claude-sonnet-4-6": "Claude Sonnet 4.6", "gpt-4o-mini": "GPT-4o-mini", "fail_only": "Flat prior"}
COL = {"pre_only": "#0072B2", "fused_rule": "#56B4E9", "fused_ml": "#009E73", "claude-sonnet-4-6": "#D55E00",
       "gpt-4o-mini": "#E69F00", "fail_only": "#999999"}
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": "#e5e5e5", "grid.linewidth": 0.6, "axes.axisbelow": True, "pdf.fonttype": 42})
ORDER = ["pre_only", "fused_rule", "fused_ml", "claude-sonnet-4-6", "gpt-4o-mini", "fail_only"]

# ---- Figure 1: P@1 and ECE by method, per corpus and pooled
fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))
groups = [("defects4j", "Defects4J\n(774 events)"), ("bugsinpy", "BugsInPy\n(493 events)"), ("pooled", "Pooled\n(1,267 events)")]
w = 0.13; x = np.arange(3)
for ax, metric, ttl in ((axes[0], "p1", "Precision@1 (higher is better)"), (axes[1], "ece", "ECE, 10 bins (lower is better)")):
    for i, m in enumerate(ORDER):
        vals = [D["per_corpus"][m][g][metric] if g != "pooled" else D["pooled"][m][metric] for g, _ in groups]
        bars = ax.bar(x + (i - 2.5) * w, vals, w * 0.92, color=COL[m], label=NAMES[m])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=5.6, rotation=90, color="#333")
    ax.set_xticks(x); ax.set_xticklabels([g[1] for g in groups]); ax.set_title(ttl, fontsize=9, loc="left")
    ax.set_ylim(0, 1.0 if metric == "p1" else 0.85)
axes[0].legend(ncol=2, fontsize=6.5, frameon=False, loc="upper left", bbox_to_anchor=(0, 1.0))
fig.tight_layout(); fig.savefig(f"{OUT}/fig1_headline.pdf"); fig.savefig(f"{OUT}/fig1_headline.png", dpi=300); plt.close(fig)

# ---- Figure 2: reliability diagrams (predictor, learned fusion, Claude), with bin counts
def llm_rows(l):
    recs = []
    for f in glob.glob(f"{llm_runs(l)}/*.json"):
        d = json.load(open(f)); conf = d["confidence_by_corpus_row"]; conf = ast.literal_eval(conf) if isinstance(conf, str) else conf
        sub = rows[rows.event_id == d["event_id"]]
        if len(conf) != len(sub): continue
        recs += list(zip(sub.real_defect.astype(int), map(float, conf)))
    a = np.array(recs); return a[:, 0], a[:, 1]
def rel(y, p):
    b = np.linspace(0, 1, 11); conf, frac, n = [], [], []
    for i in range(10):
        m = (p >= b[i]) & ((p < b[i + 1]) if i < 9 else (p <= b[i + 1]))
        if m.sum(): conf.append(p[m].mean()); frac.append(y[m].mean()); n.append(int(m.sum()))
    return np.array(conf), np.array(frac), np.array(n)
panels = [("pre_only", rows.real_defect.values, rows.score_pre_only.values), ("fused_ml", rows.real_defect.values, rows.score_fused_ml.values),
          ("claude-sonnet-4-6",) + llm_rows("claude-sonnet-4-6")]
fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7), sharey=True)
for ax, (m, y, p) in zip(axes, panels):
    c, f, n = rel(y, p); ece = D["pooled"][m]["ece"]
    ax.plot([0, 1], [0, 1], color="#999", lw=0.8, ls="--")
    ax.plot(c, f, "o-", color=COL[m], lw=2, ms=np.clip(np.sqrt(n) / 2.5, 3, 12).mean() * 0 + 5)
    ax.scatter(c, f, s=np.clip(n / 8, 8, 260), color=COL[m], alpha=0.35, edgecolor="none")
    ax.set_title(f"{NAMES[m]}  (ECE {ece:.3f})", fontsize=8.5, loc="left"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xlabel("Predicted probability"); ax.set_aspect("equal")
axes[0].set_ylabel("Observed defect fraction")
fig.text(0.5, -0.02, "Marker area is proportional to the number of candidate files in the bin; dashed line is perfect calibration.", ha="center", fontsize=7, color="#555")
fig.tight_layout(); fig.savefig(f"{OUT}/fig2_reliability.pdf", bbox_inches="tight"); fig.savefig(f"{OUT}/fig2_reliability.png", dpi=300, bbox_inches="tight"); plt.close(fig)

# ---- Figure 3: per-project P@1, predictor vs Claude Sonnet 4.6, Lang/Math/Time marked
tab = pd.DataFrame(D["per_project"]["table"]).sort_values("pre_only", ascending=False).reset_index(drop=True)
tab["label"] = tab.repo.str.replace("defects4j:", "D4J ").str.replace("bugsinpy:", "BIP ") + tab.n_events.map(lambda n: f" ({n})")
CLASSIC = {"defects4j:Lang", "defects4j:Math", "defects4j:Time"}
fig, ax = plt.subplots(figsize=(7.2, 6.4)); yy = np.arange(len(tab))
for i, r in tab.iterrows():
    ax.plot([r.pre_only, r["claude-sonnet-4-6"]], [i, i], color="#bbb", lw=1.2, zorder=1)
ax.scatter(tab.pre_only, yy, color=COL["pre_only"], s=34, zorder=3, label=NAMES["pre_only"])
ax.scatter(tab["claude-sonnet-4-6"], yy, color=COL["claude-sonnet-4-6"], s=34, marker="D", zorder=3, label=NAMES["claude-sonnet-4-6"])
ax.set_yticks(yy); ax.set_yticklabels(tab.label, fontsize=7.5); ax.invert_yaxis(); ax.set_xlim(0, 1.0); ax.set_xlabel("Precision@1 (events in parentheses)")
for lab, r in zip(ax.get_yticklabels(), tab.repo):
    if r in CLASSIC: lab.set_fontweight("bold")
ax.legend(frameon=False, fontsize=8, loc="lower left")
fig.tight_layout(); fig.savefig(f"{OUT}/fig3_per_project.pdf"); fig.savefig(f"{OUT}/fig3_per_project.png", dpi=300); plt.close(fig)

# ---- Figure 4: distractor sensitivity (ECE and P@1 vs k)
S = pd.DataFrame(D["sensitivity"]); S["method"] = S.method.replace({"llm_sonnet": "claude-sonnet-4-6", "llm_gpt4omini": "gpt-4o-mini"})
ks = ["2", "3", "4", "all"]
fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8))
for ax, metric, ttl in ((axes[0], "ece_10bin", "ECE (lower is better)"), (axes[1], "p1_mean", "Precision@1")):
    for m in ["pre_only", "fused_rule", "fused_ml", "claude-sonnet-4-6", "gpt-4o-mini"]:
        s = S[S.method == m].set_index("k").reindex(ks)
        ax.plot(range(4), s[metric], "o-", color=COL[m], lw=2, ms=5, label=NAMES[m])
    ax.set_xticks(range(4)); ax.set_xticklabels(["k = 2", "k = 3", "k = 4", "all files"]); ax.set_title(ttl, fontsize=9, loc="left"); ax.set_xlim(-0.2, 3.3)
    br = S[S.method == "pre_only"].set_index("k").reindex(ks).base_rate
    ax.set_xlabel("Candidate files per event", fontsize=8)
axes[0].legend(frameon=False, fontsize=7, loc="upper right"); fig.tight_layout(); fig.savefig(f"{OUT}/fig4_sensitivity.pdf"); fig.savefig(f"{OUT}/fig4_sensitivity.png", dpi=300); plt.close(fig)
print("wrote", sorted(os.listdir(OUT)))
