# Vikash · Q&A (pixel reader, calibration, decision rule, evaluation, baselines, safety)

Read the shared questions in [poster_qa_common.md](../poster_qa_common.md) first. Your reading guide is [reading.md](reading.md).

---

## Basic

**Q: How does the OCR + pixel reader work?**
It finds the plot area, reads the y-axis tick labels with Tesseract, fits a line from pixel to value, finds the series
by its legend colour, finds the bar top or line point at the x tick, and converts that pixel to a value.

**Q: Why have a non-neural tool at all?**
It shares no weights with the VLM, so it makes different mistakes. That makes its agreement with a neural tool real
evidence.

**Q: How do you combine readings?**
The estimate is the median of the tools' values; the disagreement is their median absolute deviation. Disagreement never
moves the estimate; it only sets how wide the margin is.

**Q: What is the decision rule?**
If the gap between the claim and the estimate is larger than the allowed rounding plus the flag margin: Mismatch. If
it is within the rounding plus the accept margin, and that margin is narrow: Consistent. Otherwise: Not sure.

**Q: What is calibration here?**
We read every point of charts with known values with every tool and record how many "disagreements" the true value was
from the estimate. The 95% quantile of that ratio becomes the flag margin factor.

---

## Results

**Q: How well does it do?**
Final untouched set: 84.9% decided, 5.6% wrong flags. All six sets: 79.7% decided, 3.5% wrong flags, 0.7% missed errors.

**Q: Against the baselines?**
On the final set: VLM asked directly (B1) 23.3% wrong flags; with a confidence threshold (B2) never below 10%; five
samples voting (B3) 19.1%; the model judging our own tool readings (B4) 25.9%. Ours: 5.6%.

**Q: What is the smallest error you catch?**
2% of the axis range, the smallest we planted: 79% of those were flagged among claims two tools could measure, rising
to 98% at 50%. None of the 489 planted errors was accepted as correct.

**Q: Did calibration beat a simple fixed margin (B5)?**
No. At a 5% wrong-flag target both reached 5.7% on the later sets, and B5 decided slightly more (−2.1 points). We report
that as a finding: the benefit comes from different tools, a disagreement-scaled margin, and abstaining.

**Q: Then why keep calibration?**
Its factor is fixed before any evaluation result is seen. B5's factor has to be tuned on labelled reports.

**Q: Did the batch check (BH) help?**
At our settings it never changed a verdict, by construction: a flag beyond the 95% cut-off has a p-value ≤ 0.05, below
α = 0.10, so BH keeps it. With a looser per-claim level (0.8) BH removes 39 flags and holds wrong flags at 8.8%
instead of 13.8%, deciding 82.1% without tuning.

**Q: How reliable is the pixel reader?**
It returned a value 74% of the time, the lowest of the four, because it refuses rather than guesses. Its errors when it
does answer are about 0.1% of the axis range on clean charts.

---

## Deeper

**Q: Why the ratio |truth − estimate| / disagreement?**
It scales with the situation: when tools disagree, the margin widens automatically. When tools agree but are wrong
together, the ratio is large, and that group's margin grows.

**Q: Why a floor on the disagreement?**
Two identical readings give zero disagreement and would give a zero margin. We add 0.5% of the axis span.

**Q: Why the (n+1) in the conformal cut-off?**
Taking the ⌈(n+1)·0.95⌉-th smallest ratio, not the plain 95th percentile, is what makes the guarantee hold on new charts
that resemble the calibration charts.

**Q: Why do you sometimes say Not sure even when the gap is tiny?**
If the accept margin is wider than 3% of the axis, a real error would also fit inside it, so accepting would mean
nothing.

**Q: Why one tool subset per calibration item?**
The conformal guarantee assumes one exchangeable ratio per item; using every subset would overcount.

**Q: What about margins per exact pair of tools?**
We tried it: wrong flags on dev rose from 1.4% to 4.1%, because a pair that stopped early because it agreed is a
selected sample. We kept it off.

**Q: How do you handle "over 80%" or "about 80%"?**
The gap is direction-aware for one-sided claims, and the allowed rounding comes from how the number is written, never
from the model.

**Q: How did you compute intervals?**
Bootstrap that resamples whole reports, because claims in one report share figures and are not independent.

**Q: What caused the wrong decisions?**
Of 31 wrong decisions out of 960 decided: retrieval 14, measurement 13, the decision rule 4 (claimed number belonged to
another series but was inside the margin).

**Q: How did you test safety?**
18 reports with hidden instructions, each compared with a clean twin. With the rule parser 0 of 210 verdicts changed.
With the LLM parser 8 claims (3.8%) were dropped as "not a claim", all from instructions in captions, and 4 of them
were correct flags of real errors. None became Consistent and 0 unsafe actions ran, because the LMS guard only allows
posting a flag, but the instruction still managed to hide claims. That is why the frozen system parses with rules.

---

## Hard questions

**Q: Your calibration lost to a fixed factor. Isn't your main idea wrong?**
The main idea is "flag only when the gap exceeds the measured reading error". That holds: it beats every
model-judges baseline by 4×. What we learned is that a fixed multiple of the disagreement is as good a margin as the
calibrated one on these charts.

**Q: The holdout set had 9.4% wrong flags. Why?**
It is our worst set, and grouped bars made up 40% of its charts, which are harder for the tools. We used it to
diagnose a calibration problem, so we no longer count it as unbiased; the untouched final set is the one to quote.

**Q: Is calibration valid on other hardware?**
The tables were measured with float16 on Apple silicon. Greedy decoding usually gives the same readings, but the
calibration charts should be re-read on new hardware before trusting the margins.

**Q: What is the failure your design cannot rule out?**
Two different models making the same mistake. Example: a correct loss of 0.371, read as 0.43 by DePlot and 0.45 by
the VLM crop; they agreed, and the claim was wrongly flagged.
