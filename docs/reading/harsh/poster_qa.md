# Harsh · Q&A (generator, PDF ingest, retrieval, claim parsing)

Read the shared questions in [poster_qa_common.md](../poster_qa_common.md) first. Your reading guide is [reading.md](reading.md).

---

## Basic

**Q: Where does your data come from?**
We generate it: tables that look like student ML results, charts drawn in many styles, short PDF lab reports, and
sentences about the charts with known labels.

**Q: Why synthetic data?**
To measure wrong flags and the detection limit we need the exact true value of every chart point and the exact size of
every error. Real reports do not come with that.

**Q: What kinds of sentences do you generate?**
Correct exact, correct rounded or hedged ("about 80%", "over 80%"), planted errors of known size, mix-ups (wrong series
or wrong x), claims about things no figure shows, and setup sentences with numbers that are not chart claims.

**Q: What sizes of errors?**
2%, 5%, 10%, 20% and 50% of the axis range.

**Q: How do you read the PDF?**
PyMuPDF gives text blocks with positions and the images. A caption is the block just below a figure starting with
"Figure N". Each figure is OCR'd once (legend, ticks, title) and its axis range measured.

**Q: How do you find the figure a sentence is about?**
An explicit "Figure N" first, then BM25 over each figure's caption and chart text. A figure is accepted only if the
claimed series (and x, on category axes) actually appear in it; otherwise the answer is "No matching figure".

---

## Results

**Q: How good is retrieval?**
The right figure was ranked first for 97.4% of claims. "No matching figure" was right for 89% of claims no figure shows,
100% on the final set.

**Q: How good is parsing?**
100% on the generated sentence templates. On unfamiliar wordings the rules recognise 40%; rules plus the LLM parser
reach 87–89% per field.

**Q: How much do wrong decisions come from your part?**
Of 31 wrong decisions out of 960, 14 started at retrieval, the largest single cause.

**Q: What fixed retrieval mistakes?**
Two fixes: trusting a cited "Figure N" when OCR misread the series name, and asking the VLM for legend names when OCR
fails. Wrong "No matching figure" dropped from 9 to 2 on dev and from 4 to 0 on test. In the pilot the legend fix
recovered 5 of 7 wrong cases and invented 0 of 23.

---

## Deeper

**Q: How do you avoid labelling a rounding as an error?**
The generator labels each sentence with the same tolerance function the checker uses, applied to the number exactly
as written. "82%" allows ±0.5, "82.4%" ±0.05, "about 80%" ±5, "over 80%" means the true value must be above 80.

**Q: Why not let the LLM decide the rounding?**
Because it would then influence the verdict. The tolerance is a deterministic function of the text.

**Q: Why have both a rule parser and an LLM parser?**
Rules are exact and cheap and handle known phrasings; the LLM handles new wordings. The agent uses the LLM only when the
rules fail or the parsed names appear in no figure.

**Q: How do you stop the LLM parser from inventing numbers?**
The claimed number must appear in the sentence, the JSON is validated, and it gets one retry with the error shown.

**Q: What if one sentence is split across a page break?**
We join blocks that were cut in the middle of a sentence, and a cut comparison is not turned into a point claim.
Both were bugs found on a fresh split and fixed.

**Q: How do you test the system on charts it has not seen?**
A held-out plotting style (grey background, white grid) is never used for calibration or fine-tuning; half the charts
are "hard" (small, compressed, busy).

**Q: How do you build the hidden-instruction test?**
15% of reports get a hidden instruction in white, tiny text in the body or a caption, plus a clean twin that is
identical except for the instruction (separate random stream).

---

## Hard questions

**Q: Synthetic charts look nothing like real student charts. Isn't that a problem?**
It is our main limitation. We made half the charts hard and kept one style completely held out to measure the effect
of a style change, but testing on real reports is future work.

**Q: Does the claim finder work on other kinds of text?**
Only partly. It needs a number and a result word such as "accuracy", "loss" or "reached", which fits ML reports.
Plain sentences like "the value was 2.89 in 2019" would be missed.

**Q: Why BM25 and not embeddings?**
BM25 is cheap, explainable and works well with exact names like "ResNet-50" and "CIFAR-10". An embedding scorer can be
plugged in; the coverage check (series must appear in the figure) does most of the work.

**Q: Couldn't a student write sentences your parser does not understand?**
Yes; those go to the LLM parser, and if no parser accepts a sentence that looks like a claim, it can be sent to the TA
instead of being dropped.
