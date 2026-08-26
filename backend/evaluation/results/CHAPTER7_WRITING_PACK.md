# Chapter 7 writing pack

Everything needed to write sections 7.3–7.10 without reopening a CSV. Every number below
is stated as a finished sentence carrying its own `n`, its uncertainty where one exists,
and the file it came from. Where a caveat must travel with a number, the caveat is inside
the sentence — do not lift the figure out of it.

**Rule for the whole chapter.** Every figure traces to a CSV written by an `eval_*`
management command or by a committed script in `evaluation/analysis/`. No number in this
pack was entered by hand. Generation runs at temperature 0.7, so what is reproducible is
the procedure, not the sample.

**Standing caveats that recur.** Four caveats attach to more than one section and are
repeated in every sentence that needs them rather than stated once:

1. **T4's effect size spans +0.287 to +0.536 across three runs.** Never quote one run's
   figure as *the* effect.
2. **The judge validation is one annotator, twelve chapters.** No human–human agreement
   figure exists to set against the human–judge one.
3. **2.8% of grounded generations returned a canned fallback silently.**
4. **Faithfulness is not accuracy, and has no recall counterpart.**

---

## 7.3 — Corpus preparation and ingestion defects

### Numbers to report

- **Eleven defects were found and recorded; six of the nine corpus defects were repaired
  with quantified before/after measurement and three remain documented limitations**
  (`corpus_defects.md`). Findings 10 and 11 were found by *using* the harness rather than
  by inspecting the corpus and are recorded in the same file for continuity of the audit
  trail.
- **Page attribution was correct for 25.5% of chunks before repair and 97.5% after**,
  measured over the whole index (`index_quality_before.csv`, `index_quality_after.csv`).
  The defect was that the page counter was never reset between buffered chunks.
- **Chapter labelling recovered from 0 / 18 / 0 / 0 genuine chapters at Grades 6–9 to
  11 / 19 / 15 / 19**, after the regex heading detector was abandoned in favour of lookup
  against the transcribed tables of contents (`index_quality_before.csv`,
  `index_quality_after.csv`). The clearest single indicator is Grade 6's
  `max_chunks_per_page`, which fell from **45 to 2**: 45 chunks sharing one page number is
  not a plausible book.
- **Distinct pages represented in the index rose from 20 to 148 at Grade 6, 53 to 149 at
  Grade 7, 64 to 147 at Grade 8 and 57 to 175 at Grade 9** (same two files).
- **Doubled characters from overprinted bold affected 8.8% of chunks before repair and
  0.6% after**, removed by `pdfplumber.dedupe_chars(tolerance=1.0)`
  (`text_quality_impact.md`).
- **Mojibake from legacy Sinhala and Tamil fonts affects 8.6% of chunks and is NOT
  repaired**; it is a documented limitation, and it causes 4 of T1's 14 false positives
  (`text_quality_impact.md`, `t1_gate_counterfactual_*_latest.csv`).
- **82.7% of chunks span more than one printed page**, which is why single-page citations
  were wrong and why citations now name a printed range (`chunk_page_spans.csv`).
- **Symbol-font ticks lost to Private Use Area codepoints affected 0.8% of chunks before
  repair and 0.0% after** (`text_quality_impact.md`).
- **17.4% of `G9P1.pdf` was distributed as image-only pages and was recovered by dual
  extraction**; 19 pages totalling 25,006 characters were transcribed twice, by Tesseract
  v5.5.3 and by vision transcription, and admitted only where the two agreed
  (`g9p1_coverage_gap.md`, `ocr_dual_extraction.csv`).
- **3.2% of the final index is recovered from page images rather than read from a text
  layer**, and every experiment reports its own exposure separately (`ocr_dual_extraction.csv`).
- **Facing-page text captured into a page's extraction inflates `total_relevant` by
  0.76%**; documented, not repaired (`duplicate_impact.csv`).
- **The page-mapping repair was validated against 272 contents-page entries with 100%
  agreement** (`toc_page_validation.csv`). The final index holds **1,122 chunks** across
  seven books.
- **37.7% of index chunks contain the books' own apparatus rather than exposition** — 366
  chunks (32.6%) carry exercise or assignment material, 80 (7.1%) carry trilingual
  *Technical Terms* glossaries, and 59 (5.3%) carry runs of two or more question stems.
  The share falls monotonically with grade: **51.9% at Grade 6, 44.0% at Grade 7, 34.0% at
  Grade 8 and 30.1% at Grade 9** (`index_assessment_content_latest.csv`). **State the
  limitation with the number: the classifier detects whether a chunk *contains* such
  material, not whether it *is* such material.**

### Figure

