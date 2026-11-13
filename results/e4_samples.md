# E4 (reduced): repeated samples of one model against tools of different kinds

Made by `python scripts/e4_samples.py`: 242 calibration points (up to 5 per chart), crop reader sampled 3 more times at temperature 0.7. Agree = within 3% of the axis; wrong = the two readings' mean is more than 5% of the axis off.

| Pair | Kind | Both answered | Agree | Wrong when they agree | Error correlation |
|---|---|---|---|---|---|
| ocr_pixel~vlm_table | different kinds | 173 | 90% | 0.6% (1 of 155) | 0.10 |
| ocr_pixel~deplot | different kinds | 172 | 99% | 0.0% (0 of 171) | 0.09 |
| ocr_pixel~vlm_crop | different kinds | 180 | 89% | 0.0% (0 of 161) | 0.03 |
| ocr_pixel~vlm_crop@s1 | different kinds | 180 | 91% | 0.0% (0 of 163) | -0.01 |
| ocr_pixel~vlm_crop@s2 | different kinds | 180 | 91% | 0.0% (0 of 163) | 0.01 |
| ocr_pixel~vlm_crop@s3 | different kinds | 180 | 89% | 0.0% (0 of 161) | 0.03 |
| deplot~vlm_table | different kinds | 205 | 85% | 0.0% (0 of 174) | -0.11 |
| deplot~vlm_crop | different kinds | 208 | 92% | 0.0% (0 of 191) | 0.29 |
| deplot~vlm_crop@s1 | different kinds | 208 | 91% | 0.0% (0 of 189) | 0.37 |
| deplot~vlm_crop@s2 | different kinds | 208 | 92% | 0.0% (0 of 192) | 0.42 |
| deplot~vlm_crop@s3 | different kinds | 208 | 91% | 0.0% (0 of 190) | 0.38 |
| vlm_table~vlm_crop | same model, different prompt | 211 | 82% | 0.0% (0 of 172) | -0.01 |
| vlm_table~vlm_crop@s1 | same model, different prompt | 211 | 81% | 0.0% (0 of 170) | 0.11 |
| vlm_table~vlm_crop@s2 | same model, different prompt | 211 | 82% | 0.0% (0 of 172) | 0.08 |
| vlm_table~vlm_crop@s3 | same model, different prompt | 211 | 82% | 0.0% (0 of 172) | 0.17 |
| vlm_crop@s1~vlm_crop@s3 | same model, sampled | 242 | 97% | 6.8% (16 of 235) | 0.97 |
| vlm_crop~vlm_crop@s1 | same model, sampled | 242 | 98% | 5.9% (14 of 237) | 0.96 |
| vlm_crop@s2~vlm_crop@s3 | same model, sampled | 242 | 95% | 5.6% (13 of 231) | 0.95 |
| vlm_crop~vlm_crop@s3 | same model, sampled | 242 | 96% | 5.6% (13 of 233) | 0.95 |
| vlm_crop@s1~vlm_crop@s2 | same model, sampled | 242 | 96% | 5.2% (12 of 232) | 0.96 |
| vlm_crop~vlm_crop@s2 | same model, sampled | 242 | 97% | 5.1% (12 of 234) | 0.93 |
