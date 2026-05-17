# Paper 9 — Reviewer Report

**Title:** Post-Execution Defect Attribution: Fusing Test-Failure Signals with SHAP-Explained Repository Priors for Practitioner-Actionable Triage
**Filename note:** the .tex is named `paper7_defect_attribution.tex` for historical reasons; this is **Paper 9** of the 9-paper series.
**Target venue (inferred):** ICSE / ICST / ASE (IEEEtran conference, ~10 pages)

**Verdict: MAJOR (1–2 weeks of fixes)** — strong core idea (post-execution attribution + self-healing interlock), solid empirical design, but blocked by missing figures/tables, weak baselines, and a "ghost-written" user study.

---

## Headline claims

* Fused post-execution methods achieve higher precision@1 than pre-execution prediction (paper 4 baseline) and failure-only triage; reported with 95% bias-corrected bootstrap CIs.
* Expected Calibration Error (ECE) improves under fused configurations.
* Simulated mean triage time reduced by concentrating true positives near top of ranked file lists.
* SHAP-attributed local contributions map repo features (commit_count, unique_developers, churn) to concrete developer actions.

## Strengths

1. Crisp problem framing — three-axis novelty (grounding, category structure, explanation granularity).
2. Practical taxonomy — 8 categories (real_defect, validation_failure, uncoordinated_contract_change, stale_fixture, flake, environmental, self_healed_hidden_defect, unclear) each maps to a concrete action.
3. **Self-healing interlock is novel** — explicit `self_healed_hidden_defect` category captures cases where self-healing masks real defects. Genuine safety contribution; reviewer hasn't seen this elsewhere.
4. Governance-preserving feedback loop — local JSONL persistence (no exfil) + versioned model retraining. Mature design for enterprise auditability.
5. Strong reproducibility posture — code + data referenced via Zenodo DOI; SZZ + issue-text hybrid labelling with sensitivity analysis.

## Major gaps

1. **Critical baselines missing** — no comparison to (a) SZZ blame-based file attribution, (b) FixerCache / SapientX style failure categorisation, (c) LLM-based root-cause analysis (GPT-4 on stack trace + diff). The two baselines (`pre_only`, `fail_only`) are strawmen.
2. **Ablation results in prose only** — §4.3 mentions ablations (no self-healing interlock, no diff features, no SHAP) but no numerical table. Need Table 2 with prec@1 / recall@5 / macro-F1 / ECE per ablation, with significance tests.
3. **User study is ghost-written** — line 195 promises "small user study sketched below" measuring developer-confidence gain from SHAP; no protocol, no N, no results. Either execute or remove the claim.
4. **Threats-to-validity shallow** — SZZ noise mitigation (hybrid labelling, tangled-change filtering) acknowledged but not quantified; flake-leakage temporal split not specified; generalisation to small / private / polyglot codebases flagged but no follow-up plan.
5. **Claims unverifiable from text** — §5 references Table 1 (`headline_metrics.tex`) inline-not-embedded and Figures 1, 2, 4 not present in submission. Reader cannot verify "fused dominates pre and fail" claim.
6. **Reproducibility cracks** — paper 4 model artefact assumed available, no DOI / archive link given. Build scripts (`scripts/build_dataset.py`) referenced but not included. Datasets directory documented but not shipped.
7. **Related work omissions** — Zimmermann et al. (2011), Schröter et al. (2006) on SZZ limitations, Carver et al. on flake retry detection, Luo et al. (2022) and Gambi et al. (2021) on test-failure analysis.
8. **Series coupling too tight** for standalone submission — heavy "Paper 4 / Paper 2" references.

## Minor issues

* **Internal inconsistency** — abstract says "8 mutually exclusive categories"; §3 lists 8; lines 197–200 then describe `validation_failure` as covering 4 sub-modes. Are sub-modes part of the 8 or separate? Restructure as sub-taxonomy.
* Sufficiency claim (line 102) — paper 4's feature set "sufficient" because cross-model Kendall τ agrees, but no formal ablation in *this* paper.
* "30 seconds per inspected file" assumption (line 156) for Mean Triage Time — no empirical justification.
* Prose: line 38 awkward; line 68 reads more like design fiction than spec; line 227 wordy.
* `D'Ambros2012` apostrophe may not render in all LaTeX builds.
* `Herzig2015` missing DOI.

