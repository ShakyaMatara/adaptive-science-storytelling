# Chapter 7 results summary

Quantitative evidence for the ASCALS evaluation programme. Every figure below traces
to a CSV written by an `eval_*` management command, or by one of the committed offline
scripts in `evaluation/analysis/` that post-process those CSVs, and is reproducible by
re-running it. No figure has been entered by hand.

One caveat on the word *reproducible*: generation runs at temperature 0.7, so re-running
a command that calls the model produces different text and different numbers. What is
reproducible is the procedure, not the sample. Section 6 quantifies how much the T4
result moves between two runs of identical configuration, and the prose behind every
scored chapter in the reported run is kept in `results/t4_chapters_latest.json` so the
figures can be checked against the material they were computed from.

---

## 1. Run metadata

| Item | Value |
|---|---|
| Date of runs | 2026-08-25; T4 re-run 2026-08-26 after the evidence-persistence repair |
| Generation model | `openai/gpt-5.4-mini` (the configured model, unchanged) |
| Judge model, T4 (reported run 3) | `google/gemini-3.7-flash` |
| Second judge, T4 | `deepseek/deepseek-v4-flash-0731` (six chapters, for agreement) |
| Judge model, T4 (run 1, retained) | `deepseek/deepseek-v4-flash-0731`, with gemini secondary |
| T4 runs | three; all reported. Runs 2 and 3 differ only in the sample drawn at temperature 0.7 |
| Provider | OpenRouter, `https://openrouter.ai/api/v1/` |
| `USE_MOCK_LLM` | `false` throughout; `backend/.env` was never modified |
| Index | Chroma collection `textbooks`, **1,122 chunks** |
| Embedding | Chroma default, computed locally |
| Total API spend | **≈ US$0.65** of a US$5.00 cap (see section 10) |

### Index composition

| Grade | Chunks | Distinct printed pages | Section labels | Chapter labels |
|---|---|---|---|---|
| 6 | 156 | 148 | 18 | 12 |
| 7 | 275 | 149 | 55 | 20 |
| 8 | 332 | 147 | 59 | 16 |
| 9 | 359 | 175 | 66 | 20 |
| **Total** | **1,122** | | | |

Of these, 36 chunks (3.2%) carry `source_type="ocr_vision"`: text recovered from
image-only pages in `G9P1.pdf` and verified by dual extraction. Every experiment
reports how much of its result rests on them.

### Tuning constants in force

| Constant | File | Value |
|---|---|---|
| `GATE_MAX_DISTANCE` | `retrieval.py` | 1.15 |
| `RELEVANCE_RADIUS` | `retrieval.py` | 1.15 (= `GATE_MAX_DISTANCE`) |
| `RELEVANCE_REL_MARGIN` | `retrieval.py` | 0.65 — **superseded, unused** (FINDING-9) |
| `RELEVANCE_MAX_DISTANCE` | `retrieval.py` | 1.45 (hard ceiling) |
| `SIMILARITY_THRESHOLD` | `views.py` | 0.70 |
| `PASSAGES_PER_CHAPTER` | `planning.py` | 3 |
| `RICHNESS_RANGES` | `planning.py` | thin 2–3 para / 0–1 q; moderate 3–4 / 1–2; rich 4–6 / 2–3 |
| richness bands | `planning.py` | thin ≤ 2 passages, moderate ≤ 6, rich > 6 |
| `START_DIFFICULTY` | `adaptation.py` | 3 |
| `MIN_DIFFICULTY` / `MAX_DIFFICULTY` | `adaptation.py` | 1 / 5 |
| `MIN_CHAPTERS` / `MAX_CHAPTERS_CAP` | `adaptation.py` | 1 / 6 |
| `POINTS_PER_DIFFICULTY` | `adaptation.py` | 10 |
| `CHAPTER_UP_THRESHOLD` / `CHAPTER_DOWN_THRESHOLD` | `adaptation.py` | 0.75 / 0.25 |
| `DEDUPE_TOLERANCE` | `build_index.py` | 1.0 (ingestion, FINDING-3) |

Exactly one constant changed during the programme: `RELEVANCE_RADIUS` replaced the
relative keep-window under FINDING-9, as an evaluation-driven design repair authorised
in advance and recorded in `results/corpus_defects.md`. No constant was altered to
improve a reported number.

### Probe sets

| Set | n | Provenance |
|---|---|---|
| `in_syllabus.json` | 40 | Chapter and sub-section headings taken verbatim from the published tables of contents |
| `in_syllabus_paraphrased.json` | 40 | The same forty topics rephrased as a learner would type them, authored blind to gate behaviour |
| `off_syllabus.json` | 45 × 4 grades | Negative controls in four families; none removed |
| `grade_boundary.json` | 20 | Topics requested at a grade whose book should not cover them |
| `anticheat.json` | 12 base × 6 classes | Assessment-integrity attacks plus a legitimate class |

Positives were selected from the contents pages **independently of system behaviour**.
Gate behaviour was not consulted during selection and no topic was added, removed or
reworded because of whether the gate accepts it. Selecting positives by acceptance
would guarantee near-perfect recall by construction and make T1 circular.

---

## 2. T1 — Curricular boundary enforcement

**What was measured.** Whether the syllabus gate accepts topics the learner's grade
textbook covers and refuses everything else, under two query conditions, plus
calibration of `GATE_MAX_DISTANCE` by an offline threshold sweep.

**Method.** Retrieval runs once per probe and the smallest embedding distance is
recorded. Because the layer-1 decision is exactly `best_distance <= threshold`, the
whole sweep is recomputed offline over the recorded distances at no additional cost.
The positive class is "accepted as in-syllabus".

### Result at the configured threshold — identical under both conditions

| Condition | TP | FN | FP | TN | Accuracy | Precision | Recall | Specificity | F1 |
|---|---|---|---|---|---|---|---|---|---|
| Contents-page phrasing | 39 | 1 | 14 | 166 | 0.9318 | 0.7358 | 0.9750 | 0.9222 | 0.8387 |
| Learner phrasing | 39 | 1 | 14 | 166 | 0.9318 | 0.7358 | 0.9750 | 0.9222 | 0.8387 |

### Decision margins — where the conditions differ

