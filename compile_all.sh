#!/usr/bin/env bash
# Build paper7_defect_attribution.pdf (macOS / Linux).
set -eu

TEX=paper7_defect_attribution

pdflatex -interaction=nonstopmode "${TEX}.tex"
bibtex "${TEX}"
pdflatex -interaction=nonstopmode "${TEX}.tex"
pdflatex -interaction=nonstopmode "${TEX}.tex"

echo
echo "Build complete: ${TEX}.pdf"