No figure is generated for 7.3. Use a two-column before/after table built from
`index_quality_before.csv` and `index_quality_after.csv`; the `max_chunks_per_page` row
carries the argument on its own.

### Failures and limitations this section must state

- Three of nine corpus defects are **documented, not repaired**: mojibake (8.6% of
  chunks), facing-page capture (0.76% inflation), and doubled characters in the residual
  0.6%.
- The corpus is **English medium only**. The Sinhala and Tamil editions are not evaluated,
  and the mojibake defect means the corpus's own non-English content is unusable.
- Defect classification was performed by **one annotator**.
- Recovered text is a **model transcription of a page image**, so any score computed
  against it measures consistency with that transcription, not fidelity to the book.

### Midpoint claims this section supersedes

- **Correction 2 — "the corpus is born-digital with clean headings usable as chunk
  boundaries."** Contradicted by eight documented defects. Heading detection by regex
  matched table rows as chapter titles; the repaired pipeline does not detect headings at
  all, it looks them up in the transcribed contents pages.
- **Correction 4 — "the UI shows a line like *Based on: Grade 7 textbook (p.16)*."** The
  cited number was the PDF page index, not the printed folio, and 82.7% of chunks span
  more than one page, so a single page number was wrong twice over.

---

## 7.4 — T1: curricular boundary enforcement

### Numbers to report

- **At the configured threshold of 1.15 the syllabus gate achieves recall 0.9750 and
  specificity 0.9222 (accuracy 0.9318, precision 0.7358, F1 0.8387) over 40 positive and
  180 negative probes, and the figures are identical under both query conditions**
  (`t1_gate_verbatim_latest.csv`, `t1_gate_paraphrased_latest.csv`).
- **The identical headline conceals a real difference in margin.** Under contents-page
  phrasing the mean decision margin on in-syllabus probes is 0.350 (sd 0.142, n = 40) with
  **zero** probes within 0.05 of the threshold; under learner phrasing it is 0.303
  (sd 0.156, n = 40) with **two** (`t1_gate_margins_verbatim_latest.csv`,
  `t1_gate_margins_paraphrased_latest.csv`).
- **The conditions diverge as the threshold tightens.** At 0.90 recall is 0.775 under
  contents-page phrasing against 0.525 under learner phrasing — a 25-point gap that is
  invisible at 1.15 (`t1_gate_sweep_verbatim_latest.csv`,
  `t1_gate_sweep_paraphrased_latest.csv`). **The apparent robustness is a property of a
  loose threshold, not of the gate.**
- **F1 is maximised at threshold 1.00 (0.9114), not at the configured 1.15 (0.8387)**;
  the configured value trades precision for recall deliberately, and that trade is stated
  rather than optimised away (`t1_gate_sweep_verbatim_latest.csv`).
- **Grade-boundary probes are the weakest family at 16/20 correct (0.800, mean best
  distance 1.282, sd 0.245), and all four leaks are into Grade 6**
  (`t1_gate_by_family_verbatim_latest.csv`). Other-subject follows at 35/40 (0.875) and
  pseudo-scientific at 18/20 (0.900); advanced-science and nonsense are perfect at 40/40
  and 20/20.
- **Specificity is 0.9222 as measured and 0.9444 on a clean-corpus counterfactual**;
  4 of the 14 false positives disappear when FINDING-4 mojibake chunks are excluded, all
  four of them `Sinhala grammar and sentence construction`, whose best distance moves from
  1.11–1.13 to 1.21–1.41 (`t1_gate_counterfactual_verbatim_latest.csv`,
  `t1_false_positive_analysis.md`). **Report the measured figure first; the corpus that
  was evaluated is the corpus that was built.** The remaining six false positives survive
  exclusion and are genuine semantic near-misses.
- **One positive was refused**: `Neutralisation` at Grade 8, best distance 1.1649 against
  a 1.15 threshold — over by 1.4%. The same topic is accepted at 0.9581 when phrased as
  *"what happens when an acid meets a base"* (`t1_verbatim_vs_paraphrased.csv`).
- **Six of the 53 accepted topics draw on recovered text, none wholly; the mean recovered
  share among those six is 19.5%**, highest at `Structure of the human heart` with 5 of 11
  passages (`t1_gate_verbatim_latest.csv`).

### Figures

**`fig_t1_sweep.png`** — *Gate recall, specificity and F1 across candidate values of
`GATE_MAX_DISTANCE`, under contents-page and learner phrasing. The configured threshold
of 1.15 is marked. Recall is identical under both phrasings at the configured value and
diverges by 25 points at 0.90, so the gate's insensitivity to phrasing is a property of
the loose threshold rather than of the gate.*