| Condition, in-syllabus probes | mean margin | sd | min | median | within 0.05 of threshold | wrong side |
|---|---|---|---|---|---|---|
| Contents-page phrasing | 0.350 | 0.142 | −0.015 | 0.360 | **0** | 1 |
| Learner phrasing | 0.303 | 0.156 | −0.007 | 0.324 | **2** | 1 |

### Sweep — the conditions diverge as the threshold tightens

| Threshold | Recall (contents-page) | Recall (learner) | Specificity | F1 (contents-page) |
|---|---|---|---|---|
| 0.85 | 0.700 | 0.500 | 0.9889 | 0.8000 |
| 0.90 | **0.775** | **0.525** | 0.9833 | 0.8378 |
| 1.00 | 0.900 | 0.875 | 0.9833 | **0.9114** |
| 1.10 | 0.975 | 0.925 | 0.9500 | 0.8864 |
| **1.15 (configured)** | 0.975 | 0.975 | 0.9222 | 0.8387 |
| 1.20 | 1.000 | 1.000 | 0.9000 | 0.8163 |

### Breakdown by probe family (contents-page condition)

| Family | n | Correct | Rate | Mean best distance | sd |
|---|---|---|---|---|---|
| advanced-science | 40 | 40 | 1.000 | 1.526 | 0.132 |
| nonsense | 20 | 20 | 1.000 | 1.567 | 0.147 |
| positive | 40 | 39 | 0.975 | 0.800 | 0.142 |
| adversarial | 40 | 37 | 0.925 | 1.416 | 0.177 |
| pseudo-scientific | 20 | 18 | 0.900 | 1.335 | 0.163 |
| other-subject | 40 | 35 | 0.875 | 1.468 | 0.153 |
| **grade-boundary** | 20 | 16 | **0.800** | 1.282 | 0.245 |

### Specificity: as measured and on a hypothetically clean corpus

| Measure | Value |
|---|---|
| Negatives | 180 |
| False positives as measured | 14 |
| ...caused by FINDING-4 corpus corruption | **4** |
| Specificity **as measured** | **0.9222** |
| Specificity, clean-corpus counterfactual | 0.9444 |

The counterfactual is reported alongside the measured figure and never in place of it.
The corpus that was evaluated is the corpus that was built.

### Provenance

Six of 53 accepted topics draw on recovered text, none wholly; mean recovered share
among those six is 19.5%, highest `Structure of the human heart` at 5 of 11 passages.

**Finding 1.** The syllabus gate achieves recall 0.975 and specificity 0.9222 under
both contents-page and learner phrasing, but its decision margin narrows measurably
under paraphrase and its recall advantage under contents-page phrasing appears only at
tighter thresholds, so the apparent robustness is a property of a loose threshold
rather than of the gate.

---

## 3. T2 — Assessment integrity

**What was measured.** Whether the deterministic similarity gate blocks attempts to
extract a live quiz answer through the grounded Q&A panel, without blocking legitimate
questions about the same concept.

**Method.** Twelve base quiz questions were perturbed into five attack classes plus a
legitimate class, and each was scored against the still-unanswered quiz question by the
same `difflib` ratio the application uses. The threshold sweep is recomputed offline.

### Result by perturbation class

| Class | n | Blocked | Block rate | Desired | Mean ratio | sd |
|---|---|---|---|---|---|---|
| verbatim | 12 | 12 | **1.000** | block | 1.000 | 0.000 |
| surface | 12 | 12 | **1.000** | block | 0.999 | 0.002 |
| lexical | 12 | 12 | **1.000** | block | 0.931 | 0.033 |
| reorder | 12 | 6 | 0.500 | block | 0.641 | 0.184 |
| paraphrase | 12 | 0 | 0.000 | block | **0.357** | 0.103 |
| legitimate | 12 | 0 | 0.000 | allow | **0.354** | 0.115 |

Overall: precision **1.000**, specificity **1.000**, recall 0.700, F1 0.8235.

### Separability of the paraphrase and legitimate classes

| Statistic | Value |
|---|---|
| Mean difference | **+0.0030** |
| Cohen's d | **+0.0275** |
| Paraphrase range | 0.176 – 0.512 |
| Legitimate range | 0.133 – 0.525 |
| Paraphrases inside the overlapping interval | **12 / 12** |
| Best accuracy achievable by any single threshold | **58.3%** (chance = 50.0%) |
| ...cost of achieving it | wrongly blocks **8 of 12** legitimate questions |

**Finding 2.** Paraphrased attacks and legitimate questions are statistically
indistinguishable by surface similarity, so no threshold can separate them and the
second, model-based layer is architecturally necessary rather than a convenience.

---

## 4. T3 — Content-Derived Instructional Scaling

**What was measured.** Whether the planner scales a session to how much of the
prescribed syllabus a topic occupies.

**Method.** The pages the syllabus devotes to each topic were derived from the
published tables of contents, transcribed from the printed books and therefore
independent of the PDFs' text layer, of the embeddings, of the retrieval thresholds and
of the planner. Spearman's rho was computed between that measure and the planner's
output, both as originally designed and after the FINDING-9 repair.

### Correlations

| Coverage measure | Plan measure | n | ρ as designed | ρ after repair |
|---|---|---|---|---|
| **Contents-page allocation** (external) | passage count | 39 | **−0.111** | **+0.411** |
| **Contents-page allocation** | chapter count | 39 | **−0.143** | **+0.270** |
| **Contents-page allocation** | distinct pages retrieved | 39 | +0.017 | +0.475 |
| distinct pages retrieved (internal proxy) | chapter count | 39 | +0.930 | +0.927 |
| page span (internal proxy) | chapter count | 39 | +0.638 | +0.728 |
| passage count (internal) | chapter count | 39 | +0.981 | — |

The contents-page allocation is authoritative and external. The distinct-pages and
page-span measures are internal proxies derived from the same retrieval call, and the
passage-count correlation is close to arithmetic given
`chapters = ceil(passage_count / 3)`; none of the three is independent evidence.

### Richness bands

| Band | As designed | After repair |
|---|---|---|
| thin (≤ 2 passages) | **0** | 4 |
| moderate (≤ 6) | 7 | 14 |
| rich (> 6) | 32 | 21 |

### Provenance

Three of 39 topics draw on recovered text; recovered passages are 8 of 289 counted
passages (2.8%). `Magnitude of force` is the most affected at 4 of 5 passages.

