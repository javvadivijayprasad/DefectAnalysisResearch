@echo off
REM Build paper7_defect_attribution.pdf (Windows).

set TEX=paper7_defect_attribution

pdflatex -interaction=nonstopmode %TEX%.tex
if errorlevel 1 goto :error
bibtex %TEX%
pdflatex -interaction=nonstopmode %TEX%.tex
pdflatex -interaction=nonstopmode %TEX%.tex

echo.
echo Build complete: %TEX%.pdf
goto :eof

:error
echo.
echo Build failed. See %TEX%.log for details.
exit /b 1