**`fig_t1_distances.png`** — *Distribution of the smallest embedding distance per probe,
by probe family (n = 220). The grade-boundary family overlaps the in-syllabus
distribution most, which is why it is the weakest at 16/20.*

### Failures and limitations this section must state

- **Grade-scoped retrieval is not an invariant.** 4 of 20 grade-boundary probes leak, all
  into Grade 6.
- **A corpus defect causes gate failures**: 4 of 14 false positives are caused by
  FINDING-4 mojibake, not by semantic near-misses.
- **Probe curation and paraphrase authoring were performed by one annotator.** The
  positive set was curated strictly from the textbook contents pages and never from gate
  behaviour; the paraphrased set was authored blind. Both protocols mitigate, neither
  removes, the single-annotator limitation.
- **An anomaly that did not generalise, and must be reported as such**: a learner's
  phrasing outperformed the textbook's own heading on `Neutralisation`, but ρ between
  heading length and paraphrase shift is **+0.085** — a null result over 40 topics. It is
  a striking single case, not a pattern.

### Midpoint claims this section supersedes

- **Correction 6 — "grade-scoped retrieval is an invariant."** It is a label, not an
  invariant: the grade-boundary family is the weakest at 0.800.
- **Correction 8 — "refusal accuracy under realistic phrasing" was to be reported as a
  single figure.** Two conditions are now reported, because a single figure would have
  concealed the margin difference above.

---

## 7.5 — T2: assessment integrity

### Numbers to report

- **The deterministic similarity gate blocks 100% of verbatim, surface and lexical
  attacks (12/12 each), 50% of reordered attacks (6/12) and 0% of paraphrased attacks
  (0/12), while blocking none of the 12 legitimate questions** — overall precision 1.000,
  specificity 1.000, recall 0.700, F1 0.8235 (`t2_anticheat_latest.csv`,
  `t2_anticheat_by_class_latest.csv`).
- **Paraphrased attacks and legitimate questions are statistically indistinguishable by
  surface similarity**: mean difference +0.0030, Cohen's d **+0.0275** — an effect size of
  essentially zero — with paraphrases spanning 0.176–0.512 and legitimate questions
  0.133–0.525, and **all 12 paraphrases falling inside the overlapping interval**
  (`t2_paraphrase_vs_legitimate_latest.csv`).
- **No threshold can separate the two classes.** The best accuracy achievable by any
  single similarity threshold is **58.3%** against a chance rate of 50.0%, and achieving
  it costs wrongly blocking **8 of 12** legitimate questions
  (`t2_anticheat_sweep_latest.csv`).

### Figures

**`fig_t2_sweep.png`** — *Attack catch rate against legitimate false-block rate across
similarity thresholds. No operating point separates paraphrased attacks from legitimate
questions: the two curves move together, which is the evidence that a second,
model-based layer is architecturally necessary.*

**`fig_t2_by_class.png`** — *Block rate by perturbation class (n = 12 per class). The
cliff between lexical (1.000) and paraphrase (0.000) locates exactly where surface
similarity stops working.*

### Failures and limitations this section must state

- **Layer 1 catches nothing that is genuinely paraphrased.** This is a limitation of the
  mechanism, not a tuning failure, and the chapter should present it that way.
- **Twelve base questions, one annotator.** The perturbation classes were authored by one
  party, and n = 12 per class is small.
- T2 uses **no retrieval and no model**, so it is unaffected by every corpus defect in
  7.3 — worth stating, because it makes T2 the cleanest result in the programme.

### Midpoint claims this section supersedes

- **Correction 7 — "a heavy paraphrase can slip under it,"** implying partial coverage.
  Coverage is not partial: layer 1 catches **0 of 12** full paraphrases. The risk noted in
  the code comment is the entire behaviour of the class.

---

## 7.6 — T3 and T3b: content-derived instructional scaling

### Numbers to report

- **As designed, session length was uncorrelated with curricular emphasis**: Spearman's
  ρ between the pages the published contents pages devote to a topic and the planner's
  chapter count was **−0.143** (n = 39), and −0.111 for passage count
  (`t3_planner_latest.csv`, `ground_truth.csv`).
- **The cause was a design error, not a threshold choice.** The keep-window was
  *relative* — every passage within +65% of the best hit's distance — so a topic that
  matched the corpus worse was credited with a wider window and therefore more content.
  Passage count correlated **+0.545** with the best hit's distance and **−0.771** with the
  spread of retrieval distances, so it tracked lexical cohesion roughly seven times more
  strongly than curricular coverage (`t3_diagnostics.csv`).
