# Real-world sample reports

Seven reports written the way students actually write them, for testing the verifier on what the generated splits
never contain. Every one is rebuilt by `python scripts/real/make_sample_reports.py` (the two LaTeX ones need
pdflatex with IEEEtran and pgfplots).

| Folder | What it tests |
|---|---|
| `01_latex_ieee_two_column` | IEEE two-column LaTeX, figures included as matplotlib PDFs (vector), hyphenated words across lines, ligatures, the LaTeX minus sign and `\times10^{-4}`, "Fig. 1." captions, past tense, "lower than", a fall in loss, number words |
| `02_word_excel_charts` | A Word-style report: Excel / Google Sheets look charts (no frame, so the y-axis cannot be read), captions "Figure 1 –", "Fig 2:" and one written above its chart, a chart with no caption, "~85%", ">85%", "≈81%", "(see Table 2)", "Dr." |
| `03_tricky_language` | Readable charts with hard sentences: negations, "drops by", "trails", "loss improves by", "improves by 8.2%" (points or relative?), "about 1000 images per second", "84-86%", "between", "±", number words, "after 5 epochs", "VGG-16's accuracy is" |
| `04_similar_names_and_splits` | ResNet-18 / 34 / 50 / 101 / 152, VGG-16 / 19, CIFAR-10 / CIFAR-100, and separate training, validation and test charts |
| `05_hard_charts` | Two y-axes, a "1e-4" multiplier above the axis, a log scale, a seaborn style, horizontal bars, a two-panel figure |
| `06_scanned_copy` | Report 03 printed and scanned: image-only pages, slightly rotated, JPEG |
| `07_latex_pgfplots_full_report` | A three-page LaTeX article with pgfplots charts (ticks inside the frame, grid lines), setup numbers that must be skipped, "Figs. 1 and 2", a repeated sentence, a claim inside a caption |

Each folder has `report.pdf`, `truth.json` (the true value of every plotted point, per figure number and panel) and
`expected.json` (every sentence with a number: `true`, `false`, `negated`, `no_figure` or `setup`, the verdicts
that are acceptable, the harmful ones, and why).

## How to use them

- **In the web app.** Upload any `report.pdf` in ReportLens Lite and compare each verdict with `expected.json`.
  A true claim may be CONSISTENT or NOT_SURE but never MISMATCH; a false one MISMATCH or NOT_SURE but never
  CONSISTENT; a negated sentence is always NOT_SURE.
- **From the command line.**

  ```bash
  python scripts/real/check_samples.py                                    # v5, stand-in readers, no model loaded
  python scripts/real/check_samples.py -c configs/exp/local_real.yaml     # the config the web app used before v4
  python scripts/real/check_samples.py --readers real                     # with the real models (stop the web app first)
  ```

  "Stand-in readers" return the true chart values in place of DePlot and the two Qwen tools, while the real
  OCR+pixel reader runs, so the run tests everything except model reading. The exit code is 1 if any sentence gets a
  harmful verdict. `tests/test_sample_reports.py` runs reports 03 and 04 this way.
