# Poster Q&A

Likely questions at the poster and short answers you can say out loud, with the numbers to quote. Every number comes
from `results/` or the final report (`docs/final_report/report.pdf`).

| File | For |
|---|---|
| this file | **everyone**: questions any of us may get |
| [hritik/poster_qa.md](hritik/poster_qa.md) | agent, planner, tool profile, pipeline |
| [vikash/poster_qa.md](vikash/poster_qa.md) | OCR + pixel reader, calibration, decision rule, evaluation, baselines, safety |
| [harsh/poster_qa.md](harsh/poster_qa.md) | generator, PDF ingest, retrieval, claim parsing |
| [karan/poster_qa.md](karan/poster_qa.md) | model loader, tool interface, neural tools, fine-tuning |

How to answer: **one sentence answer, then one number, then stop.** If they want more, they will ask.

---

## Numbers to remember

| What | Number |
|---|---|
| Untouched final set | 20 reports, 205 claims, generated after the method was frozen, run once |
| Final: decided without the TA | **84.9%** |
| Final: wrong flags | **5.6%** (5 of 89) |
| Final: VLM asked directly (B1) | **23.3%** wrong flags, misses 55.8% of errors |
| All six sets pooled | 1,205 claims, 79.7% decided, **3.5%** wrong flags, 0.7% missed errors |
| Smallest error caught | **2% of the axis range** (79% caught among measured claims) |
| Planted errors accepted as correct | **0 of 489** (every miss was a hand-off to the TA) |
| Model time per 200 claims | planner 16.2 min, all tools 43.6 min (2.7×) |
| Hidden instructions | 0 of 210 verdicts changed, 0 unsafe actions |

---

## Questions anyone may get

**Q: What does your project do, in one sentence?**
It checks whether the numbers a student writes in a report match the report's own charts, and flags a sentence only
when the mismatch is clearly bigger than the error of reading the chart.

**Q: Why not just ask GPT / a VLM?**
We did, as baseline B1: the same VLM asked directly made 23% wrong flags on the final set and missed more than half the
real errors. Our system made 5.6% wrong flags with the same model inside it.

**Q: What is a "wrong flag" and why is it your main metric?**
A wrong flag is accusing a student of a wrong number when the number is right. It is the costly mistake for a TA, so
we optimise for few wrong flags and let unclear cases go to the TA instead.

**Q: What is your research question?**
Does a checker that flags only when the gap is larger than its own measured reading error make fewer wrong flags than
simpler approaches with the same model?

**Q: What is the answer?**
Against approaches where the model judges: clearly yes (5.6% vs 23–26%). Against the same pipeline with a simple
fixed margin (B5): no, it did about as well. The gain comes from reading with different kinds of tools, a margin that
grows with their disagreement, and abstaining; not from calibration itself.

**Q: Where does the language model fit in?**
It reads charts (two of the four tools), can parse unusual sentences and can choose tools. It never decides a verdict;
a few lines of tested Python do.

**Q: What are the four tools?**
VLM crop (Qwen3-VL-4B on a zoomed crop), VLM table (Qwen3-VL-4B converts the whole chart to a table), DePlot (a
different chart-to-table model) and OCR + pixel measurement (no neural network).

**Q: What are the four outcomes?**
Consistent, Mismatch, Not sure (goes to the TA), No matching figure.

**Q: Is the data real?**
No, it is generated: synthetic lab reports with charts and sentences whose true values we know, including planted
errors of known size. That is what lets us measure the detection limit exactly. Testing on real reports is future work.

**Q: How do you know you did not overfit to your test set?**
The final set was generated after the method was frozen and was run once. We also report which earlier sets were used
for design decisions.

**Q: What surprised you?**
Two tools agreeing is only evidence when they make different mistakes. Samples of the same model agree with each
other 95–98% of the time and are still wrong together 5–7% of the time.

**Q: What did not work?**
Three things, reported as findings: the calibrated margin did not beat a fixed margin, the batch check never changed a
verdict at our settings, and fine-tuning improved chart reading but not wrong flags.

**Q: Limitations?**
Synthetic reports; bar and line charts only; claims about single values, differences and relative changes; claims at an
x position without a tick label usually go to the TA; two different models can still make the same mistake.

**Q: Could a student trick it with hidden text?**
We tested it: 18 reports with hidden instructions. With the rule parser 0 of 210 verdicts changed; the system can only
post a flag, so it cannot change a grade or email anyone. With an LLM parser, caption instructions did hide 8 claims,
which is why the final system parses with rules.

**Q: How long does it take?**
About 16 minutes of model time per 200 claims on an Apple-silicon laptop, close to the cost of asking the VLM once per
claim (11–15 minutes).

**Q: Who did what?**
Hritik: agent, planner, pipeline. Vikash: pixel reader, calibration, decision rule, evaluation. Harsh: data generator,
PDF reading, retrieval, parsing. Karan: model loading, neural tools, fine-tuning.
