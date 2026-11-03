# Report

- `report.pdf`: the report (about 15 pages). Source: `report.tex`.
- `figures/`: the figures, drawn by `make_figures.py` from the numbers in `../results/` (no model is called).

Rebuild: `python report/make_figures.py` (needs matplotlib), then `pdflatex report.tex` twice from this folder.
