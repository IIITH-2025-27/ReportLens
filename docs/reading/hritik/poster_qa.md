# Hritik · Q&A (agent, planner, tool profile, pipeline)

Read the shared questions in [poster_qa_common.md](../poster_qa_common.md) first. Your reading guide is [reading.md](reading.md).

---

## Basic

**Q: What does the agent do?**
For each report it plans which tools to use per figure, then for each claim runs a loop: read a value with a tool,
combine the readings, ask the decision rule, and stop as soon as the answer is clear or hand the claim to the TA.

**Q: What does the agent decide, and what can it not decide?**
It decides which tool to call next, whether to repair a failure, and when to hand off. It cannot give a verdict; a
policy may only return "read", "repair" or "hand off".

**Q: What is the tool profile?**
A table measured on charts with known values: for each tool and each kind of chart, how often it answers, its typical
error, how often it is badly wrong, its time per call, and for every pair of tools how often they agree on a wrong
value.

**Q: What is a "situation"?**
What a chart looks like before measuring: line or bar, easy or hard. Hard means a small image, four or more series,
or an axis we cannot read.

**Q: What policies did you compare?**
P0 all tools, P1 fixed order (cheapest first), P1b ordered by calibrated error, P2 the LLM chooses, and P3 our
planner, which decides from the measured profile.

---

## Results

**Q: Does the planner help?**
Mainly for cost: 16.2 minutes of model time per 200 claims against 43.6 for running every tool (2.7× less), with
1.86 tool calls per claim. Pooled wrong flags were 3.5% against 4.4% for all tools.

**Q: Is it better than a fixed order?**
On the final set P1 and P3 made the same share of wrong flags (5.6%) and P1 decided slightly more. So we do not claim
the planner beats a good fixed order on safety; it is faster (16 vs 21–23 min) and missed fewer errors pooled
(0.7% vs 1.2%).

**Q: Why is running all tools not the safest?**
Extra readings from the less reliable tools widen the spread, so more claims end up between the two margins and go to
the TA, while the planner decides them correctly with a trustworthy pair.

**Q: What happened when the LLM chose the tools (P2)?**
It did worse: 8.1% wrong flags and 2.3× the tool time. A lookup in measured reliability beat a language model choosing.

**Q: Where do the savings come from?**
178 early hand-offs that cost no model time (the planner sees no trustworthy pair can answer, for example at an x
without a tick label) and 685 calls answered from report memory.

---

## Deeper

**Q: Why does the planner choose pairs of tools, not single tools?**
A wrong verdict needs two tools that agree on the same wrong value, because the rule only accepts or flags when the
readings agree. So what matters is how often a pair agrees wrongly, not how good each tool is alone.

**Q: Give an example of that.**
On hard line charts the VLM crop reader alone is badly wrong 40% of the time, but when it agrees with the pixel reader
both are wrong only 2.4% of the time.

**Q: How do you decide a pair is trustworthy?**
Its measured wrong-agreement must be under 5%, half the 10% wrong-flag target, and it must rest on at least 20
agreements. Tools that share a model are never each other's cross-check.

**Q: Which tool is read first?**
The member of the pair most likely to fail per second of cost, so a failure shows up before the expensive tool is paid
for.

**Q: What if the profile has little data for a situation?**
Numbers resting on fewer than 10 points or fewer than 5 charts fall back to the pooled numbers, because points on one
chart share their mistakes.

**Q: What does the memory do?**
It remembers which tool failed on which figure and series with which error code, and how far that failure reaches
(whole figure, one series, or one point), measured from calibration. It does not retry a failure that will repeat.

**Q: What is a repair?**
If the pixel reader fails because it cannot read the legend names, the VLM can read the legend once and the pixel
reader is tried again. The planner only proposes a repair that worked at least half the time in calibration and would
complete a trustworthy pair.

**Q: What if a sentence fits two figures?**
Both are checked. The claim is never flagged, because one of the figures is the wrong one; it may be accepted only if
both agree (our "both" rule).

**Q: How did you compare policies fairly?**
Every tool reading is cached, so all policies were replayed on the same readings without calling the model again
(offline replay); a missing reading is counted, never silently fetched.

**Q: How do you make sure the evaluated system is the deployed one?**
`run`, `check` and the web backend all build the agent through the same function, so a TA checking one report runs
exactly the system we evaluated.

---

## Hard questions

**Q: Isn't 5% a magic number?**
It is half the 10% wrong-flag target, so that one bad pair cannot use up the whole budget. It is in the config with
its reason, not hard-coded.

**Q: Your planner did not improve safety over P1. Why keep it?**
It uses less model time (16.2 vs 21–23 minutes per 200 claims), misses fewer errors pooled (0.7% vs 1.2%), hands off
early without paying for models, and logs every decision with the measured number behind it, which a TA can read.

**Q: Couldn't the LLM planner improve with a better prompt?**
Possibly, but it had the same evidence as P3 and still made 8.1% wrong flags. A rule that reads measured numbers is
easier to check and cannot be talked into a wrong choice by report text.
