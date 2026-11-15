# A reader from a second model family (run_log section I)

Model: IBM Granite Vision 4.1 4B (`ibm-granite/granite-vision-4.1-4b`), run locally (Apple M4, MPS, bfloat16). `vlm2_crop` asks it the same crop question as `vlm_crop`; `vlm2_table` uses its chart-to-CSV task.

## I1: the new tools on the calibration charts (live calls to the new model, the rest from the cache)

| situation | tool | points (charts) | answers | answers at x without a tick label | badly wrong (> 5% of the axis) | median error |
|---|---|---|---|---|---|---|
| line|hard | ocr_pixel | 749 (20) | 41.7% | 22.6% | 1.3% | 0.16% |
| line|hard | deplot | 749 (20) | 54.7% | 9.0% | 6.6% | 0.23% |
| line|hard | vlm_table | 749 (20) | 54.1% | 8.2% | 33.6% | 2.40% |
| line|hard | vlm_crop | 749 (20) | 100.0% | 100.0% | 33.5% | 2.61% |
| line|hard | vlm2_crop | 749 (20) | 100.0% | 100.0% | 29.1% | 1.19% |
| line|hard | vlm2_table | 749 (20) | 97.7% | 95.3% | 32.5% | 2.55% |
| bar|hard | ocr_pixel | 228 (19) | 61.4% | 57.0% | 0.7% | 0.16% |
| bar|hard | deplot | 228 (19) | 93.9% | 89.2% | 2.8% | 0.30% |
| bar|hard | vlm_table | 228 (19) | 93.4% | 88.2% | 21.6% | 1.13% |
| bar|hard | vlm_crop | 228 (19) | 100.0% | 100.0% | 6.6% | 0.70% |
| bar|hard | vlm2_crop | 228 (19) | 100.0% | 100.0% | 6.1% | 0.50% |
| bar|hard | vlm2_table | 228 (19) | 100.0% | 100.0% | 11.0% | 0.81% |
| line|easy | ocr_pixel | 45 (4) | 97.8% | - | 0.0% | 0.11% |
| line|easy | deplot | 45 (4) | 100.0% | - | 0.0% | 0.22% |
| line|easy | vlm_table | 45 (4) | 100.0% | - | 2.2% | 0.62% |
| line|easy | vlm_crop | 45 (4) | 100.0% | - | 2.2% | 0.90% |
| line|easy | vlm2_crop | 45 (4) | 100.0% | - | 0.0% | 0.28% |
| line|easy | vlm2_table | 45 (4) | 100.0% | - | 2.2% | 0.79% |
| bar|easy | ocr_pixel | 41 (8) | 95.1% | 100.0% | 0.0% | 0.08% |
| bar|easy | deplot | 41 (8) | 100.0% | 100.0% | 0.0% | 0.12% |
| bar|easy | vlm_table | 41 (8) | 100.0% | 100.0% | 0.0% | 0.40% |
| bar|easy | vlm_crop | 41 (8) | 100.0% | 100.0% | 0.0% | 0.52% |
| bar|easy | vlm2_crop | 41 (8) | 100.0% | 100.0% | 0.0% | 0.20% |
| bar|easy | vlm2_table | 41 (8) | 100.0% | 100.0% | 0.0% | 0.30% |
| * | ocr_pixel | 1063 (51) | 50.3% | 33.7% | 0.9% | 0.15% |
| * | deplot | 1063 (51) | 66.8% | 31.6% | 4.6% | 0.24% |
| * | vlm_table | 1063 (51) | 66.2% | 30.8% | 26.0% | 1.40% |
| * | vlm_crop | 1063 (51) | 100.0% | 100.0% | 25.1% | 1.63% |
| * | vlm2_crop | 1063 (51) | 100.0% | 100.0% | 21.8% | 0.75% |
| * | vlm2_table | 1063 (51) | 98.4% | 96.6% | 25.2% | 1.77% |

Pairs: of the points where both tools answered and agreed (within 3% of the axis), the share where both were badly wrong. The planner trusts a pair at <= 5% with >= 20 agreements on >= 5 charts.

