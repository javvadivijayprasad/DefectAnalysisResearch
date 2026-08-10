# QC Audit — Paper F for Journal of Systems and Software (JSS)

Audit date: 2026-08-09
Author: Vijay Prasad Javvadi (Independent Researcher, Plainsboro NJ USA, ORCID 0009-0004-1192-6906)
Files: `paperF_JSS.tex` (22pp, 675,920 B PDF), `cover_letter_JSS.tex` (2pp PDF), `paperF_references.bib`, `figures/` (4 PNGs).

---

## 1. Verdict

**MINOR CONCERNS.** No blocking issues. The manuscript compiles cleanly (0 errors, 0 undefined refs/cites, 1 overfull hbox at 2.61 pt — well under the 20 pt threshold), all headline numbers are internally consistent with the ground-truth spec, stale synthetic-era numbers appear only in the Discussion contrast paragraph as intended, and venue targeting is correct. Two Elsevier-required author-facing artefacts (**Highlights** and a **CRediT authorship contribution statement**) are missing from the .tex; both are trivial to add. Word count (~4,843) sits below JSS's typical 6,000–9,000 range but is not disqualifying.

## 2. Venue targeting

- `\journal{Journal of Systems and Software}` present at line 23 of `paperF_JSS.tex`.
- Cover letter (lines 15–20) addressed to *"Professors Paris Avgeriou and David Shepherd, Co-Editors-in-Chief, Journal of Systems and Software, Elsevier"* — names spelled correctly, no other editors referenced.
- Grep for `STVR|Discover|Scientific Reports|Nature|Springer` across both documents: **0 matches**. No leftover cross-venue text.

## 3. Number consistency

Grep counts across `paperF_JSS.tex`:

| Number | Count | Status |
|---|---|---|
| `1{,}323` (events) | 12 | present |
| `6{,}988` (rows) | 5 | present |
| `5.28` (avg files/event) | 2 | present |
| `0.231` (real-defect fraction) | 1 | present |
| `LOPO` | 29 | present |
| `33 projects` | 5 | present |
| `0.7770` p@1 pre_only | 7 | present |
| `0.2494` p@1 fail_only | 4 | present |
| `0.7800` p@1 fused_rule | 6 | present |
| `0.7475` p@1 fused_ml | 7 | present |
| `0.0209` ECE pre_only | 7 | present |
| `0.7689` ECE fail_only | 5 | present |
| `0.0626` ECE fused_rule | 5 | present |
| `0.0326` ECE fused_ml | 5 | present |

Stale numbers audit — must appear ONLY in Discussion:
- `6{,}000`, `0.9398`, `0.9443` all occur exactly once, all on **line 236** (Discussion §5.1 flipped-finding paragraph). Correct.
- `296,457`, `0.0157`, `0.0936`, `0.0886`, `0.3579` — **0 occurrences**. Clean.
- No `Dr.` anywhere in either .tex.

## 4. Author identity

Verified in `paperF_JSS.tex` lines 31–34 and `cover_letter_JSS.tex` lines 6–12: name, affiliation, city/state/country, email, ORCID all correct. No "Dr." title.

## 5. JSS format compliance

| Item | Status |
|---|---|
| `\documentclass[preprint,12pt]{elsarticle}` | ✓ |
| `\author[1]{...}` + `\affiliation[1]{...}` Elsevier syntax | ✓ |
| `\bibliographystyle{elsarticle-num}` | ✓ |
| Structured abstract (Context/Objective/Method/Results/Conclusion) | ✓ |
| Keywords block | ✓ |
| **Highlights (3–5 bullets ≤ 85 chars)** | ✗ **MISSING** — needed as `highlights.txt` at submission |
| **CRediT authorship contribution statement** | ✗ **MISSING** — JSS requires it |
| Data availability statement | ✓ (§Declarations, Zenodo-at-acceptance) |
| Funding statement | ✓ |
| Conflict of interest statement | ✓ |
| AI use disclosure (Elsevier 2024/25 policy) | ✓ (Acknowledgements + cover letter) |
| Word count (JSS full paper: ~6000–9000) | ⚠ **4,843** (approx via `detex | wc -w`) — under target but not blocking |