- **After the FINDING-9 repair — a fixed relevance radius of 1.15 — ρ rises to +0.270 for
  chapter count and +0.411 for passage count (n = 39)** (`t3_planner_latest.csv`). **Both
  figures are permanent; the repaired figure replaces the original nowhere.**
- **A magnitude-matched control excludes the rival explanation.** The repair reduces mean
  passages from 12.43 to 7.22; applying the original relative rule truncated to the top 8
  reproduces the magnitude (7.33 passages) and **none** of the improvement (ρ = −0.133
  against the as-designed −0.134). Across truncation from N = 3 to N = 15 the correlation
  never rises above 0.000 (`t3_diagnostics.csv`).
- **The repair is partial and this must be stated.** The dependence on match quality was
  **inverted, not eliminated**: ρ(best distance, passage count) moved from +0.545 to
  **−0.634**. This is intrinsic to measuring density within a fixed radius — if the
  nearest chunk is far, every chunk is far.
- **1.15 was not the best-scoring value.** `RELEVANCE_RADIUS = GATE_MAX_DISTANCE` because
  the system already uses 1.15 to decide whether a topic is in the book at all; 0.95
  scores +0.419 and 1.20 scores +0.466. A value that follows from the existing design was
  preferred over a value selected from a sweep, and the correlation is positive and stable
  across 0.85–1.30, which is what identifies a mechanism defect rather than a parameter
  choice.
- **The richness bands went from unusable to populated**: thin/moderate/rich held
  0 / 7 / 32 topics as designed and 4 / 14 / 21 after repair (n = 39,
  `t3_planner_latest.csv`).
- **T3b — fixed-length planning starves thin topics.** Over the eight thinnest topics,
  content-derived planning gives **1.75 passages per chapter** against **0.92** under a
  forced three chapters, and mean words demanded per grounding passage rises from
  **157.0 to 268.1 — 71% more prose from each passage**. All eight topics move in the same
  direction; **four fall below one passage per chapter**, meaning chapters with no
  grounding evidence at all, and the worst case rises 154% (`t3_ablation_latest.csv`).
- **Three of 39 topics draw on recovered text; recovered passages are 8 of 289 counted
  (2.8%)**, worst at `Magnitude of force` with 4 of 5 (`t3_planner_latest.csv`).

### Figures

**`fig_t3_scatter.png`** — *Contents-page coverage against planned session length, before
and after the FINDING-9 repair (n = 39 topics). The as-designed relationship is flat to
slightly negative (ρ = −0.143); after repair it is weakly positive (ρ = +0.270). Both are
plotted because the repaired figure supersedes the original nowhere.*

**`fig_t3_richness.png`** — *Chapter and question budgets by richness band, before and
after repair. As designed no topic reached the thin band, so one of three configured
bands was unreachable.*

### Failures and limitations this section must state

- **The repaired result is weak.** ρ = +0.270 for chapter count is weak to moderate and
  **does not establish** that instructional volume is derived from curricular emphasis.
  The chapter must say the original claim remains stronger than the evidence supports.
- **The repair is partial**: the match-quality dependence inverted (+0.545 → −0.634)
  rather than vanishing, and the cohesion dependence only halved (−0.771 → −0.333).
- **Three of the six correlations reported are internal proxies**, derived from the same
  retrieval call, and are **not independent evidence**. The passage-count correlation is
  close to arithmetic given `chapters = ceil(passage_count / 3)`.
- **This is an evaluation-driven design change**, not a tuning adjustment, and the chain
  from measurement to redesign is recorded in `corpus_defects.md` under FINDING-9 with a
  dated record.

### Midpoint claims this section supersedes

- **Correction 1 — the rheostat / solar-system example**, offered as evidence that
  instructional volume derives from textbook coverage. Superseded by the measured ρ, both
  as designed and after repair.
- **Correction 3 — "a session's chapter count and each chapter's paragraph/question
  ranges come from how much of the grade's textbook actually covers the topic."**
  Falsified as designed (ρ = −0.143) and only weakly supported after repair (+0.270).
- **Correction 5 — "the richness classification discriminates content volume."** As
  designed, **none** of 39 topics fell in the thin band: one of three bands was
  unreachable.

---

## 7.7 — T4: groundedness ablation

### Numbers to report

- **Retrieval grounding raises measured faithfulness from 0.566 (sd 0.241, n = 12) to
  0.853 (sd 0.330, n = 12), a difference of +0.287 that is statistically significant
  (Mann–Whitney U = 22.5, z = 2.907, p = 0.00365), and reduces unsupported claims from
  3.08 to 0.83 per chapter (U = 18.0, p = 0.0014)** — a safety property rather than an
  accuracy improvement (`t4_faithfulness_summary_latest.csv`,
  `t4_significance_latest.csv`). Cohen's d = 0.993. All 24 judgements were usable and none
  reported a claim total inconsistent with the claim list it returned.
