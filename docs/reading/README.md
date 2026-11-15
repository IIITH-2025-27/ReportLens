# Reading guides and poster Q&A

Everyone first reads [00_overview.md](00_overview.md), then opens their own folder. Each folder has two files:

- `reading.md`: from the basic ideas to the full implementation of that area
- `poster_qa.md`: likely poster questions with short answers and the numbers to quote

[poster_qa_common.md](poster_qa_common.md) holds the numbers to remember and the questions anyone may get.

| Member | Area | Reading | Poster Q&A |
|---|---|---|---|
| everyone | what the system does, data flow, data contract, how to run it | [00_overview.md](00_overview.md) | [poster_qa_common.md](poster_qa_common.md) |
| Hritik | data contract, agent, tool profile, pipeline, CLI, integration tests | [hritik/reading.md](hritik/reading.md) | [hritik/poster_qa.md](hritik/poster_qa.md) |
| Vikash | OCR + pixel reader, measurement, calibration, decision rule, evaluation, baselines, safety | [vikash/reading.md](vikash/reading.md) | [vikash/poster_qa.md](vikash/poster_qa.md) |
| Harsh | dataset generator, PDF ingest, retrieval (RAG), claim finding and parsing | [harsh/reading.md](harsh/reading.md) | [harsh/poster_qa.md](harsh/poster_qa.md) |
| Karan | model loader, tool interface, neural tools, simulated tools, fine-tuning, pilots | [karan/reading.md](karan/reading.md) | [karan/poster_qa.md](karan/poster_qa.md) |

Every `reading.md` has the same levels:

| Level | What you do |
|---|---|
| 0. Background | the ideas you need before reading the code, with one or two outside references each |
| 1. Read | the files of your area in reading order, with what to look for in each |
| 2. Run | commands that exercise your area on its own, on a laptop |
| 3. Full implementation | the details that matter: edge cases, design decisions, how your part talks to the others |
| 4. Check yourself | questions you should be able to answer without opening the code |

Every `poster_qa.md` goes Basic → Results → Deeper → Hard questions. Ownership follows the team table; where git
history shows shared work, the guide says so.