| situation | pair | agreements | wrong when agreeing | charts (with a wrong agreement) | passes the gate |
|---|---|---|---|---|---|
| line|hard | deplot~vlm2_crop | 309 | 0.6% (2) | 20 (2) | yes |
| line|hard | deplot~vlm2_table | 287 | 1.7% (5) | 20 (4) | yes |
| line|hard | ocr_pixel~vlm2_crop | 265 | 0.8% (2) | 17 (1) | yes |
| line|hard | ocr_pixel~vlm2_table | 238 | 0.4% (1) | 17 (1) | yes |
| line|hard | vlm2_crop~vlm2_table | 423 | 13.2% (56) | 20 (5) | no |
| line|hard | vlm_crop~vlm2_crop | 448 | 14.3% (64) | 20 (5) | no |
| line|hard | vlm_crop~vlm2_table | 348 | 10.1% (35) | 20 (6) | no |
| line|hard | vlm_table~vlm2_crop | 214 | 3.3% (7) | 20 (4) | yes |
| line|hard | vlm_table~vlm2_table | 197 | 6.1% (12) | 19 (5) | no |
| bar|hard | deplot~vlm2_crop | 189 | 0.0% (0) | 19 (0) | yes |
| bar|hard | deplot~vlm2_table | 172 | 0.0% (0) | 19 (0) | yes |
| bar|hard | ocr_pixel~vlm2_crop | 132 | 0.0% (0) | 15 (0) | yes |
| bar|hard | ocr_pixel~vlm2_table | 126 | 0.0% (0) | 15 (0) | yes |
| bar|hard | vlm2_crop~vlm2_table | 190 | 2.6% (5) | 19 (2) | yes |
| bar|hard | vlm_crop~vlm2_crop | 205 | 3.9% (8) | 19 (3) | yes |
| bar|hard | vlm_crop~vlm2_table | 189 | 2.6% (5) | 19 (2) | yes |
| bar|hard | vlm_table~vlm2_crop | 145 | 1.4% (2) | 19 (1) | yes |
| bar|hard | vlm_table~vlm2_table | 137 | 2.2% (3) | 19 (1) | yes |
| * | deplot~vlm2_crop | 584 | 0.3% (2) | 51 (2) | yes |
| * | deplot~vlm2_table | 537 | 0.9% (5) | 51 (4) | yes |
| * | ocr_pixel~vlm2_crop | 480 | 0.4% (2) | 44 (1) | yes |
| * | ocr_pixel~vlm2_table | 439 | 0.2% (1) | 44 (1) | yes |
| * | vlm2_crop~vlm2_table | 692 | 8.8% (61) | 51 (7) | no |
| * | vlm_crop~vlm2_crop | 737 | 9.8% (72) | 51 (8) | no |
| * | vlm_crop~vlm2_table | 617 | 6.5% (40) | 51 (8) | no |
| * | vlm_table~vlm2_crop | 444 | 2.0% (9) | 51 (5) | yes |
| * | vlm_table~vlm2_table | 412 | 3.6% (15) | 50 (6) | yes |

Cost per call (seconds, measured): vlm2_crop 7.87 per read, 104.7 per figure, vlm2_table 0.00 per read, 8.6 per figure

**Rule I1** (vlm2_crop answers >= 50% at x without a tick label on line|hard, and a new-old pair passes the gate there): answers 100.0%, a pair passes: yes. **GO**

## I2: six splits, v3 against v3 plus the second model family (P3 informed)

| | v3 | v3 + Granite | change |
|---|---|---|---|
| claims | 1205 | 1205 | +0 |
| coverage (decided) | 79.6% | 77.1% | -2.5 points |
| flags | 455 | 404 | -51 |
| wrong flags (a correct claim flagged) | 15 | 12 | -3 |
| missed errors (an error accepted) | 4 | 9 | +5 |
| right when decided | 96.9% | 96.6% | -0.3 points |
| sent to the TA | 246 | 276 | +30 |

| split | coverage v3 | coverage v3 + Granite | wrong flags v3 / new | missed errors v3 / new | offline misses |
|---|---|---|---|---|---|
| test | 74.1% | 71.1% | 1 / 2 | 0 / 1 | 0 |
| dev | 80.8% | 76.0% | 1 / 1 | 1 / 2 | 0 |
| holdout | 78.0% | 75.8% | 6 / 4 | 0 / 0 | 0 |
| holdout2 | 83.7% | 83.2% | 1 / 1 | 1 / 3 | 0 |
| holdout3 | 75.6% | 75.1% | 1 / 1 | 1 / 2 | 0 |
| final | 84.9% | 81.0% | 5 / 3 | 1 / 1 | 0 |

Verdict changes, claim by claim (old -> new, gold label):

- MISMATCH -> NOT_SURE (error): 50
- NOT_SURE -> CONSISTENT (correct): 22
- CONSISTENT -> NOT_SURE (correct): 6
- NOT_SURE -> MISMATCH (error): 5
- MISMATCH -> NOT_SURE (correct): 5
- MISMATCH -> CONSISTENT (error): 3
- MISMATCH -> CONSISTENT (correct): 2
- CONSISTENT -> MISMATCH (correct): 2
- NOT_SURE -> CONSISTENT (error): 2
- NOT_SURE -> MISMATCH (no_figure): 1
- NOT_SURE -> MISMATCH (correct): 1

| why a claim still goes to the TA | v3 | v3 + Granite |
|---|---|---|
| no trustworthy pair of tools for this point | 137 | 122 |
| still unclear, no usable tool left | 42 | 99 |
| two figures fit the sentence | 37 | 37 |
| readings too spread out, or too few | 30 | 18 |

Tool calls (pooled): ocr_pixel 1206 -> 1023, deplot 330 -> 306, vlm_table 56 -> 62, vlm_crop 486 -> 267, vlm2_crop 0 -> 73, vlm2_table 0 -> 200

Model seconds spent in the v3 + Granite runs (cached readings cost nothing): vlm2 52 min

**Rule I2** (pooled: wrong flags do not rise, missed errors do not rise, coverage +2 points or more, 0 unsafe LMS actions): wrong flags 15 -> 12, missed errors 4 -> 9, coverage -2.5 points, unsafe actions 0. **NOT KEPT**