- **Every chapter in both conditions had zero contradicted claims.** Ungrounded generation
  invents material the book does not cover; it does not assert the opposite of what the
  book says (`t4_faithfulness_latest.csv`).
- **One of the twelve rag_on chapters was not a grounded generation at all**, and the
  figures must be given both ways. `generate_chapter` fell through both parse attempts and
  returned the canned fallback from `core/llm.py:414`; the judge scored a generic essay on
  scientific method against four passages about mirrors. **Excluding it, grounding raises
  faithfulness from 0.566 to 0.930 (sd 0.200, n = 11), a difference of +0.364 (d = 1.644,
  U = 11.0, p = 0.00054)** (`t4_fallback_sensitivity_latest.csv`). **The as-measured figure
  answers "what does a learner receive end to end"; the fallback-excluded figure answers
  "does retrieval constrain generation when generation succeeds". Neither replaces the
  other and neither may be quoted without saying which question it answers.**
- **Detection of the fallback is deterministic and needs no judgement** — in `rag_on` the
  application always attaches source refs, so `sources_attached == 0` means the fallback
  fired. Applied retrospectively across all three runs: **1 of 36 grounded generations
  (2.8%)**, 0 in runs 1 and 2 (`t4_fallback_sensitivity_latest.csv`).
- **The effect size is not stable across runs and must never be quoted from one run.**
  Across three runs it is **+0.536, +0.401 and +0.287**, significant in every one. Runs 2
  and 3 are identical in every configurable respect — same twelve topics, same prompts,
  same index, same primary judge, same token budget — and differ only in the sample drawn
  at temperature 0.7. Paired chapter by chapter (n = 24) the mean absolute movement is
  **0.119**, with 10 of 24 chapters unchanged (`t4_generation_variance_latest.csv`).
  **The defensible statement is that retrieval grounding produces a large, reliably
  significant increase in faithfulness whose magnitude cannot be pinned down to better
  than roughly ±0.12 from twelve chapters per condition.**
- **The judge is validated against blind human scoring at Spearman ρ = +0.971 with a mean
  absolute difference of 0.039 over twelve chapters, 10 of 12 agreeing within 0.10 and 9
  of 12 within 0.05** (`t4_human_agreement_latest.csv`,
  `t4_human_validation_latest.csv`). **State the boundary in the same sentence: this is
  one annotator scoring twelve chapters from six topics, with no second human and
  therefore no human–human agreement figure to compare against.**
- **The ablation conclusion survives human scoring and is slightly larger under it**:
  0.450 → 0.870 (+0.420) by hand against 0.503 → 0.872 (+0.369) by the judge on the same
  twelve chapters (`t4_human_ablation_latest.csv`). **Both disagreements above 0.10 are
  `rag_off` rows where the human scored lower**, so the judge is mildly lenient on
  ungrounded prose and the measured effect is biased downwards, not up.
- **The two scorers atomise claims differently and still agree on the ratio**: the human
  extracted 10.00 claims per chapter against the judge's 7.42 — 35% more — and the counts
  correlate at only ρ = +0.600 while the ratios correlate at +0.971
  (`t4_human_validation_latest.csv`). Faithfulness is robust to the granularity at which
  claims are cut, which is not obvious in advance. The hand-written ratios agree with the
  counts recorded beside them in 12 of 12 cases.
- **Inter-judge agreement, six chapters scored by both models on identical evidence and
  prose, is ρ = +0.718, +0.727 and +0.898 across the three runs**, with mean absolute
  differences of 0.152, 0.186 and 0.032 (`t4_interjudge_agreement_latest.csv`,
  `t4_interjudge_agreement_gemini_run1_latest.csv`,
  `t4_interjudge_agreement_deepseek_primary_latest.csv`). `Weather` rag_on diverged
  severely in runs 1 and 2 (1.000 vs 0.286; 0.700 vs 0.000) and by only 0.067 in run 3, so
  **the divergence is a property of particular generations, not of the topic.**
- **Faithfulness is not accuracy.** The `Weather` rag_on chapter scored 0.333 on nine
  claims; the six unsupported ones — *a thermometer measures temperature*, *humidity is
  the amount of water vapour in the air*, *weather is not the same as climate* — are all
  **true**, and simply absent from the two passages retrieved. The second judge marked the
  same claims unsupported (`t4_chapters_latest.json`).
