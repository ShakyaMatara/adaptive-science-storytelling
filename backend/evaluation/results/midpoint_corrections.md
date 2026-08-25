# Claims falsified or revised by the evaluation programme

Every claim this project has made about itself that the Chapter 7 measurements
contradict or qualify, with the original statement, the measurement, and the corrected
wording. This is the basis of the thesis's deviations section. Recording the trail is
more defensible than silently editing the earlier text, and several of these
corrections are themselves results.

Dated 2026-08-25. Measurements are reproducible from the CSVs named in each entry.

**A note on sourcing.** Where a claim exists verbatim in the repository, it is quoted
with its file and line. Claims made only in the midpoint report are recorded as
supplied by the supervisor; the exact wording should be checked against that document
before the thesis quotes them.

---

## 1. The rheostat / solar-system content-scaling example

**Original claim** (midpoint report, as supplied): a thin topic (rheostat) produces
one chapter while a rich topic (solar system phenomena) produces six, offered as
evidence that instructional volume is derived from textbook coverage.

**Measurement.** The two topics behave as described, but not for the stated reason.

| | `Rheostat` (G8) | `solar system phenomena` (G8) |
|---|---|---|
| chapters planned | 1 | 5 |
| richness band | thin | rich |
| passages retrieved | 1 | 13 |
| best match distance | 1.0433 | 0.7891 |
| sections actually retrieved | 1 | 3 |
| **pages the syllabus devotes to them** | **6.0** | **21.0** |

Rheostat is **not thinly covered**. The syllabus gives `Current controlling
components` (G8P2 10.3) six pages. It scored a single passage because the word is
lexically rare in the corpus and its best match sits at 1.0433, barely inside the
1.15 gate. The coverage ratio between the two topics is roughly 4:1; the system
produced a 13:1 passage ratio.

**Corrected statement.** The contrast is produced by lexical rarity, not by curricular
thinness. This example does not evidence content-derived scaling and is withdrawn.

**Evidence:** `t3_diagnostics.csv`, log `t3_diagnostics_*.log`.

---

## 2. The corpus is born-digital with clean headings usable as chunk boundaries

**Original claim** (midpoint report, as supplied): the textbook PDFs are born-digital
and their headings are clean enough to use as chunk boundaries.

**Measurement.** Contradicted by eight documented defects (`corpus_defects.md`):

- Heading detection produced **false** chapter labels from numbered table rows, which
  then propagated over the rest of the book: 124 of 160 Grade 6 chunks carried a
  materials-table row as their chapter label (FINDING-2).
- Grade 8 chapter headings are **undetectable** from the text layer at all: the chapter
  number sits alone on a line and the title wraps across two.
- Chunk page attribution was wrong for **74.5%** of chunks (FINDING-1).
- 8.8% of chunks carried doubled characters from overprinted bold (FINDING-3).
- 8.6% carry mojibake from legacy Sinhala and Tamil fonts, still unrepaired (FINDING-4).
- A page's extraction captures the facing page's material (FINDING-5).
- Symbol-font ticks were lost to Private Use Area codepoints (FINDING-7).
- **17.4% of Grade 9 Part 1's content pages carry no text layer at all** — they are
  images, and were recovered only by dual extraction (FINDING-8).

**Corrected statement.** The corpus is not uniformly born-digital. One book is
substantially image-only; heading structure is recoverable from the text layer in one
of the four grades and had to be sourced from the transcribed contents pages instead;
and several extraction defects required repair before any measurement was trustworthy.

**Evidence:** `corpus_defects.md`, `index_quality_before.csv`, `index_quality_after.csv`,
`text_quality_impact.md`, `g9p1_coverage_gap.md`.

---

## 3. Session length scales with how much of the textbook covers the topic

**Original claim**, verbatim from the repository:

> "a session's chapter count and each chapter's paragraph/question ranges come from how
> much of the grade's textbook actually covers the topic (thin → short, few/no
> questions; rich → longer, more)" — `ARCHITECTURE.md:120-123`

> "how long the story runs is driven by how much the grade's textbook actually covers
> the topic" — `README.md:210-212`

**Measurement (as designed).** Against the pages the published contents pages devote to
each topic, Spearman's rho was **-0.143** for chapter count and **-0.111** for passages
retrieved: no relationship, very slightly negative. The planner instead correlated
**+0.981** with its own retrieved passage count, which is close to arithmetic given
`chapters = ceil(total_relevant / 3)`.

The measure was dominated by lexical properties rather than coverage: rho **-0.771**
with the spread of retrieval distances, and **+0.545** with the best match's distance.
The clearest single case is `Magnitude of force` — one syllabus page, 35 passages, a
six-chapter session.

**Corrected statement (as designed).** Session length was derived from how lexically
cohesive a topic's vocabulary is, not from how much of the textbook covers it.

**Subsequent repair.** FINDING-9 replaced the relative keep-window with a fixed
relevance radius. Post-repair rho against the contents pages is **+0.411** for passage
count and **+0.27** for chapter count — a weak-to-moderate positive relationship.

**Corrected statement (post-repair).** Session length is moderately related to
curricular emphasis. The original claim of derivation from coverage remains stronger
than the evidence supports, and both measurements are reported.