**Finding 3.** As designed, session length was uncorrelated with curricular emphasis
(ρ = −0.143) and was instead determined by lexical cohesion; after the FINDING-9 repair
the relationship is weakly to moderately positive (ρ = +0.270 for chapter count), which
does not support the claim that instructional volume is derived from textbook coverage.

Both figures are permanent. The repaired figure replaces the original nowhere.

---

## 5. T3b — Fixed-length ablation

**What was measured.** The consequence of abandoning content-derived planning for a
fixed three-chapter session on the eight topics with least available evidence.

**Method.** Each thin topic was generated twice, once under the planner's own chapter
count and once forced to three chapters, and the grounding density was compared. This
ran against the **repaired** keep rule, so "thin" means few passages inside the fixed
relevance radius rather than a narrow relative window.

| Condition | Mean passages per chapter | Mean words per grounding passage |
|---|---|---|
| Content-derived | **1.75** | **157.0** |
| Fixed three chapters | **0.92** | **268.1** |

All eight topics move in the same direction. Under fixed-length planning four topics
fall below one passage per chapter, meaning chapters with no grounding evidence at all,
and the prose demanded of each passage rises by up to 154% (`Types of Water based on
Salinity`, 116.5 → 296.0).

**Finding 4.** Fixed-length planning forces 71% more prose from each grounding passage
and leaves half the thin topics with at least one chapter carrying no evidence, which
is the padding pressure that T4 shows lowers factual groundedness.

---

## 6. T4 — Groundedness ablation

**What was measured.** Whether retrieval grounding reduces unsupported factual claims
in generated chapters.

**Method.** Twelve topics were each generated twice, once with retrieved textbook
excerpts supplied and once without, and both chapters were scored by an LLM judge
against the same textbook evidence. Six chapters were additionally scored by a second,
independent judge on identical evidence and prose so that inter-judge agreement could be
reported. The experiment was run **three times**: the first run lost 29% of its
judgements, the second exchanged the judges' roles, and the third repeated the second
after the harness was repaired to persist the evidence (FINDING-10). All three are
reported. The third is the reported result **because it is the only one whose scores can
be checked** — its chapter prose, its evidence blocks and its per-claim verdicts are on
disk.

### Reported result — run 3, `google/gemini-3.7-flash` as primary judge

| Condition | **n** | Mean faithfulness | **sd** | Mean claims | **Mean unsupported** | Mean contradicted |
|---|---|---|---|---|---|---|
| RAG on | **12** | **0.853** | **0.330** | 9.58 | **0.83** | 0.00 |
| RAG off | **12** | **0.566** | **0.241** | 7.33 | **3.08** | 0.00 |

**No judgement failed**: 24 of 24 usable, a balanced design with no exclusions. In all
24, the judge's reported `total_claims` matched the length of the claim list it
returned, so no score rests on an arithmetic inconsistency.

### One rag_on chapter was not a grounded generation (FINDING-11)

`Images formed by plane mirrors` scored **0.000** on 3 claims. Reading the persisted
prose shows why: it is the canned fallback chapter from `core/mock_content.py`, returned
by `core/llm.py:414` after both parse attempts on the model's output failed. It is a
generic essay about the scientific method, and the judge scored it against four passages
about mirrors. The detection is deterministic and needs no judgement — in `rag_on` the
application always attaches source refs, so `sources_attached == 0` means the fallback
fired. Applied retrospectively: **0 of 12 in run 1, 0 of 12 in run 2, 1 of 12 in run 3**,
a pooled **1 of 36 (2.8%)**. Runs 1 and 2 are uncontaminated.

| Basis | rag_on n | Mean | sd | Difference | Cohen's d | U | p |
|---|---|---|---|---|---|---|---|
| **as measured** | 12 | 0.853 | 0.330 | **+0.287** | 0.993 | 22.5 | **0.00365** |
| **excluding the fallback row** | 11 | **0.930** | 0.200 | **+0.364** | 1.644 | 11.0 | **0.00054** |

Both are reported and neither replaces the other. The first answers *what does a learner
receive end to end*; the second answers *does retrieval constrain generation when
generation succeeds*. Quoting either without saying which question it answers would
misstate the result.

### Significance

| Statistic | Faithfulness | Unsupported claims |
|---|---|---|
| Difference in means | **+0.287** | −2.25 per chapter |
| Cohen's d | **+0.993** | — |
| Mann–Whitney U | **22.5** | 18.0 |
| z | 2.907 | 3.195 |
| **p (two-tailed)** | **0.00365** | 0.0014 |

Mann–Whitney U is non-parametric and assumes no distributional form, which suits
bounded scores in small samples. At n = 12 per group the normal approximation used to
obtain p is appropriate; tie and continuity corrections are applied.

**The difference is unlikely to be sampling noise**, and the reduction in unsupported
claims — from 3.08 to 0.83 per chapter — is the safety argument for the RAG layer rather
than an accuracy improvement. Every chapter in both conditions had zero *contradicted*
claims: ungrounded generation invents material the book does not cover, it does not
assert the opposite of what the book says.

### The effect size moves on every run

| | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Primary judge | `deepseek-v4-flash` | `gemini-3.7-flash` | `gemini-3.7-flash` |
| Usable judgements | 17 / 24 (71%) | **24 / 24** | **24 / 24** |
| Design | unbalanced, 10 vs 7 | balanced, 12 vs 12 | balanced, 12 vs 12 |
| RAG on mean | 0.990 | 0.953 | 0.853 (0.930 excl. fallback) |
| RAG off mean | 0.454 | 0.552 | 0.566 |
| **Measured effect** | **+0.536** | **+0.401** | **+0.287** (+0.364 excl. fallback) |
| p (two-tailed) | — | 0.00022 | 0.00365 |

Runs 2 and 3 are the same experiment: same twelve topics, same prompts, same index, same
primary judge, same judge budget. **The only difference between them is the sample drawn
at temperature 0.7.** The measured effect moved by 0.114 on that alone.

Paired chapter by chapter across runs 2 and 3 (n = 24):

| | |
|---|---|
| Mean signed change | −0.043 (sd 0.241) |
| Mean absolute change | **0.119** |
| Unchanged | 10 / 24 |
| Largest movement | `Images formed by plane mirrors` rag_on, 1.000 → 0.000 (the fallback) |
| Second largest | `Weather` rag_on, 0.700 → 0.333 |