- **Faithfulness is also blind to specificity.** The ungrounded `Geomagnetism` chapter
  scored **0.82** by asserting that magnetic north is *"not exactly the same as"*
  geographic north, where the grounded chapter gave the north-west offset. Both are
  faithful; one is informative. **On well-covered topics the generator's parametric
  knowledge overlaps the textbook heavily enough that faithfulness alone will not separate
  the conditions** (`t4_chapters_latest.json`).
- **Two of the twelve topics are grounded entirely on the book's apparatus.** For
  `Weather` at Grade 6, `total_relevant = 2` and both passages are furniture: 520
  characters of trilingual *Technical Terms* glossary, and an exercise page carrying a
  fill-in-the-blank stem, a June 2012 Colombo data table, five unanswered questions and
  the same glossary repeated. Neither defines weather, climate, humidity, thermometer,
  rain gauge, anemometer or wind vane, and **3.28% of the evidence block's characters are
  FINDING-4 mojibake — the first measured case of that defect reaching a learner-facing
  generation** (`t4_evidence_composition_latest.csv`, `t4_chapters_latest.json`).
- **Higher faithfulness sits on larger evidence bases, not smaller ones.** Within rag_on,
  ρ(evidence characters, faithfulness) = **+0.514** and ρ(`total_relevant`, faithfulness)
  = +0.080; the thin band scores lowest in both conditions (rag_on 0.667, moderate 0.975,
  rich 0.833) and the nine chapters scoring exactly 1.000 sit on a mean evidence base of
  5,256 characters against 3,690 for the three below it
  (`t4_faithfulness_by_evidence_base_latest.csv`, `t4_faithfulness_by_richness_latest.csv`).
  **A prior hypothesis that high faithfulness would concentrate on thin topics was tested
  and falsified**; the mechanism is that a thin topic must fill the same paragraph budget
  from less evidence, so the model goes beyond it.
- **Provenance**: 20 chapters were grounded on the text layer only (mean faithfulness
  0.693) and 4 included recovered text (0.789). **At n = 4 this supports no inference**,
  and where grounding includes recovered text the judge scores against a model
  transcription of a page image rather than the book
  (`t4_faithfulness_by_provenance_latest.csv`).

### Figure

**`fig_t4_ablation.png`** — *Faithfulness with and without retrieval grounding, twelve
topics per condition, scored by `google/gemini-3.7-flash` against the same textbook
evidence in both conditions. The grounded mean of 0.853 includes one chapter that came
from the application's canned fallback path rather than from generation; excluding it the
mean is 0.930. Effect sizes across three runs of this experiment span +0.287 to +0.536.*

### Failures and limitations this section must state

- **Run 1 lost 7 of 24 judgements (29%)**, all `deepseek-v4-flash` returning invalid JSON,
  leaving an unbalanced 10-against-7 design. It is retained as evidence that judge choice
  determines the usable sample.
- **The effect size is judge-dependent and generation-dependent.** ±0.135 from swapping
  the scorer on identical prose; ±0.114 from re-sampling at temperature 0.7.
- **The generation fallback is silent.** A learner receives a generic chapter under the
  requested topic's title, with no sources and no indication anything went wrong.
- **A multiple-choice question leaked into one chapter's narrative** — the model wrote
  three questions, two reached the `questions` field and the third was emitted inside
  `paragraphs`, so a learner would read the three wrong options as part of the story. One
  of 24; found by reading, not by any metric.
- **Faithfulness has no recall counterpart.** The programme measures precision against the
  evidence and never measures how much of the evidence a chapter delivers. **A coverage or
  detail-retention metric is the single most valuable addition the evaluation could take**
  and is recorded as future work, because it needs a per-passage fact inventory that does
  not exist.
- **The judge validation is one annotator on twelve chapters.**

### Midpoint claims this section supersedes

None directly. T4 did not exist at the midpoint. It supplies the evidence for the
groundedness claim that the midpoint report asserted without measurement, and its
FINDING-11 fallback rate qualifies any claim that the system always grounds its output.

---

## 7.8 — T5: difficulty adaptation validity

### Numbers to report

- **All three surface readability measures move monotonically with the configured
  difficulty**: Flesch–Kincaid Grade Level ρ = **+0.770**, Flesch Reading Ease ρ =
  **−0.710**, words per sentence ρ = **+0.695**, over 40 generations (5 levels × 2 topics ×
  4 repetitions) (`t5_difficulty_latest.csv`).
- **Type–token ratio does not move as predicted**: ρ = **+0.090**, effectively null. The
  model lengthens sentences without broadening vocabulary
  (`t5_difficulty_latest.csv`).
- **Mean FKGL rises from 5.73 (sd 0.69) at level 1 to 11.28 (sd 2.92) at level 5**, with
  n = 8 per level; mean Flesch Reading Ease falls from 72.5 to 49.8 and mean length rises
  from 235 to 358 words (`t5_difficulty_latest.csv`).
