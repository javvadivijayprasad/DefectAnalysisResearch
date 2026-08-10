# Finalize bundle — pre-upload punch list

The assembler cannot reach the parquet corpus or the per-row scores CSV
because they live in WSL2 native filesystem (`~/paperF/...`), which is
outside the sandbox that assembled this bundle. **Run this checklist
before zipping and uploading to Zenodo.**

## 1. Copy parquet datasets from WSL

From a WSL2 Ubuntu shell:

```bash
cp ~/paperF/datasets/real_events*.parquet \
   /mnt/e/EB1A_Research/EB1_Master/06_Authorship/Research/PaperF_rebuild/zenodo_bundle_v1.0.0/datasets/
```

Verify:

```bash
ls -lh /mnt/e/EB1A_Research/EB1_Master/06_Authorship/Research/PaperF_rebuild/zenodo_bundle_v1.0.0/datasets/
# should list:
#   real_events.parquet
#   real_events_d4j.parquet
#   real_events_bip.parquet
#   README.md
```

## 2. Copy per-row scores CSV from WSL (if not already present)

```bash
cp ~/paperF/results/per_row_scores_real.csv \
   /mnt/e/EB1A_Research/EB1_Master/06_Authorship/Research/PaperF_rebuild/zenodo_bundle_v1.0.0/results/
```

If the file is not on disk yet, re-run:

```bash
python3 scripts/run_real_experiment.py
```

## 3. Verify bundle contents

```powershell
# From Windows PowerShell:
cd E:\EB1A_Research\EB1_Master\06_Authorship\Research\PaperF_rebuild\zenodo_bundle_v1.0.0
(Get-ChildItem -Recurse -File).Count      # expect ~25-30 files
"{0:N2} MB" -f ((Get-ChildItem -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
# expect ~10-50 MB (dominated by parquet + PDF)
```

## 4. Zip the bundle

Choose one:

```powershell
# PowerShell:
Compress-Archive -Path E:\EB1A_Research\EB1_Master\06_Authorship\Research\PaperF_rebuild\zenodo_bundle_v1.0.0\* `
                 -DestinationPath E:\...\zenodo_bundle_v1.0.0.zip
```

```bash
# WSL:
cd /mnt/e/EB1A_Research/EB1_Master/06_Authorship/Research/PaperF_rebuild
zip -r zenodo_bundle_v1.0.0.zip zenodo_bundle_v1.0.0/
```

## 5. Upload to Zenodo

- Log in to <https://zenodo.org>, create a **New Upload**.
- Upload the zip.
- Metadata:
  - Title: *Post-Execution Defect Attribution on Real-World Defects — Reproducibility Bundle v1.0.0*
  - Creator: Javvadi, Vijay Prasad — ORCID 0009-0004-1192-6906
  - Affiliation: Independent Researcher, Plainsboro, NJ, USA
  - Version: `v1.0.0`
  - License: Apache-2.0
  - Communities: (optional) `software`
  - Related identifiers: link to companion paper DOI once assigned by JSS.
- Publish. Record the returned **Concept DOI** and **Version DOI**.

## 6. Replace DOI placeholders

The following placeholders must be replaced with the real DOIs:

| Placeholder            | Files                                            |
| ---------------------- | ------------------------------------------------ |
| `[ZENODO-DOI-HERE]`    | `README.md` (BibTeX block, URL)                  |
| `[PAPER-DOI-HERE]`     | `README.md`, `CITATION.cff`                      |
| `[ZENODO-DOI-HERE]`    | `paper/paperF_JSS.tex` — Data availability section |

Use ripgrep to find every occurrence:

```bash
grep -rn "ZENODO-DOI-HERE\|PAPER-DOI-HERE" .
```

## 7. Recompile the manuscript

```bash
cd paper
pdflatex paperF_JSS.tex && bibtex paperF_JSS && pdflatex paperF_JSS.tex && pdflatex paperF_JSS.tex
```

Verify the Data Availability section now shows the resolved Zenodo DOI.

## 8. Submit to JSS

Use the recompiled PDF for submission. Upload `paperF_JSS.pdf`,
`cover_letter_JSS.pdf`, `highlights.txt`, and reference the Zenodo DOI in
the Elsevier submission form's *Data & code* field.

Only after all 8 steps: submit.