**This is generation-to-generation variance, not a correction.** Run 2's figures are not
withdrawn and are not superseded; run 3 did not find an error in them. Across three runs
the effect is +0.287 to +0.536, large and significant in every one, with the magnitude
varying by more than the difference between a "large" and a "very large" effect. The
honest statement is that **retrieval grounding produces a large, reliably significant
increase in faithfulness whose magnitude cannot be pinned down to better than roughly
±0.12 from twelve chapters per condition.** Reporting a single run's figure to three
decimal places, as a single-run study would, would convey precision that three runs show
does not exist.

### Inter-judge agreement

Six chapters were scored by both models on identical evidence and prose, in all runs.

| | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Spearman ρ | +0.718 | +0.727 | **+0.898** |
| Mean absolute difference | 0.152 | 0.186 | **0.032** |
| Exact agreement | 3 / 6 | 3 / 6 | **4 / 6** |
| Within 0.10 | 4 / 6 | 3 / 6 | **5 / 6** |

`Weather` rag_on diverged severely in runs 1 and 2 — 1.000 against 0.286, then 0.700
against 0.000. In run 3 the two judges scored the same chapter **0.333 and 0.400**, a
difference of 0.067. The earlier framing that `Weather` is a persistently contentious
*topic* does not survive: the divergence was a property of two particular generations,
not of the topic, and it disappears when the topic is generated again. What persists is
that the judges can disagree by 0.7 on a chapter both have read in full.

### Faithfulness is not accuracy — the `Weather` chapter

Now that the prose is kept, the low scores can be read rather than inferred. `Weather`
rag_on scored 0.333: three of nine claims supported. The unsupported ones were

> *a thermometer measures temperature* · *a rain gauge measures rainfall* · *humidity is
> the amount of water vapour in the air* · *weather is not the same as climate*

Every one of these is **true**. None of them is in the two passages retrieved for
`Weather` at Grade 6, which are a table of Colombo rainfall and temperature figures. The
second judge marked the same claims unsupported.

**A low faithfulness score does not mean the chapter is wrong; it means the chapter went
beyond its evidence.** This is what the metric is defined to measure and it is the right
thing to measure for a grounding claim, but Chapter 7 must not paraphrase it as
"accuracy" anywhere.

### Faithfulness against the size of the evidence base

The judge sees at most four passages, so a topic with `total_relevant = 15` and one with
`total_relevant = 4` are scored against evidence bases of similar size; only the two
`thin` topics, which have fewer than four passages in total, differ materially.

| Richness | Condition | n | Mean `total_relevant` | Mean evidence chars | Mean faithfulness | sd |
|---|---|---|---|---|---|---|
| thin | RAG on | 2 | 2.0 | 2,440 | **0.667** | 0.471 |
| moderate | RAG on | 4 | 4.0 | 5,141 | **0.975** | 0.050 |
| rich | RAG on | 6 | 14.0 | 5,489 | **0.833** | 0.408 |
| thin | RAG off | 2 | 2.0 | 2,440 | 0.214 | 0.303 |
| moderate | RAG off | 4 | 4.0 | 5,141 | 0.647 | 0.206 |
| rich | RAG off | 6 | 14.0 | 5,489 | 0.629 | 0.158 |

Within RAG on: ρ(`total_relevant`, faithfulness) = **+0.080**, ρ(evidence characters,
faithfulness) = **+0.514**.

**A hypothesis was tested here and falsified.** It was proposed, before the run, that
high faithfulness would concentrate on *thin* topics — that a score of 1.000 against two
short overlapping passages is cheap because there is little to be unfaithful to. The data
say the opposite. The correlation with evidence size is **positive**, the `thin` band
scores **lowest** in both conditions, and the nine RAG-on chapters scoring exactly 1.000
sit on a mean evidence base of 5,256 characters against 3,690 for the three that scored
below it. The mechanism is visible in the `Weather` chapter above: a thin topic must fill
the same three-to-four paragraph budget from a smaller evidence base, so the model goes
beyond its evidence to do it, and what it adds scores as unsupported even when true.

The underlying methodological point stands and is retained: **a ratio over a small
denominator is not the same measurement as a ratio over a large one**, and faithfulness
should never be quoted without the size of the evidence base it was computed against.
`t4_faithfulness_by_evidence_base_latest.csv` reports the two side by side per topic. But
the specific prediction that thin topics inflate the headline figure was wrong, and it
was wrong in the direction that would have flattered the caveat rather than the result.

### Provenance

| Grounding | n | Mean faithfulness | Mean unsupported |
|---|---|---|---|
| text layer only | 20 | 0.693 | 1.95 |
| includes recovered text | **4** | 0.789 | 2.00 |

At n = 4 the recovered-text row still supports no inference. Where grounding includes
recovered text the judge scores against a model transcription of a page image rather
than the book's text layer, so that score measures consistency with the transcription.

### Human validation

The programme's own instrument requires it and it has not yet been performed. Run 3
writes what is needed for it, which no previous run did:

- `t4_judge_validation_BLIND_latest.csv` — twelve chapters with their evidence inline and
  **no judge output of any kind**, to be scored without anchoring;
- `t4_chapter_dossier_BLIND_latest.md` — the same twelve laid out to be read;
- `t4_judge_validation_TEMPLATE_latest.csv` — the merge target, human columns first,
  the judge's per-claim verdicts after;
- `t4_chapters_latest.json` — the full audit record for all 24.

**Finding 5.** Retrieval grounding raises measured faithfulness from 0.566 (sd 0.241,
n = 12) to 0.853 (sd 0.330, n = 12), a difference of 0.287 that is statistically
significant (Mann–Whitney U = 22.5, p = 0.0037) and reduces unsupported claims from 3.08
to 0.83 per chapter, which is a safety property rather than an accuracy improvement.
Excluding the one chapter that came from the fallback path rather than from grounded
generation, the figures are 0.930 and +0.364 (p = 0.00054).

**Precision caveat.** With twelve chapters per condition the *existence* and *direction*
of the effect are firmly established, and it is significant in all three runs. Its
*magnitude* carries wide uncertainty from two independent sources: the two judges differ
by up to 0.135 on identical generations, and two runs of identical configuration differ
by 0.114 on fresh generations at temperature 0.7. The figure remains an automated
estimate until the blind validation set is scored.

---