## 6. Figure integrity

Four PNGs in `figures/`, all referenced exactly once each:
- `fig_headline_bars.png` → `fig:headline` (line 182)
- `fig_ece_bars.png` → `fig:ece` (line 195)
- `fig_reliability.png` → `fig:reliability` (line 202)
- `fig_per_repo_precision.png` → `fig:per_repo` (line 215)

Captions are all informative multi-sentence. Numbering contiguous 1–4.

## 7. Bibliography

- 38 `@`-entries in `paperF_references.bib`.
- Defects4J (`just2014defects4j`) ✓ and BugsInPy (`widyasari2020bugsinpy`) ✓ both fully populated.
- **BibTeX warnings (7, non-blocking):** empty `pages` in yang2024llmao, shahini2024conformal, hong2024atlassian, parry2025systemic; empty `journal` in abreu2009spectrum, niculescu2005predicting, herzig2013. Reviewers may nit these — worth a 10-minute pass to fill in.
- 0 undefined citations reported by BibTeX or LaTeX.

## 8. Compile status

Re-ran `pdflatex → bibtex → pdflatex → pdflatex` from a clean scratch copy in `/tmp`. Result:
- **0 errors, 0 undefined refs, 0 undefined cites**
- 1 overfull hbox at **2.61 pt** (output routine, cosmetic; well under 20 pt gate)
- Underfull hbox / font-shape substitution notes are LaTeX-standard cosmetic warnings only
- **Output: 22 pages, 675,920 bytes**

## 9. Loose-ends punch list (must-do before submit)

**Elsevier-required (BLOCKING at submission portal):**
1. **Highlights** — create `highlights.txt` with 3–5 bullets, each ≤ 85 characters. Suggested:
   - `1,323 real Defects4J+BugsInPy bugs evaluated under Leave-One-Project-Out`
   - `Machine-learned fusion loses 2.95 pp to pre-execution baseline on real data`
   - `Pre-execution defect priors are exceptionally well-calibrated (ECE 0.0209)`
   - `Reversal of the fused-ML advantage previously reported on synthetic corpora`
   - `Reproducibility bundle: LOPO corpus, four methods, per-event metrics, figures`
2. **CRediT statement** — add before Declarations, single-author full-scope:
   *"Vijay Prasad Javvadi: Conceptualization, Methodology, Software, Formal analysis, Investigation, Data curation, Writing – original draft, Writing – review & editing, Visualization."*

**Reproducibility / claim-support (needed to honor promises in §Declarations and cover letter):**
3. Zenodo bundle upload — event corpus (`events_real.parquet` or the parquet you build), four method impls, `per_event_metrics_real.csv`, figure scripts, `summary_real.json`. DOI must be inserted into the Data Availability paragraph in the camera-ready.
4. GitHub repo push + tagged release matching the Zenodo snapshot.

**Nice-to-have but not blocking:**
5. Fill 7 empty `pages`/`journal` fields in `paperF_references.bib` (yang2024llmao, shahini2024conformal, hong2024atlassian, parry2025systemic, abreu2009spectrum, niculescu2005predicting, herzig2013).
6. Consider padding to ~6,000 words (JSS-typical) via one added subsection — e.g., an operational-implications case study or a language-stratified LOPO ablation. Optional.
7. **Graphical abstract** — Elsevier accepts and encourages; not required. `fig_ece_bars.png` would work with minor annotation.
8. Author photo — JSS does not require; skip.
9. Supplementary materials — the Zenodo bundle satisfies this; no separate SI PDF needed.

---

## Recommendation

**Submit tomorrow** is fine *only after* items 1 and 2 (Highlights + CRediT) are added — both are <30-minute edits. Item 3 (Zenodo DOI) is promised as "at acceptance" in the manuscript, so it can wait, but the actual code+data snapshot should be prepared this week so a DOI can be minted immediately if the paper is accepted. Everything else is polish. The manuscript itself is scientifically clean, the reversal-and-calibration framing is honest and defensible, and there are no stale numbers or wrong-venue artefacts.
