# Karan · Q&A (model loader, tool interface, neural tools, fine-tuning)

Read the shared questions in [poster_qa_common.md](../poster_qa_common.md) first. Your reading guide is [reading.md](reading.md).

---

## Basic

**Q: Which models do you use?**
Qwen3-VL-4B-Instruct, a vision-language model, for two tools and for parsing, and DePlot, a separate chart-to-table
model, for a third tool.

**Q: Why a 4B model and not a bigger one?**
It runs on a laptop GPU or a free T4, and the system's point is that a modest model inside a careful checker beats the
same model judging on its own.

**Q: What is the VLM crop tool?**
It crops the chart around the target x, stitches the y-axis labels on the left, upscales it, tells the model the
series colour, and asks for one number.

**Q: What is the VLM table tool?**
The model turns the whole chart into a JSON table once; every later value on that figure is a free lookup.

**Q: What is DePlot and why include it?**
A Pix2Struct model trained to turn plots into tables. It is a different model from Qwen, so it makes different
mistakes, which is what cross-checking needs.

**Q: What is the tool interface?**
Every tool takes a figure and a (series, x) query and returns a reading: a value, or an error code. Tools never crash
the agent, and every reading is cached.

---

## Results

**Q: How often does each tool answer?**
VLM crop 100%, DePlot 96%, VLM table 96%, pixel reader 74% (it refuses rather than guesses).

**Q: Did fine-tuning help?**
Chart reading clearly improved: the table tool answered more often (66% → 74%), its median error halved (1.4% → 0.8% of
the axis range), and badly wrong answers fell from 26% to 17%.

**Q: Then why did you not use the fine-tuned model?**
The system did not get reliably safer: pooled over six sets, coverage rose (79.7% → 82.3%) but wrong flags also rose
(3.5% → 4.2%). It was better on the final set and clearly worse on two others, so we kept the base model.

**Q: Why did a better reader not give fewer wrong flags?**
With the base model, the two Qwen tools agree on a wrong value 5.1% of the time on hard line charts, just above the
planner's 5% limit, so the planner never paired them. The adapted tool answers more often, so the same wrong agreements
became 3.8%, under the limit, and the planner started pairing the two Qwen tools: 10 of the adapted system's 16 wrong
flags rest on both. Replayed with a rule that never pairs tools sharing a model, wrong flags fall to 2.3% but coverage
falls to 76.7%. The extra coverage came from a risky pair, not from better reading.

**Q: How was the LoRA trained?**
On 918 generated charts with their exact tables as targets, one epoch, 114 steps, about 146 minutes on Apple silicon,
using the tool's exact prompt. Validation loss went from 0.53 to 0.27. Two earlier attempts ran out of memory.

---

## Deeper

**Q: Do the two Qwen tools count as independent?**
No. Same model, so they are never each other's cross-check. Samples of the same model agree 95–98% of the time but are
wrong together 5–7% of the time; tools of different kinds agree wrongly at most 0.6% of the time.

**Q: How do you keep readings reproducible?**
Greedy decoding (temperature 0) for every tool, and a cache keyed by tool, tool version, image hash, series and x.
Changing a prompt means changing the version, so old answers are never reused by mistake.

**Q: Is the LoRA used for everything?**
No, only for chart-to-table. For crops, parsing and the legend repair the adapter is switched off, so fine-tuning
cannot quietly change the other tools.

**Q: What happens when the model returns bad output?**
We extract the first valid JSON (models add text and code fences); if there is none the tool returns `bad_json` and
the agent tries another tool or hands off.

**Q: How do you develop without a GPU?**
Simulated tools read the true values and add noise, with shared noise between tools of the same model so the
correlation study has something to find. They are for plumbing only; we never report their numbers.

**Q: How do you replay experiments without the model?**
Offline mode answers only from the cache; a missing reading is reported as an `offline_miss`, never fetched or cached.

**Q: What are the pilots you ran?**
Legend pilots: whether the VLM can read legend names for the pixel reader and for retrieval. For retrieval it
recovered 5 of 7 wrong "No matching figure" cases and invented 0 of 23.

---

## Hard questions

**Q: Why not use a bigger model like GPT-4o?**
It would read charts better, but a model judging on its own still gives a verdict when its reading is too rough. Our
point holds for any reader: flag only when the gap exceeds the measured reading error. Cost and privacy also favour a
local model.

**Q: Can it run on a normal laptop?**
The pixel reader, DePlot and everything else can. Qwen3-VL-4B needs about 8 GB in 16-bit, so we run it on a laptop GPU,
a free Kaggle T4, or a model server.

**Q: Does fine-tuning risk overfitting to your chart styles?**
Yes, which is why the training charts come from separate generator seeds and the held-out style is never used.

**Q: If you fine-tuned again, what would you change?**
Measure the pair agreement of the adapted tool with the other Qwen tool before deploying, since that, not single-tool
accuracy, decided whether wrong flags went up.