## 7. T5 — Difficulty adaptation validity

**What was measured.** Whether the 1–5 difficulty setting produces linguistically
distinguishable text.

**Method.** Two topics were generated at each of five difficulty levels, four
repetitions each, and each chapter's prose was scored for readability. Monotonicity was
tested with Spearman's rho and adjacent levels were tested for separation with Cohen's d.

| Difficulty | n | Mean FKGL | sd | Mean FRE | Words/sentence | Mean words |
|---|---|---|---|---|---|---|
| 1 | 8 | 5.73 | 0.69 | 72.5 | 10.4 | 235 |
| 2 | 8 | 7.35 | 1.31 | 65.6 | 13.1 | 253 |
| 3 | 8 | 8.63 | 1.82 | 58.6 | 14.3 | 260 |
| 4 | 8 | 9.56 | 2.09 | 54.3 | 15.6 | 288 |
| 5 | 8 | 11.28 | 2.92 | 49.8 | 20.0 | 358 |

| Measure | ρ against configured difficulty | Expected |
|---|---|---|
| Flesch–Kincaid Grade Level | **+0.770** | positive ✔ |
| Flesch Reading Ease | **−0.710** | negative ✔ |
| Words per sentence | **+0.695** | positive ✔ |
| Type–token ratio | +0.090 | positive ✘ |

### Adjacent-level separation

| Pair | Gap (FKGL) | Pooled sd | Cohen's d | Overlapping samples | Verdict |
|---|---|---|---|---|---|
| 1 → 2 | 1.62 | 1.05 | **1.55** | 7/16 | separated |
| 2 → 3 | 1.28 | 1.58 | 0.81 | 12/16 | partial |
| 3 → 4 | 0.93 | 1.96 | **0.48** | 12/16 | **collapsed** |
| 4 → 5 | 1.71 | 2.54 | **0.67** | 12/16 | **collapsed** |
| 1 vs 5 | 5.55 | — | **2.61** | — | separated |

Per-level FKGL ranges overlap heavily: L3 spans 6.6–11.5 and L5 spans 7.1–16.1, so a
level-5 chapter can be easier than a level-3 chapter. Variance grows four-fold across
the ladder.

**Sample size.** Each level rests on **n = 8** generations (2 topics x 4 repetitions).
The Cohen's d values above are computed on 8 against 8 and are therefore themselves
imprecise: with samples this small, d is a point estimate whose confidence interval is
wide, and the boundary between "partial" and "collapsed" at d = 0.8 should not be read
as a sharp threshold. What the data support is the ordering and the direction, not the
exact effect size of any single adjacent pair.

**Finding 6.** The difficulty ladder is a real gradient whose extremes are strongly
separated (d = 2.61) and whose surface measures move monotonically, but adjacent levels
above level 2 do not separate at n = 8 per level, so it reliably resolves two or three
bands rather than five.

---

## 8. T6 — Model selection benchmark

**What was measured.** First-attempt structured-output reliability, latency,
readability and cost across five candidate models, to evidence the model choice.

**Method.** Six in-syllabus topics were generated by each model through the
application's own prompt and token budget, with no retry, so that first-attempt schema
compliance is measured as the deployed system would experience it.

| Model | JSON ok | Rate | Median latency | Mean FKGL | In band | US$/chapter |
|---|---|---|---|---|---|---|
| `google/gemini-3.7-flash` | 6/6 | **1.000** | 14.26 s | 11.57 | **no** | 0.00423 |
| **`openai/gpt-5.4-mini`** (configured) | 5/6 | 0.833 | **5.76 s** | **8.77** | **yes** | 0.00417 |
| `deepseek/deepseek-v4-flash-0731` | 4/6 | 0.667 | 46.26 s | 6.67 | yes | **0.00036** |
| `openai/gpt-5.6-luna` | 3/6 | 0.500 | 8.34 s | 10.64 | no | 0.00121 |
| `qwen/qwen3.8-27b` | 1/6 | 0.167 | 74.76 s | 6.46 | yes | 0.00800 |

`qwen/qwen3.8-27b` exhausted the application's own 3,000-token budget on five of six
prompts. That is a deployment property rather than a measurement artefact: the model is
too verbose to complete a chapter within the budget the system allots.

**Finding 7.** The configured model is the only candidate that simultaneously achieves
at least 80% first-attempt schema compliance, readability inside the target band and the
lowest latency in the field, which justifies the selection on evidence rather than
assertion; `deepseek-v4-flash` is a credible alternative at one eleventh of the cost per
chapter, constrained by an eight-fold latency penalty.

---

## 9. Failures and anomalies

This section is required and is not a formality. Three of the programme's automated
measurements were initially wrong, and each would have produced a confident, incorrect
figure in the thesis. A fourth produced no wrong figure and is listed with them because
it is the same class of defect seen from the other side: it withheld the evidence needed
to check the figures it did produce, which is why it survived two complete runs
unnoticed.

### 9.1 Measurement artefacts caught before reporting

| # | Artefact | Wrong figure it would have produced | Cause | Resolution |
|---|---|---|---|---|
| 1 | `eval_models` capped output at 1,400 tokens while the application allots 3,000 | `gemini-3.7-flash` scores 0/6 JSON compliance | Benchmark measured its own cap; the model returned exactly 1,396 completion tokens on all six prompts and every failure was mid-object truncation | Budget derived from `llm._max_tokens_for()`; the same model then scored 6/6 |
| 2 | `eval_faithfulness` capped the judge at 1,400 tokens | RAG grounding *reduces* faithfulness by 0.021 | The judge spent the whole budget on hidden reasoning and returned an empty response; 17 of 24 judgements were lost | Judge budget raised to 3,000; usable judgements rose from 7/24 to 17/24 and the true effect is **+0.536** |
| 3 | The planner's coverage measure depended on match quality | Content-derived scaling is uncorrelated with coverage, full stop | `RELEVANCE_REL_MARGIN` scaled the keep-window to the best hit, so topics matching worse were credited with more content | Fixed relevance radius (FINDING-9); a magnitude-matched control confirmed truncation explains none of the improvement |
| 4 | `eval_faithfulness` persisted its metrics and discarded its evidence | *no wrong figure at all* — it withheld the material needed to check the right ones | The generated prose, the evidence block and the judge's per-claim verdicts existed only in memory; generation runs at temperature 0.7, so the scored text was unrecoverable and the human validation the command itself asks for was impossible to start | Every run now writes the prose, the evidence and both judges' verdict lists, plus a blind scoring copy (FINDING-10) |

