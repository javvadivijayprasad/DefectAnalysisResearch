# LLM file-level attribution baseline (Paper F)

`scripts/llm_baseline.py` adds an EXTERNAL fifth method next to `pre_only`,
`fail_only`, `fused_rule`, `fused_ml`: an LLM ranks each failing event's
candidate files and assigns each a probability of being defective. Results are
scored with the paper's own metric code (imported from
`scripts/run_real_experiment.py`), so P@1/P@3/R@5/MRR/triage/ECE are computed
identically to Table 1 of the paper.

## Design facts (for the paper text)

- **Unit of prompting**: one prompt per EVENT (1,323 prompts total), each
  showing that event's full candidate list (~5.28 files/event; 6,988 rows).
- **LOPO**: the LLM has no training phase and never sees data from any corpus
  project, so leave-one-project-out is satisfied by construction.
- **Information parity**: the LLM observes exactly the columns `fused_ml`
  consumed — event-level failure signal (`exception_type`, `exception_idx`,
  `http_status`, the six change-topology flags, `historical_flake_rate`) plus
  the per-file 7-feature repo-history list (`commit_count`,
  `unique_developers`, `lines_added`, `lines_deleted`, `code_churn`,
  `file_age_days`, `commit_frequency`) and the candidate file paths and
  project name. It does NOT see labels, file contents, diffs, test source, or
  fix commits. (Caveat worth stating in the paper: in the real corpus the
  failure signal is nearly degenerate — `exception_type` is always
  `AssertionError`, `http_status`=0, flake=0 — so every method's usable signal
  is effectively paths + history features.)
- **Order-leak guard**: the corpus lists fix files before distractors, so
  candidates are shown to the LLM in a deterministic per-event shuffle
  (SHA-256 of `event_id`), never corpus order. Parse-failure fallbacks use the
  shuffled order too.
- **Scoring**: per-row score = the LLM's raw confidence (used as-is for ECE).
  For ranking metrics only, `1e-6 × rank-position` is subtracted so the LLM's
  explicit ranking breaks ties among equal confidences; everything then goes
  through the paper's `evaluate_per_event` / `summarize` (random tie-break
  seed 42, triage 3 s/file, 10-bin ECE), same as the four internal methods.
- **Robustness**: strict-JSON output with fence-stripping; one retry on parse
  failure; a second failure records the event as `unparsed_fallback`
  (presented order, uniform 1/n confidence) and the rate is reported in
  `summary.csv` — never hidden.
- **Determinism**: temperature 0, deterministic prompts, deterministic pilot
  sample (seed 42). Reruns resume from per-event files and skip finished work.

## Commands (PowerShell, from the repo root)

```powershell
cd "E:\EB1A_Research\EB1_Master\06_Authorship\Research\Defect analysis Reserch"

# 0. Sanity checks (no API key needed)
python scripts\llm_baseline.py --self-test          # ECE vs hand-computed example
python scripts\llm_baseline.py --dry-run --pilot 30 # fake backend, pipeline only

# 1. Set the key for this shell session
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 2. Cost preview (no calls made)
python scripts\llm_baseline.py --backend anthropic --model claude-sonnet-4-6 --estimate-only

# 3. Pilot: 30 events stratified across the 33 projects (~$0.15, ~1 min)
python scripts\llm_baseline.py --backend anthropic --model claude-sonnet-4-6 --pilot 30

# 4. Full run: 1,323 events (~$6, roughly 15-30 min at --workers 4)
python scripts\llm_baseline.py --backend anthropic --model claude-sonnet-4-6 --workers 4

# Optional secondary backend
$env:OPENAI_API_KEY = "sk-..."
python scripts\llm_baseline.py --backend openai --model gpt-4o-mini --workers 4
```

Estimated full-run size (chars/4 heuristic, printed again before each run):
~875K input + ~228K output tokens → about **$6 for claude-sonnet-4-6**
(3/15 per MTok) or **$0.27 for gpt-4o-mini**. Runtime scales with rate limits;
if you hit 429s, lower `--workers` or add `--sleep 0.5`. The run is fully
resumable — just re-execute the same command and it continues.

Useful extras: `--limit 5` (smoke-test 5 real calls first), `--score-only`
(recompute metrics from existing per-event files), `--pilot N` (any N).

## Outputs

```
results\llm_baseline\<model>\runs\<event_id>.json   # per-event: prompt order, raw response, parse status, usage
results\llm_baseline\<model>\summary.csv            # P@1, P@3, R@5, MRR, triage_s, ECE + parse-failure stats + token totals
results\llm_baseline\<model>\summary.json           # same, JSON
results\llm_baseline\<model>\per_event_metrics.csv  # per-event metrics (same schema as per_event_metrics_real.csv)
results\llm_baseline\<model>\per_project.csv        # per-repo breakdown incl. per-repo ECE
```

Dry-run output goes to a separate `<model>_dryrun\` directory, is gitignored,
and must never be reported — it validates plumbing only.

## What to paste back for integration

After the full run, paste (or commit) these three files and the console tail:

1. `results\llm_baseline\claude-sonnet-4-6\summary.csv`
2. `results\llm_baseline\claude-sonnet-4-6\per_project.csv`
3. the `parse_failure_rate` / `n_ok_after_retry` lines from the console
   (also inside summary.csv)

That is sufficient to add the LLM row to the paper's headline table and the
per-project analysis, with the parse-failure rate reported alongside.
