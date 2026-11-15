# v3feat: the v3 changes feature by feature (run_log section H)

30 reports, 279 claims ({'unsupported:horizontal_bar': 7, 'alias': 11, 'plain': 48, 'two_numbers': 16, 'cross_chart': 5, 'dual': 36, 'caption': 9, 'peak': 42, 'fraction': 17, 'panels': 27, 'range': 12, 'log': 10, 'unsupported:heatmap': 5, 'error_rate': 3, 'band': 10, 'unsupported:scatter': 3, 'unsupported:histogram': 5, 'errbar': 6, 'unsupported:box': 7}). Readers: real ocr_pixel + simulated DePlot / VLM table / VLM crop, so verdicts test the logic, not real VLM reading on these charts.

## Whole split, v2 switches vs v3 switches

| | v2 (switches off) | v3 |
|---|---|---|
| coverage | 77.3% | 64.2% |
| accuracy_when_decided | 37.2% | 96.6% |
| wrong_flag_rate | 14.7% | 1.5% |
| missed_errors | 1.1% | 3.6% |
| n_flagged | 34 | 68 |
| retrieval_top1 | 33.6% | 97.7% |

## Claims by feature (v3; the v2 row is the same claims with the switches off)

| feature | claims | decided | right when decided | wrong flags | missed errors | note |
|---|---|---|---|---|---|---|
| alias | 11 | 9 of 11 (82%) | 9 of 9 (100%) | 0 | 0 |  |
| alias (v2) | 11 | 10 of 11 (91%) | 0 of 10 (0%) | 0 | 0 |  |
| band | 10 | 10 of 10 (100%) | 10 of 10 (100%) | 0 | 0 |  |
| band (v2) | 10 | 10 of 10 (100%) | 7 of 10 (70%) | 0 | 0 |  |
| caption | 9 | 8 of 9 (89%) | 8 of 8 (100%) | 0 | 0 |  |
| caption (v2) | 7 | 7 of 7 (100%) | 0 of 7 (0%) | 0 | 0 |  |
| cross_chart | 5 | 3 of 5 (60%) | 3 of 3 (100%) | 0 | 0 |  |
| cross_chart (v2) | 5 | 3 of 5 (60%) | 0 of 3 (0%) | 0 | 0 |  |
| dual | 36 | 0 of 36 (0%) | - | 0 | 0 |  |
| dual (v2) | 36 | 33 of 36 (92%) | 11 of 33 (33%) | 0 | 1 |  |
| errbar | 6 | 6 of 6 (100%) | 6 of 6 (100%) | 0 | 0 |  |
| errbar (v2) | 6 | 6 of 6 (100%) | 4 of 6 (67%) | 0 | 0 |  |
| error_rate | 3 | 2 of 3 (67%) | 2 of 2 (100%) | 0 | 0 |  |
| error_rate (v2) | 3 | 2 of 3 (67%) | 0 of 2 (0%) | 0 | 0 |  |
| fraction | 17 | 16 of 17 (94%) | 15 of 16 (94%) | 0 | 1 |  |
| fraction (v2) | 17 | 17 of 17 (100%) | 7 of 17 (41%) | 3 | 0 |  |
| log | 10 | 10 of 10 (100%) | 8 of 10 (80%) | 0 | 1 |  |
| log (v2) | 10 | 6 of 10 (60%) | 4 of 6 (67%) | 0 | 0 |  |
| panels | 27 | 24 of 27 (89%) | 21 of 24 (88%) | 1 | 2 |  |
| panels (v2) | 27 | 14 of 27 (52%) | 0 of 14 (0%) | 0 | 0 |  |
| peak | 42 | 28 of 42 (67%) | 28 of 28 (100%) | 0 | 0 |  |
| peak (v2) | 21 | 7 of 21 (33%) | 2 of 7 (29%) | 0 | 0 |  |
| range | 12 | 9 of 12 (75%) | 9 of 9 (100%) | 0 | 0 |  |
| range (v2) | 12 | 0 of 12 (0%) | - | 0 | 0 |  |
| two_numbers | 16 | 10 of 16 (62%) | 10 of 10 (100%) | 0 | 0 |  |
| two_numbers (v2) | 8 | 7 of 8 (88%) | 0 of 7 (0%) | 2 | 0 |  |
| unsupported:box | 7 | 2 of 7 (29%) | 2 of 2 (100%) | 0 | 0 |  |
| unsupported:box (v2) | 7 | 7 of 7 (100%) | 2 of 7 (29%) | 0 | 0 |  |
| unsupported:heatmap | 5 | 0 of 5 (0%) | - | 0 | 0 |  |
| unsupported:heatmap (v2) | 4 | 4 of 4 (100%) | 0 of 4 (0%) | 0 | 0 |  |
| unsupported:histogram | 5 | 0 of 5 (0%) | - | 0 | 0 |  |
| unsupported:histogram (v2) | 5 | 5 of 5 (100%) | 0 of 5 (0%) | 0 | 0 |  |
| unsupported:horizontal_bar | 7 | 1 of 7 (14%) | 1 of 1 (100%) | 0 | 0 |  |
| unsupported:horizontal_bar (v2) | 7 | 6 of 7 (86%) | 3 of 6 (50%) | 0 | 0 |  |
| unsupported:scatter | 3 | 0 of 3 (0%) | - | 0 | 0 |  |
| unsupported:scatter (v2) | 3 | 2 of 3 (67%) | 2 of 2 (100%) | 0 | 0 |  |