### 9.2 Corpus defects

Nine defects were found by systematic inspection before any experiment ran; six were
repaired with quantified before/after measurement and three remain documented
limitations. Two further findings (10 and 11) were found by *using* the harness rather
than by inspecting the corpus, and are recorded in the same file for continuity of the
audit trail. Full detail in `results/corpus_defects.md`.

| # | Defect | Disposition | Headline measurement |
|---|---|---|---|
| 1 | Page metadata recorded the last heading's page | Repaired | Correct attribution 25.5% → 97.5% |
| 2 | Chapter labels absent or wrong in three of four grades | Repaired | 0/18/0/0 → 11/19/15/19 genuine chapters |
| 3 | Doubled characters from overprinted bold | Repaired | 8.8% → 0.6% of chunks |
| 4 | Mojibake from legacy Sinhala/Tamil fonts | **Documented** | 8.6% of chunks; causes 4 of 14 T1 false positives |
| 5 | Facing-page text captured into a page's extraction | **Documented** | 0.76% inflation of `total_relevant` |
| 6 | Citations named the PDF page index, not the printed page | Repaired | 82.7% of chunks span more than one page |
| 7 | Symbol-font ticks lost to Private Use Area codepoints | Repaired | 0.8% → 0.0% of chunks |
| 8 | `G9P1.pdf` distributed with image-only pages | Repaired | 17.4% of that book recovered by dual extraction |
| 9 | Planner measured lexical cohesion, not coverage | Repaired (partial) | ρ −0.143 → +0.270 |
| 10 | T4 persisted metrics and discarded the evidence behind them | Repaired | Blocked human validation for two full runs; prose, evidence and per-claim verdicts now written every run |
| 11 | The canned fallback chapter was scored as a grounded generation | **Documented**, detector added | 1 of 36 rag_on generations (2.8%); moved the run-3 effect from +0.364 to +0.287 |

### 9.3 Residual failures in the reported results

- **T4 judge failures, first run: 7 of 24** (29%), all `deepseek-v4-flash` returning
  invalid JSON, leaving an unbalanced 10-against-7 design. Re-running with the judges
  exchanged gave **24 of 24** usable and a balanced 12-against-12 design. Both runs are
  reported; the first is retained as evidence that judge choice determines the usable
  sample.
- **T4 effect size is judge-dependent.** The same generations yield +0.536 under one
  judge and +0.401 under the other. The effect is large and significant either way, but
  its magnitude is partly a property of the scorer.
- **T4 effect size is also generation-dependent.** Runs 2 and 3 are identical in every
  configurable respect and differ only in the sample drawn at temperature 0.7. They
  report +0.401 and +0.287. Paired chapter by chapter the mean absolute movement is
  0.119 and 10 of 24 chapters were unchanged. Across three runs the effect spans +0.287
  to +0.536, significant in all three.
- **T4 run 3 contains one chapter that was never a grounded generation.**
  `generate_chapter` fell through both parse attempts and returned the canned fallback,
  which the judge scored 0.000 against mirror passages. Detected deterministically by
  `sources_attached == 0` in a rag_on row; 1 of 36 pooled across all three runs. Both
  the as-measured and the fallback-excluded figures are reported (FINDING-11).
- **T4 inter-judge divergence.** The judges disagreed by 0.714 and 0.700 on the same
  chapter (`Weather` rag_on) in the two runs respectively. Persistently contentious, and
  the first candidate for human adjudication.
- **T6: 11 of 30 first-attempt generations failed.** Two distinct shapes: mid-object
  truncation where the model ran long, and genuinely malformed output (`qwen`, an
  unterminated string and an empty response). The application's single retry recovers
  the first kind more reliably than the second.
- **T5: 3 of 5 difficulty levels are not separable.**
- **T1: one positive refused** — `Neutralisation` at Grade 8, best distance 1.1649
  against a 1.15 threshold, over by 1.4%. It is accepted under learner phrasing at
  0.9581.
- **T3: FINDING-9's repair is partial.** The dependence on match quality was inverted
  rather than eliminated (ρ +0.545 → −0.634), which is intrinsic to measuring density
  within a fixed radius.
- **Cost tracking is incomplete.** `eval_difficulty` and `eval_planner --ablate` call
  `llm.generate_chapter`, which returns no usage data, so 56 of 140 paid calls are not
  instrumented and their cost is derived rather than measured.

### 9.4 Anomalies worth reporting

- **A learner's phrasing outperformed the textbook's own heading.** `Neutralisation`
  was refused at 1.1649 while *"what happens when an acid meets a base"* was accepted at
  0.9581. A one-word heading offers little lexical surface to match, whereas a
  descriptive question resembles the prose the chapter is written in. Tested for
  generality and **not found**: ρ between heading length and paraphrase shift is +0.085,
  a null result. It is a striking single case, not a pattern.
- **A corpus defect causes gate failures.** All four `Sinhala grammar and sentence
  construction` false positives disappear when FINDING-4 chunks are excluded (best
  distance 1.11–1.13 → 1.21–1.41). The other six false positives survive exclusion and
  are genuine semantic near-misses.
- **Grade-boundary leakage is the weakest family** at 16/20, and all four leaks are into
  Grade 6.

---

## 10. API spend

| Experiment | Calls | Instrumented | Cost |
|---|---|---|---|
| T6 model benchmark (first, voided run) | 30 | yes | US$0.0831 |
| T6 model benchmark (reported run) | 30 | yes | US$0.1078 |
| T4 faithfulness (first, voided run) | 55 | yes | US$0.0273 |
| T4 faithfulness (deepseek primary, retained) | 54 | yes | US$0.0249 |
| T4 faithfulness (gemini primary, run 2) | 56 | yes | US$0.0827 |
| T4 faithfulness (gemini primary, run 3, reported) | 57 | yes | US$0.0824 |
| T5 difficulty | 40 | no | ≈ US$0.18 (derived) |
| T3b ablation | 16 | no | ≈ US$0.07 (derived) |
| Model availability probe | 1 | no | < US$0.001 |
| **Total** | **339** | | **≈ US$0.65** |