- **The extremes are strongly separated but the middle of the ladder is not.** Level 1
  against level 5 gives Cohen's d = **2.61**; adjacent pairs give d = 1.55 (1→2,
  separated), 0.81 (2→3, partial), **0.48 (3→4, collapsed)** and **0.67 (4→5, collapsed)**
  (`t5_adjacent_separation_latest.csv`).
- **Twelve of sixteen samples overlap on each of the three upper adjacent pairs**, and
  per-level ranges overlap heavily — level 3 spans FKGL 6.6–11.5 and level 5 spans
  7.1–16.1, **so a level-5 chapter can be easier than a level-3 chapter**. Variance grows
  four-fold across the ladder (`t5_difficulty_latest.csv`).
- **State the imprecision with the effect sizes**: each level rests on n = 8, so the
  Cohen's d values are point estimates with wide confidence intervals, and the d = 0.8
  boundary between "partial" and "collapsed" must not be read as a sharp threshold. **What
  the data support is the ordering and the direction, not the exact effect size of any
  single adjacent pair.**

### Figure

**`fig_t5_difficulty.png`** — *Flesch–Kincaid Grade Level against configured difficulty,
n = 8 generations per level. The trend is monotonic (ρ = +0.770) but per-level
distributions overlap from level 3 upwards, so the ladder resolves two or three usable
bands rather than five.*

### Failures and limitations this section must state

- **Three of five difficulty levels are not separable at n = 8 per level.** The
  configured five-band ladder reliably resolves two or three.
- **Readability formulae measure surface linguistic complexity, not conceptual
  difficulty.** FKGL cannot distinguish a hard idea in simple words from an easy idea in
  complex ones, and the null type–token result is direct evidence that the model is
  manipulating surface form rather than conceptual load.
- **n = 8 per level, two topics.** The topic factor is not separable from the level factor
  at this sample size.
- **T5's cost is not instrumented** — `eval_difficulty` calls `llm.generate_chapter`,
  which returns no usage data.

### Midpoint claims this section supersedes

None. The midpoint report made no quantitative claim about difficulty separability. This
section is the first evidence on the point, and it qualifies the five-level design.

---

## 7.9 — T6: model selection benchmark

### Numbers to report

- **The configured model is the only candidate of five that simultaneously clears all
  three bars**: `openai/gpt-5.4-mini` achieves 5/6 first-attempt schema compliance
  (0.833), the lowest median latency in the field at **5.76 s**, and mean FKGL 8.77 inside
  the target band, at US$0.00417 per chapter (`t6_models_summary_latest.csv`).
- **`google/gemini-3.7-flash` is the only model with perfect schema compliance (6/6)** but
  its mean FKGL of 11.57 is outside the target band and its median latency is 14.26 s —
  2.5× the configured model's (`t6_models_summary_latest.csv`).
- **`deepseek/deepseek-v4-flash-0731` is a credible alternative at one eleventh of the
  cost** — US$0.00036 per chapter against US$0.00417 — with readability in band, but
  4/6 compliance and a median latency of 46.26 s, an eight-fold penalty
  (`t6_models_summary_latest.csv`).
- **`openai/gpt-5.6-luna` scores 3/6 and `qwen/qwen3.8-27b` 1/6.** `qwen` exhausted the
  application's own 3,000-token budget on five of six prompts: **a deployment property
  rather than a measurement artefact** — the model is too verbose to complete a chapter
  within the budget the system allots (`t6_models_latest.csv`).
- **11 of 30 first-attempt generations failed across the field**, in two distinct shapes:
  mid-object truncation where the model ran long, and genuinely malformed output — `qwen`
  produced an unterminated string and an empty response. **The application's single retry
  recovers the first kind more reliably than the second** (`t6_models_latest.csv`).
- **Costs are indicative of 2026-08-25 prices**, recorded in `harness.PRICES_PER_MTOK` and
  taken live from the provider's model endpoint on that date.

### Figure

**`fig_t6_models.png`** — *First-attempt schema compliance, median latency and cost per
chapter for five candidate models, n = 6 prompts each, generated through the
application's own prompt and token budget with no retry. The configured model is the only
one clearing schema compliance, latency and readability simultaneously.*

### Failures and limitations this section must state

- **n = 6 prompts per model.** A compliance rate of 5/6 has a wide confidence interval and
  the ranking between adjacent models is not established.
- **The benchmark's first run was voided by a measurement artefact** — the harness capped
  output at 1,400 tokens while the application allots 3,000, so `gemini-3.7-flash` scored
  0/6 by being truncated. Corrected to `llm._max_tokens_for()`; the same model then scored
  6/6. This must be reported in the methodology, not buried.