## Parsing (rules H6, H10)

| claims | parsed right (v3) | parsed right (v2) |
|---|---|---|
| range | 12 of 12 (100%) | 0 of 12 (0%) |
| two_numbers | 16 of 16 (100%) | 0 of 16 (0%) |
| peak | 42 of 42 (100%) | 3 of 42 (7%) |
| caption | 9 of 9 (100%) | 7 of 9 (78%) |

## TA-card notes (rules H1-H3)

- Wrong figure number noted: 11 of 12 (92%); note on a right figure number: 0 of 86 (0%).
- Mix-up explained on flagged mix-ups: 3 of 8 (38%); on other flags: 8 of 60 (13%).
- Conflict notes: 20.

## Unsupported charts and dual axes (rule H15)

- Claims on them handed to the TA: v3 60 of 63 (95%), v2 5 of 62 (8%); flags on them: v3 1, v2 6 (wrong: v3 0, v2 0).

## ocr_pixel (real) on the new chart kinds (rules H9, H12, H14)

| chart kind | asked | answered | badly wrong (> 5% of the axis; log axes in log units) |
|---|---|---|---|
| band | 6 | 4 of 6 (67%) | 0 of 4 (0%) |
| band (vector) | 4 | 4 of 4 (100%) | 0 of 4 (0%) |
| cross_pair | 9 | 8 of 9 (89%) | 0 of 8 (0%) |
| cross_pair (vector) | 5 | 4 of 5 (80%) | 0 of 4 (0%) |
| errbar | 2 | 2 of 2 (100%) | 0 of 2 (0%) |
| errbar (vector) | 3 | 3 of 3 (100%) | 0 of 3 (0%) |
| fraction | 7 | 7 of 7 (100%) | 0 of 7 (0%) |
| fraction (vector) | 7 | 7 of 7 (100%) | 0 of 7 (0%) |
| log | 18 | 12 of 18 (67%) | 0 of 12 (0%) |
| log (vector) | 4 | 4 of 4 (100%) | 0 of 4 (0%) |
| panels | 31 | 28 of 31 (90%) | 0 of 28 (0%) |
| panels (vector) | 13 | 13 of 13 (100%) | 0 of 13 (0%) |
| plain | 8 | 7 of 8 (88%) | 0 of 7 (0%) |
| plain (vector) | 19 | 17 of 19 (89%) | 0 of 17 (0%) |
| unsupported:box (vector) | 1 | 1 of 1 (100%) | 0 of 1 (0%) |
| unsupported:horizontal_bar | 1 | 0 of 1 (0%) | - |

## v3feat vs its one-column raster twin

- Gold claims found as sentences: v3feat 279 of 279 (100%), one-column raster twin 279 of 279 (100%) (exact text); gold claim sentences read with at most small OCR differences (similarity >= 90 of 100): 250 of 250 (100%).
- Same verdict on claims found in both: 264 of 279 (95%).
- Two-column reports: claims found 134 of 134 (100%) (twin 134 of 134 (100%)). Vector-figure reports: 114 of 114 (100%) (twin 114 of 114 (100%)).
- Vector-figure reports, figures measured for at least one claim: v3feat 35, raster twin 35.

## v3feat vs its scanned twin

- Gold claims found as sentences: v3feat 279 of 279 (100%), scanned twin 255 of 279 (91%) (exact text); gold claim sentences read with at most small OCR differences (similarity >= 90 of 100): 241 of 250 (96%).
- Same verdict on claims found in both: 115 of 255 (45%).
