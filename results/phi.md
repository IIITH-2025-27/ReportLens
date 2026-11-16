# Phi-4-multimodal as the second model family (run_log I6/I7)

## I6: Phi-4-multimodal on the calibration charts (live calls to Phi, the rest from the cache)

| situation | tool | points (charts) | answers | answers at x without a tick label | badly wrong (> 5% of the axis) | median error |
|---|---|---|---|---|---|---|
| line|hard | ocr_pixel | 749 (20) | 41.7% | 22.6% | 1.3% | 0.16% |
| line|hard | deplot | 749 (20) | 54.7% | 9.0% | 6.6% | 0.23% |
| line|hard | vlm_table | 749 (20) | 54.1% | 8.2% | 33.6% | 2.40% |
| line|hard | vlm_crop | 749 (20) | 100.0% | 100.0% | 33.5% | 2.61% |
| line|hard | vlm2_crop | 749 (20) | 56.7% | 78.1% | 65.6% | 8.20% |
| line|hard | vlm2_table | 749 (20) | 56.2% | 9.3% | 59.4% | 7.51% |
| bar|hard | ocr_pixel | 228 (19) | 61.4% | 57.0% | 0.7% | 0.16% |
| bar|hard | deplot | 228 (19) | 93.9% | 89.2% | 2.8% | 0.30% |
| bar|hard | vlm_table | 228 (19) | 93.4% | 88.2% | 21.6% | 1.13% |
| bar|hard | vlm_crop | 228 (19) | 100.0% | 100.0% | 6.6% | 0.70% |
| bar|hard | vlm2_crop | 228 (19) | 25.0% | 37.6% | 56.1% | 6.80% |
| bar|hard | vlm2_table | 228 (19) | 91.2% | 82.8% | 43.8% | 3.90% |
| line|easy | ocr_pixel | 45 (4) | 97.8% | - | 0.0% | 0.11% |
| line|easy | deplot | 45 (4) | 100.0% | - | 0.0% | 0.22% |
| line|easy | vlm_table | 45 (4) | 100.0% | - | 2.2% | 0.62% |
| line|easy | vlm_crop | 45 (4) | 100.0% | - | 2.2% | 0.90% |
| line|easy | vlm2_crop | 45 (4) | 46.7% | - | 4.8% | 2.39% |
| line|easy | vlm2_table | 45 (4) | 46.7% | - | 66.7% | 6.96% |
| bar|easy | ocr_pixel | 41 (8) | 95.1% | 100.0% | 0.0% | 0.08% |
| bar|easy | deplot | 41 (8) | 100.0% | 100.0% | 0.0% | 0.12% |
| bar|easy | vlm_table | 41 (8) | 100.0% | 100.0% | 0.0% | 0.40% |
| bar|easy | vlm_crop | 41 (8) | 100.0% | 100.0% | 0.0% | 0.52% |
| bar|easy | vlm2_crop | 41 (8) | 7.3% | 0.0% | 0.0% | 0.36% |
| bar|easy | vlm2_table | 41 (8) | 90.2% | 83.3% | 0.0% | 0.60% |
| * | ocr_pixel | 1063 (51) | 50.3% | 33.7% | 0.9% | 0.15% |
| * | deplot | 1063 (51) | 66.8% | 31.6% | 4.6% | 0.24% |
| * | vlm_table | 1063 (51) | 66.2% | 30.8% | 26.0% | 1.40% |
| * | vlm_crop | 1063 (51) | 100.0% | 100.0% | 25.1% | 1.63% |
| * | vlm2_crop | 1063 (51) | 47.6% | 65.8% | 61.7% | 7.68% |
| * | vlm2_table | 1063 (51) | 64.6% | 29.3% | 51.7% | 5.48% |

Pairs: of the points where both tools answered and agreed (within 3% of the axis), the share where both were badly wrong. The planner trusts a pair at <= 5% with >= 20 agreements on >= 5 charts.

| situation | pair | agreements | wrong when agreeing | charts (with a wrong agreement) | passes the gate |
|---|---|---|---|---|---|
| line|hard | deplot~vlm2_crop | 39 | 0.0% (0) | 14 (0) | yes |
| line|hard | deplot~vlm2_table | 122 | 3.3% (4) | 18 (2) | yes |
| line|hard | ocr_pixel~vlm2_crop | 38 | 0.0% (0) | 11 (0) | yes |
| line|hard | ocr_pixel~vlm2_table | 109 | 0.0% (0) | 15 (0) | yes |
| line|hard | vlm2_crop~vlm2_table | 52 | 36.5% (19) | 17 (10) | no |
| line|hard | vlm_crop~vlm2_crop | 132 | 37.1% (49) | 16 (6) | no |
| line|hard | vlm_crop~vlm2_table | 130 | 12.3% (16) | 20 (8) | no |
| line|hard | vlm_table~vlm2_crop | 47 | 21.3% (10) | 14 (6) | no |
| line|hard | vlm_table~vlm2_table | 110 | 10.0% (11) | 18 (7) | no |
| bar|hard | deplot~vlm2_crop | 18 | 11.1% (2) | 11 (2) | no |
| bar|hard | deplot~vlm2_table | 89 | 2.2% (2) | 17 (2) | yes |
| bar|hard | ocr_pixel~vlm2_crop | 4 | 0.0% (0) | 4 (0) | no |
| bar|hard | ocr_pixel~vlm2_table | 72 | 0.0% (0) | 13 (0) | yes |
| bar|hard | vlm2_crop~vlm2_table | 16 | 31.2% (5) | 11 (4) | no |
| bar|hard | vlm_crop~vlm2_crop | 19 | 10.5% (2) | 10 (2) | no |
| bar|hard | vlm_crop~vlm2_table | 93 | 3.2% (3) | 18 (2) | yes |
| bar|hard | vlm_table~vlm2_crop | 18 | 11.1% (2) | 11 (2) | no |
| bar|hard | vlm_table~vlm2_table | 88 | 4.5% (4) | 17 (3) | yes |
| * | deplot~vlm2_crop | 73 | 2.7% (2) | 32 (2) | yes |
| * | deplot~vlm2_table | 252 | 2.4% (6) | 44 (4) | yes |
| * | ocr_pixel~vlm2_crop | 59 | 0.0% (0) | 22 (0) | yes |
| * | ocr_pixel~vlm2_table | 219 | 0.0% (0) | 37 (0) | yes |
| * | vlm2_crop~vlm2_table | 72 | 33.3% (24) | 32 (14) | no |
| * | vlm_crop~vlm2_crop | 172 | 29.7% (51) | 33 (8) | no |
| * | vlm_crop~vlm2_table | 263 | 7.2% (19) | 47 (10) | no |
| * | vlm_table~vlm2_crop | 84 | 14.3% (12) | 32 (8) | no |
| * | vlm_table~vlm2_table | 241 | 6.2% (15) | 44 (10) | no |

Cost per call (seconds, measured): vlm2_crop 11.76 per read, 200.0 per figure, vlm2_table 0.00 per read, 11.3 per figure


Phi-Qwen pairs on line|hard: vlm_crop~vlm2_crop 37.1% of 132 agreements (fails); vlm_crop~vlm2_table 12.3% of 130 agreements (fails); vlm_table~vlm2_crop 21.3% of 47 agreements (fails); vlm_table~vlm2_table 10.0% of 110 agreements (fails)

**Rule I6** (on line|hard: vlm2_crop answers >= 50% at x without a tick label, and a Phi-Qwen pair passes the gate): answers 78.1%, a Phi-Qwen pair passes: no. **NO-GO**