- **Provider prices and model availability change.** All costs are indicative of a single
  date.
- **No model was tested for factual quality here** — T6 measures schema compliance,
  latency, readability and cost only. Faithfulness is T4's question.

### Midpoint claims this section supersedes

None. The midpoint report asserted the model choice without evidence; T6 supplies it.

---

## 7.10 — Functional testing

### Numbers to report

- **`python manage.py test core` passes 27 tests**, unchanged from the baseline recorded
  before any modification in this programme and re-verified after every repair, including
  the ingestion rebuild, the FINDING-9 retrieval change and the FINDING-10 harness change.
- **The application's tuning constants were not altered to improve any result.** One
  constant changed during the programme — the relative keep-window was replaced by a fixed
  `RELEVANCE_RADIUS` — and that change is recorded as an evaluation-driven **design**
  change with a dated record, a mechanism justification, a magnitude-matched control, and
  both the before and after figures reported permanently (FINDING-9, `corpus_defects.md`).
  `GATE_MAX_DISTANCE`, `SIMILARITY_THRESHOLD`, `RICHNESS_RANGES`, `PASSAGES_PER_CHAPTER`,
  `START_DIFFICULTY`, `CHAPTER_UP_THRESHOLD`, `CHAPTER_DOWN_THRESHOLD` and
  `MAX_CHAPTERS_CAP` are untouched.
- **One recommended threshold change was deliberately NOT applied**: the T1 sweep shows
  `GATE_MAX_DISTANCE = 1.10` improves specificity, but it was left at 1.15 and the
  recommendation recorded instead, because changing a constant after seeing the result it
  improves and then reporting it as the original design would misrepresent the work.
- **Total measured API spend was approximately US$0.65 against a US$5.00 cap**, of which
  US$0.4082 is instrumented across 339 calls (`RESULTS_SUMMARY.md` §10).

### Figure

None. Use the test output verbatim.

### Failures and limitations this section must state

- **Cost tracking is incomplete.** 56 of 140 paid calls in the original budget are not
  instrumented, because `eval_difficulty` and `eval_planner --ablate` call
  `llm.generate_chapter`, which returns no usage data. Their cost is **derived from the
  token profile measured in T6**, not measured.
- **The provider account reports lifetime usage only and no pre-run baseline was taken**,
  so the account figure cannot corroborate the total.
- **27 unit tests is a regression guard, not a correctness proof.** They establish that
  the repairs did not break the application; they do not establish that the application is
  correct.
- **No classroom deployment and no human participants.** Every result in Chapter 7 is a
  property of the system measured in isolation. **Nothing in this chapter evidences
  learning gain, engagement or usability**, and the chapter should say so in its own
  words rather than leaving it to the limitations list.

### Midpoint claims this section supersedes

None. This section records the discipline under which the rest of the chapter was
produced.

---

## Appendix — the four measurement artefacts, for the methodology section

Three of the programme's automated measurements were initially wrong and would each have
put a confident, incorrect figure in the thesis. A fourth produced no wrong figure at all
and belongs with them because it is the same class of defect seen from the other side.

| # | Artefact | Wrong figure it would have produced | Resolution |
|---|---|---|---|
| 1 | `eval_models` capped output at 1,400 tokens while the application allots 3,000 | `gemini-3.7-flash` scores 0/6 JSON compliance | Budget from `llm._max_tokens_for()`; the model then scored 6/6 |
| 2 | `eval_faithfulness` capped the judge at 1,400 tokens | RAG grounding *reduces* faithfulness by 0.021 | Judge budget raised to 3,000; usable judgements 7/24 → 17/24 |
| 3 | The planner's coverage measure depended on match quality | Content-derived scaling is uncorrelated with coverage | Fixed relevance radius; magnitude-matched control (FINDING-9) |
| 4 | `eval_faithfulness` persisted its metrics and discarded its evidence | **no wrong figure** — it withheld the material needed to check the right ones | Prose, evidence and per-claim verdicts now written every run (FINDING-10) |

Artefact 4 is the one worth a paragraph of its own. It survived two complete runs because
nothing about the output looked wrong: the command completed, the table printed, the
validation template was written — and the template could not be filled in, because the
chapters it asked to be scored no longer existed. Generation runs at temperature 0.7, so
re-running produces different chapters; the scored text was unrecoverable. On the first
run after the repair, reading the persisted chapters immediately found three defects no
metric had surfaced: a canned fallback chapter averaged into the results as though it were
grounded generation, a topic grounded entirely on a corrupted glossary and an exercise
page, and faithfulness's blindness to specificity.