## Cross-paper coupling

* References paper 4 (SHAP layer reuse) + paper 2 (self-healing) — either provide as supplementary preprints or replace with citable references. (See §S5 in `SUBMISSION_REVIEW.md`.)
* Shared Zenodo DOI mentioned in preamble but not in the paper body — add explicit citation.
* Series-formalism: "defect-attribution-service", "test-prioritization-service", "test-case-generation-service" used informally — formalise in a glossary.
* `ai-quality.config.yaml` referenced but not included.
* Filename `paper7_defect_attribution.tex` is a historical artefact — rename to `paper9_defect_attribution.tex`.

## Concrete fix list

1. **Title:** add "(Paper 9 of the TestForge AI series)" or similar context line. Or, for standalone submission, remove series language entirely.
2. **§2.3 Related Work:** add "Defect-attribution baselines" subsection — SZZ blame (Sliwerski et al. 2005), FixerCache (Zeller et al. 2021), SapientX (Lampropoulos et al. 2020), LLM stack-trace analysis. Discuss why they aren't directly comparable.
3. **§4.1 Methods:** add fifth baseline `lgreg_baseline` — logistic regression on exception type + HTTP status + flake rate + diff flags, no repo features. Tests the contribution of the repo prior specifically.
4. **§4.3 Ablations:** replace prose with numerical Table 2:
   ```
   Method                            | Prec@1 (±CI) | Recall@5 | Macro-F1 | ECE
   fused_rule (full)                 | …            | …        | …        | …
   - no self-healing interlock       | …            | …        | …*       | …
   - no diff features                | …            | …        | …*       | …
   - no SHAP attribution             | …            | …        | …        | …
   ```
   Footnote: `*` significant at p < 0.05 (Wilcoxon signed-rank).
5. **§4.4 User study:** either execute (protocol, N, DV = developer-confidence rating, IV = SHAP-on/off, results, analysis) or replace with: "Future work: controlled user study to measure SHAP-driven confidence gain."
6. **§5 Results:** embed Table 1 inline (not via `\input{...}`); show numeric values reviewers can verify.
7. **Figures 1, 2, 4:** embed as PNG or convert to TikZ/pgfplots; or include in supplementary with explicit pointers.
8. **Reproducibility footnote in abstract or intro:** "Code, datasets, paper 4 model checkpoint, scripts at Zenodo DOI [INSERT]."
9. **§3.2 SHAP fallback (line 106):** clarify what "analytic per-feature contribution" means — linear-model SHAP closed-form? Cite reference.
10. **§3 Taxonomy:** restructure `validation_failure` 4 sub-modes (`rule_defect`, `stale_fixture`, `contract_change`, `app_code_defect`) as explicit sub-taxonomy. Clarify whether macro-F1 in Table 1 is over 8 or 11 categories.
11. **§5 Triage time:** justify 30-s-per-file assumption (cite empirical study or report sensitivity to alternative timings).
12. **§T-T-V SZZ noise:** quantify: how many cases filtered by tangled-change rule? What changes in metrics with/without filtering?
13. **§T-T-V flake split:** specify "X months held out for flake-leakage protection."
14. **Acknowledgments:** acknowledge SZZ authors (Sliwerski / Zimmermann / Zeller).
15. **Series coupling:** for ICSE submission, remove "in this series" and replace with citable preprint refs (§S5). For ICST industry track, keep but provide preprints as supplementary.
16. **Filename:** rename `paper7_defect_attribution.tex` → `paper9_defect_attribution.tex`.
17. **Zenodo DOI:** apply canonical from §S1 in `SUBMISSION_REVIEW.md`.

---

**Recommendation:** with the user study properly executed and the missing baselines added, this is the **strongest paper of the series**. The self-healing interlock is genuinely novel and the governance-preserving feedback loop is mature design. Push hard on the missing user study — it is the single highest-leverage fix.