**Evidence:** `t3_planner_latest.csv`, `t3_diagnostics.csv`, FINDING-9 in
`corpus_defects.md`.

---

## 4. Page-level citation

**Original claim**, verbatim from the repository:

> "the API response includes a `sources` list and the UI shows a line like *'Based on:
> Grade 7 textbook (p.16)'*" — `README.md:163-164`

**Measurement.** The cited number was wrong on two counts.

- **FINDING-1:** every chunk was stamped with the page of the most recent *heading*,
  not its own page. Only **25.5%** of chunks were attributed to a page their text
  actually appears on. Grade 6's 160 chunks collapsed onto 20 distinct page values, one
  of which carried 45 chunks — around 11,000 words on a single claimed page.
- **FINDING-6:** the number cited was the **PDF page index**, which appears nowhere in
  the printed book. It was also a single page for chunks spanning up to five: **82.7%**
  of chunks span more than one page.

**Corrected statement.** Page attribution is now correct for **97.5%** of chunks, and
citations name the **printed** page or page range (`pp. 15-16`), derived from a
per-book offset validated against 272 contents-page entries at 100% agreement.
Citations for the 5.5% of chunks in front and back matter fall back to the PDF page,
and 3.2% of chunks cite text recovered from page images rather than from a text layer.

**Evidence:** `corpus_defects.md` FINDINGS 1 and 6, `toc_page_validation.csv`,
`chunk_page_spans.csv`.

---

## 5. The richness classification discriminates content volume

**Original claim**, verbatim: "thin → short, few/no questions; rich → longer, more"
(`ARCHITECTURE.md:121-122`), implying three working bands.

**Measurement (as designed).** Of 39 planned topics, **none** fell in the thin band:
passage counts ranged 4 to 35, median 11, so the `thin` threshold of two passages was
**unreachable** for any topic the gate accepts. All 14 deliberately narrow
single-concept sections — including four occupying a single syllabus page — were
classified `rich`.

**Corrected statement (as designed).** The thin band was inert; the classification
distinguished two bands, not three.

**Post-repair.** The bands are now populated: thin 4 topics, moderate 14, rich 21.
`RICHNESS_RANGES` was not altered.

**Evidence:** `t3_planner_latest.csv`, `t3_diagnostics.csv`.

---

## 6. Grade-scoped retrieval is an invariant

**Original claim** (implicit in the design and in the harness's own framing): grade
filtering is an invariant rather than a label, so a topic belonging to a higher grade
is refused at a lower one.

**Measurement.** The grade-boundary family is the **weakest** of the seven probe
families at **16/20 (0.80)**. Four topics leak into Grade 6: `Electric circuits`
(0.7061), `Work power and energy` (0.7393), `Respiration in living organisms` (0.8899)
and `Reflection of light and mirrors` (1.0427) — the first two comfortably inside the
gate.

**Corrected statement.** Grade filtering restricts *which* chunks are searched, but it
does not prevent a higher-grade topic being accepted at a lower grade when the lower
grade's book contains related material. It is an invariant over the corpus, not over
the curriculum.

**Evidence:** `t1_gate_verbatim_latest.csv`, `t1_gate_by_family_verbatim_latest.csv`.

---

## 7. The deterministic anti-cheat gate catches paraphrased quiz questions

**Original claim**, verbatim from the code: the layer-1 similarity check exists so that
"a heavy paraphrase can slip under it" is a noted risk (`views.py:97-98`), implying
partial coverage.

**Measurement.** Layer 1 catches **0 of 12** full paraphrases — not partial coverage but
none. It blocks verbatim, surface and lexical attacks completely (36/36) and half of
reorderings (6/12), with zero false positives.

More importantly, paraphrased attacks and legitimate questions are **not separable by
similarity at all**: means 0.3570 and 0.3540, Cohen's d **0.0275**, with all twelve
paraphrases falling inside the legitimate class's range. The best threshold that could
exist reaches 58.3% accuracy against a 50% baseline, and only by wrongly blocking eight
of twelve legitimate questions.

**Corrected statement.** No similarity threshold can separate paraphrased attacks from
legitimate questions. The layer-2 model instruction is architecturally necessary rather
than a backstop, and this is a proof of necessity rather than a performance shortfall.

**Evidence:** `t2_anticheat_latest.csv`, `t2_anticheat_sweep_latest.csv`,
`t2_paraphrase_vs_legitimate_latest.csv`.

---

## 8. Refusal accuracy under realistic phrasing

**Original position.** T1 recall was to be reported as a single figure.

**Measurement.** Under contents-page phrasing recall is 0.975; under learner phrasing it
is also 0.975. Reporting that as robustness would be misleading. Mean decision headroom
falls from 0.350 to 0.303, two topics move within 0.05 of the threshold where none was
before, the failure set swaps in both directions, and the sweeps diverge sharply once
the threshold tightens — at 0.90 verbatim recall is 0.775 against paraphrased 0.525.

**Corrected statement.** Recall is robust to paraphrase in aggregate at the configured
threshold, but the safety margin is not. The gate appears paraphrase-robust largely
because the threshold is loose.

**Evidence:** `t1_verbatim_vs_paraphrased.csv`, `t1_gate_margins_*_latest.csv`.