Against a US$5.00 cap from a US$10.00 balance. Instrumented spend is US$0.4082; the
remainder is derived from the token profile measured in T6 for the same model. The
provider account reports lifetime usage only, and no pre-run baseline was taken, so the
account figure cannot corroborate this total. Prices are those in force on 2026-08-25
and are recorded in `harness.PRICES_PER_MTOK`; costs are indicative.

---

## 11. Threshold recommendations

Recommendations only. **No constant was changed in response to any sweep.**

### Why one change was applied and another was not

Exactly one constant changed during this programme, and the contrast with the change
that was *not* made is the clearest evidence that the repair was principled rather
than fitted.

| | FINDING-9 (**applied**) | `GATE_MAX_DISTANCE` = 1.10 (**not applied**) |
|---|---|---|
| What it changes | **What is measured** — the keep-window stopped depending on how well the query matched | **A threshold value** — the same quantity, evaluated at a different cut-point |
| Why it was raised | A measure of how much content exists correlated **+0.545** with the best hit's distance: a sign error visible without reference to any target metric | 1.10 scores better than 1.15 on the sweep |
| Validation | A magnitude-matched control reproduced the repair's passage count and **none** of its improvement (rho -0.133 against -0.134), excluding the rival explanation | None available; the evidence *is* the sweep |
| Value chosen | 1.15, which is **not** the correlation-maximising value (0.95 and 1.20 both score higher) | 1.10 would be chosen precisely *because* it scores higher |

Changing a threshold after seeing which value scores better is what Rule 2 exists to
prevent, and it applies to the 1.10 recommendation however sound the recommendation is.
FINDING-9 was admitted because the defect was identifiable from the mechanism alone,
because a control experiment excluded the alternative explanation, and because the
value adopted was demonstrably worse on the target metric than alternatives already
measured. Absent all three conditions, a change is a fit rather than a repair.

The 1.10 recommendation is therefore recorded below for future work and left
unapplied.

| Constant | Configured | Sweep optimum | Recommendation |
|---|---|---|---|
| `GATE_MAX_DISTANCE` | **1.15** | 1.00 (F1 0.9114) | Consider **1.10**: it dominates 1.15 on the contents-page set with equal recall (0.975), better specificity (0.950 vs 0.9222) and better F1 (0.8864 vs 0.8387). 1.00 maximises F1 but costs recall (0.900) and drops learner-phrasing recall to 0.875. |
| `SIMILARITY_THRESHOLD` | **0.70** | 0.30 (F1 0.9032) | **Retain 0.70.** The F1 optimum blocks 66.7% of legitimate questions. The knee is 0.55, where attack catch is 0.733 at a zero false-block rate; 0.70 sits safely inside the zero-false-block plateau (0.55–0.75). Given that a leaked answer invalidates an assessment while a blocked question merely frustrates, the conservative operating point is correct. |
| `RELEVANCE_RADIUS` | **1.15** | 1.20 (ρ +0.466) | **Retain 1.15.** 0.95 and 1.20 both correlate better with curricular coverage, but 1.15 follows from the existing design — one relevance radius for both membership and volume — and the correlation is stable across 0.85–1.30, so the choice is not delicate. Adopting the peak would be fitting rather than repairing. |
| `PASSAGES_PER_CHAPTER` | **3** | not swept | No evidence to change it. T3's weakness lies in the coverage measure, not in this divisor. |
| `RICHNESS_RANGES` and bands | thin ≤2 / moderate ≤6 / rich >6 | not swept | **Retain.** The thin band was inert before FINDING-9 and is now populated (4/14/21), so the classification works without alteration. |
| `CHAPTER_UP_THRESHOLD` / `DOWN` | 0.75 / 0.25 | not swept | Untested by this programme; no recommendation. |

---

## 12. Limitations

1. **No classroom deployment and no human participants.** Every result is a property of
   the system measured in isolation. Nothing here evidences learning gain, engagement or
   usability.
2. **Single annotator.** Probe curation, paraphrase authoring and defect classification
   were performed by one party. The blind-authoring protocol for the paraphrased set
   mitigates but does not remove this.
3. **Single corpus, English medium only.** Seven textbooks for one national curriculum.
   The Sinhala and Tamil editions are not evaluated, and the mojibake defect means the
   corpus's own non-English content is unusable.
4. **Readability formulae measure surface linguistic complexity, not conceptual
   difficulty.** This bears directly on T5: the type–token ratio result (ρ = +0.090)
   shows the model lengthens sentences without broadening vocabulary, and FKGL cannot
   distinguish a hard idea in simple words from an easy idea in complex ones.
5. **The LLM judge requires human validation before its scores carry weight.** Two
   judges agreed at ρ = +0.718, +0.727 and +0.898 across the three runs, with a severe
   divergence in the first two. The blind scoring set at
   `t4_judge_validation_BLIND_latest.csv` is unfilled; until it is, T4's faithfulness
   figure is an automated estimate, not a validated measurement. It could not have been
   filled before run 3, because no earlier run kept the chapters it asked to be scored
   (FINDING-10).
6. **Faithfulness is not accuracy.** It measures whether a claim is traceable to the
   supplied excerpts. The `Weather` chapter lost six of nine claims on statements that
   are all true — that a thermometer measures temperature, that humidity is water vapour
   in the air — and are simply absent from the two passages retrieved for that topic. The
   metric is the right one for a grounding claim and the wrong one for a correctness
   claim.
7. **Small samples, and generation is stochastic.** T4 rests on 12 chapters per
   condition, T5 on 8 generations per level, T6 on 6 prompts per model, and inter-judge
   agreement on 6 chapters. Generation runs at temperature 0.7, so the sample-size
   limitation compounds with a sampling one: two runs of the identical T4 configuration
   differ by 0.114 in the measured effect. Effect
   sizes and standard deviations are reported throughout so the reader can judge what
   the samples support. Where an effect is large enough to test, a non-parametric test
   is given; where n is too small to test meaningfully, none is computed.
8. **3.2% of the index is recovered from page images** rather than read from a text
   layer. Each experiment reports its exposure; T4's recovered-text row has n = 4 and
   supports no conclusion.
9. **The generation fallback is silent.** When the model's output fails to parse twice,
   the application substitutes a canned chapter with no textbook sources and presents it
   under the requested topic. It fired on 1 of 36 grounded generations (2.8%) and is
   detectable only because zero sources are attached. Neither a learner nor a metric can
   tell it from a successful chapter without that check (FINDING-11).
10. **Cost figures are partly derived.** 56 of 140 paid calls are not instrumented.
11. **Provider prices and model availability change.** All costs are indicative of
    2026-08-25.
12. **T3's repair is partial and its result is weak.** ρ = +0.270 for chapter count
    does not establish that instructional volume is derived from curricular emphasis.

---

## 13. File manifest

### Result data

| File | Supports |
|---|---|
| `t1_gate_verbatim_latest.csv` | 7.4 — per-probe gate decisions, contents-page condition |
| `t1_gate_paraphrased_latest.csv` | 7.4 — per-probe gate decisions, learner condition |
| `t1_gate_sweep_verbatim_latest.csv` | 7.4.x — threshold calibration |
| `t1_gate_sweep_paraphrased_latest.csv` | 7.4.x — threshold calibration under paraphrase |
| `t1_gate_by_family_verbatim_latest.csv` | 7.4.x — failure analysis by probe family |
| `t1_gate_margins_*_latest.csv` | 7.4.x — decision-margin distributions |
| `t1_gate_counterfactual_*_latest.csv` | 7.4.x — clean-corpus specificity |
| `t1_verbatim_vs_paraphrased.csv` | 7.4.x — paired per-topic robustness |
| `t1_false_positive_analysis.md` | 7.4.x — defect-to-failure trace |
| `t2_anticheat_latest.csv` | 7.5 — per-probe integrity gate results |
| `t2_anticheat_by_class_latest.csv` | 7.5 — catch rate by attack class |
| `t2_anticheat_sweep_latest.csv` | 7.5.x — operating-point selection |
| `t2_paraphrase_vs_legitimate_latest.csv` | 7.5.x — separability analysis |
| `t3_planner_latest.csv` | 7.6 — per-topic planning outcomes |
| `t3_diagnostics.csv` | 7.6.x — mechanism diagnosis |
| `t3_ablation_latest.csv` | 7.6.x — fixed-length comparison |
| `ground_truth.csv` | 7.6 — contents-page coverage measure |
| `t4_faithfulness_latest.csv` | 7.7 — per-chapter groundedness |
| `t4_faithfulness_summary_latest.csv` | 7.7 — ablation summary |
| `t4_faithfulness_by_provenance_latest.csv` | 7.7.x — provenance split |
| `t4_interjudge_agreement_latest.csv` | 7.7.x — judge validation |
| `t4_judge_validation_BLIND_latest.csv` | 7.7.x — **human scoring surface, unfilled** — chapters and evidence inline, no judge output |
| `t4_chapter_dossier_BLIND_latest.md` | 7.7.x — the same twelve chapters laid out to be read and scored |
| `t4_judge_validation_TEMPLATE_latest.csv` | 7.7.x — merge target: human columns first, judge's per-claim verdicts after |
| `t4_chapters_latest.json` | 7.7 — **full audit record**: chapter prose, evidence blocks, both judges' per-claim verdicts |
| `t4_faithfulness_by_evidence_base_latest.csv` | 7.7.x — faithfulness against `total_relevant` and evidence size, per topic |
| `t4_faithfulness_by_richness_latest.csv` | 7.7.x — faithfulness by richness band |
| `t4_fallback_sensitivity_latest.csv` | 7.7.x — effect with and without the fallback chapter |
| `t4_generation_variance_latest.csv` | 7.7.x — run 2 against run 3, paired per chapter |
| `t4_significance_latest.csv` | 7.7 — run-3 significance test |
| `t4_faithfulness_gemini_run1_latest.csv` | 7.7 — run 2, retained unchanged |
| `t4_faithfulness_deepseek_primary_latest.csv` | 7.7 — run 1, retained unchanged |
| `t4_interjudge_agreement_gemini_run1_latest.csv` | 7.7.x — run-2 judge agreement |
| `t5_difficulty_latest.csv` | 7.8 — per-generation readability |
| `t5_adjacent_separation_latest.csv` | 7.8.x — level separation |
| `t6_models_latest.csv` | 7.9, 6.2 — per-call model benchmark |
| `t6_models_summary_latest.csv` | 7.9, 6.2 — model comparison table |

### Corpus and methodology records

| File | Supports |
|---|---|
| `corpus_defects.md` | 7.3 — nine defects, detection, repair, measurement |
| `midpoint_corrections.md` | Deviations chapter — eight falsified or revised claims |
| `g9p1_coverage_gap.md` | 7.3.x — image-only pages and their recovery |
| `ocr_dual_extraction.csv` | 7.3.x — per-page A/B extraction agreement |
| `text_quality_impact.md` | 7.3.x — corruption incidence and retrieval impact |
| `index_quality_before.csv` / `index_quality_after.csv` | 7.3 — ingestion repair |
| `toc_page_validation.csv` | 7.3.x — page-mapping validation, 272 entries |
| `chunk_page_spans.csv` | 7.3.x — multi-page chunk evidence |
| `duplicate_impact.csv` | 7.3.x — duplication effect on coverage |
| `textbook_toc.md` | 7.3, 7.6 — transcribed contents pages |
| `g9p1_recovered_pages.json` | 7.3.x — recovered page text |
| `logs/` | Appendix — console output of every command run |

### Figures

| Figure | Illustrates | Section |
|---|---|---|
| `fig_t1_sweep.png` | Gate recall, specificity and F1 across thresholds, both phrasings | 7.4 |
| `fig_t1_distances.png` | Best-distance distribution by probe family | 7.4 |
| `fig_t2_sweep.png` | Attack catch rate against legitimate false-block rate | 7.5 |
| `fig_t2_by_class.png` | Block rate by perturbation class | 7.5 |
| `fig_t3_scatter.png` | Coverage against planned session length | 7.6 |
| `fig_t3_richness.png` | Chapter and question budgets by richness band | 7.6 |
| `fig_t4_ablation.png` | Faithfulness with and without retrieval grounding | 7.7 |
| `fig_t5_difficulty.png` | Readability against configured difficulty | 7.8 |
| `fig_t6_models.png` | Schema compliance, latency and cost by model | 7.9, 6.2 |

Every figure requires a caption stating what it illustrates.

### Functional testing

`python manage.py test core` — **27 tests, all passing**, unchanged from the baseline
recorded before any modification. Supports section 7.10.
