# Corpus and ingestion defects: detection, repair and measurement

A running record of defects found in the ASCALS textbook corpus and its ingestion
pipeline during the Chapter 7 evaluation programme. All were found by systematic
inspection of the built index before any experiment was run, which is why none of
them contaminates a reported result.

Each entry records how the defect was detected, whether it was repaired or
documented as a limitation, and the before/after measurement.

| # | Defect | Detected by | Disposition |
|---|---|---|---|
| 1 | Page metadata recorded the last heading's page, not the text's own page | Index metadata audit | **Repaired** |
| 2 | Numbered table rows accepted as chapter headings | Chapter-label distribution audit | **Repaired** |
| 3 | Doubled characters from overprinted bold text | Page-attribution verification | Documented |
| 4 | Mojibake from legacy Sinhala/Tamil font encodings | Manual spot-check | Documented |
| 5 | Duplicated two-page spreads indexed twice | Supervisor spot-check challenge | Documented, impact measured |
| 6 | Single-page citation for chunks spanning up to five pages | Span audit | **Repaired** |

---

## FINDING-1 - page attribution (REPAIRED)

**Detection.** The metadata audit showed Grade 6 holding 160 chunks across only 20
distinct page values, one of which carried 45 chunks - roughly 11,000 words, which
no printed page can hold.

**Cause.** `build_chunks_for_file` buffered body text across page boundaries until
the next heading flushed it, but recorded only `buf_page`, which was set when a
heading was seen and never reset. Every chunk between two headings inherited the
earlier heading's page number.

**Repair.** The line buffer now carries the page each line came from,
`split_into_word_chunks` returns each chunk's starting word index, and each chunk is
stamped with the page its own first word occupies.

**Measurement.** Proportion of chunks whose first eight words are actually present
on the page the metadata claims:

| | Before | After |
|---|---|---|
| Correct attribution | 282/1105 (**25.5%**) | 1074/1101 (**97.5%**) |

Distinct page values per grade rose by 130-640%; the maximum number of chunks
sharing one page value fell from 45 to 6. The residual 2.5% are chunks straddling a
page boundary, where an eight-word contiguous probe cannot match by construction; a
three-word probe scores 98.9%.

**Side effect.** `planning.plan_session` orders each session's passages by
`(page, distance)` so that a story traverses the material in textbook order. With
only 20 distinct page values the primary key was near-constant and ordering
collapsed onto the distance tie-breaker, so chapters were in fact traversing the
material in *relevance* order. Mean chunks sharing a page value fell from 5.2-8.0 to
1.1-2.3, so the intended ordering now holds. `planning.py` was not modified.

## FINDING-2 - false chapter headings (REPAIRED)

**Detection.** Chapter-label distribution: Grade 8 had one label for all 332 chunks,
and Grade 6 had 124 of 160 chunks labelled
`Brittle- Tendency of a material to break Glass`.

**Cause.** `CHAPTER_RE` matched any two-digit number followed by a capitalised
phrase. Numbered table rows are indistinguishable from chapter headings once the
layout is flattened. Two tables in the corpus were being read as headings whose
labels then propagated over the remainder of the book: a materials-properties table
(G6 p.44, five rows) and the Mohs hardness scale (G9P2 p.171, ten rows).

**Repair.** Two mechanisms, because one is not sufficient:

1. `CHAPTER_RE` caps the title at six words and disallows commas. Every genuine
   chapter title in the corpus is one to six words long; the G6 rows are seven to
   ten.
2. Single-word rows such as `01 Talc` are lexically identical to genuine headings
   such as `09 Light`, so no regex can separate them. `_chapter_heading_pages()`
   accepts a candidate only when it is the sole candidate on its page - a chapter
   spans many pages, whereas a table packs ten rows onto one.

**Measurement.**

| Book | False headings before | After |
|---|---|---|
| G6.pdf | 5 | **0** |
| G9P2.pdf | 10 | **0** |
| G7P1 + G7P2 (genuine) | 18 | **18 - regression check passes** |

**Unresolved.** Grade 8 still detects no chapters. Its books do not use the
`NN Title` form in the body at all: the chapter number sits alone on a line, where
`clean_page_text` discards it as a page number, and the title wraps across two
lines. The only `NN Title` lines are table-of-contents rows, correctly excluded
because they end in a page number. Detecting these requires multi-line heading
assembly, which is a different strategy rather than a tighter pattern, and was
judged out of scope. Grade 8 section labels are unaffected (59 distinct).

## FINDING-3 - doubled characters (DOCUMENTED)

**Detection.** Noticed while verifying page attribution: an affected chunk reads
`TThhrreeee ppeenn ttuubbeess iinn ddiiffffeerreenntt lleennggtthh` (G8P1 p.77).

**Cause.** The textbooks render bold type by overprinting the same glyphs, and
`pdfplumber` recovers both impressions, so every character of an affected run
appears twice. The defect is invisible in the rendered PDF.

**Incidence: 97/1101 chunks (8.8%)** - Grade 7 85 chunks (30.9%), Grade 8 12 (3.6%),
Grades 6 and 9 none.

**Disposition: not repaired.** A robust remedy needs character-level de-duplication
driven by glyph coordinates, since a naive regex on doubled letters would destroy
legitimate words such as "letter" and "book". That is not a contained change, and
changing the corpus underneath the experiments for a defect of this size was judged
the worse trade. Documented as a limitation. Worked examples in
`text_quality_impact.md`.

## FINDING-4 - mojibake from legacy font encodings (DOCUMENTED)

**Detection.** Manual spot-check of a Grade 8 chunk that began
`- laIqø Ôù ydhkh - ~sn[Q¨ ¤›øP¯õUP®`.

**Cause.** Each chapter closes with a trilingual `Technical Terms` glossary whose
Sinhala and Tamil columns use legacy non-Unicode fonts. Their bytes are recovered as
unrelated Latin characters and indexed as though they were English prose.

**Incidence: 199/1101 chunks (18.1%)** carry at least ten such characters - Grade 9
75 (22.2%), Grade 8 60 (18.1%), Grade 7 40 (14.5%), Grade 6 24 (15.4%).

**Disposition: not repaired.** Decoding the legacy encodings is a research problem in
its own right. Stripping the runs was considered and rejected: the glossary lines
interleave English terms with the corrupted columns, so a strip aggressive enough to
remove the mojibake would also remove the English term it defines.

## FINDING-3 and FINDING-4 - combined severity and retrieval impact

Counting a chunk as affected if it contains *any* corrupted token overstates the
harm, because most affected chunks are ordinary prose carrying a short glossary tail
or one bold run. Banding by the share of corrupted words, and excluding characters
the books use legitimately (superscripts, degree, micro, maths operators, the bullet
glyph), gives the honest picture:

| Corrupted share of chunk | Chunks in index | % | Retrieved passages (k=8) | % |
|---|---|---|---|---|
| clean (0%) | 837 | **76.0%** | 254 | **79.4%** |
| trace (<2%) | 82 | 7.4% | 11 | 3.4% |
| light (2-10%) | 120 | 10.9% | 33 | 10.3% |
| heavy (>=10%) | 62 | **5.6%** | 22 | **6.9%** |

Corrupted chunks are retrieved at approximately their base rate, so the defects are
neither preferentially retrieved nor avoided. **Three-quarters of the index is
entirely clean, and 6.9% of passages actually reaching the generator are heavily
corrupted.** That last figure is the one that bears on generation quality and it is
the one reported in Chapter 7.

## FINDING-5 - duplicated two-page spreads (DOCUMENTED, impact measured)

**Detection.** A supervisor spot-check reported a phrase two pages later than the
metadata claimed. Re-derivation showed the metadata was correct and that the PDF's
page structure was the actual cause.

**Cause.** Most PDF pages in these books carry a two-page *spread*, evidenced by
footers of the form
`12 Science | Animal Classification Science | Animal Classification 13`. Some
spreads additionally appear on two consecutive PDF pages, so their text is indexed
twice.

| Book | PDF pages with a spread footer |
|---|---|
| G6.pdf | 0/190 (0%) |
| G7P1.pdf | 42/160 (26%) |
| G7P2.pdf | 0/140 (0%) |
| G8P1.pdf | 94/137 (69%) |
| G8P2.pdf | 78/152 (51%) |
| G9P1.pdf | 13/122 (11%) |
| G9P2.pdf | 158/180 (88%) |

**Measured impact on curricular coverage.** Because `total_relevant` is the measure
T3 uses for how much of the syllabus a topic occupies, duplication would inflate the
project's headline claim. Near-duplicate chunk pairs were identified by 5-gram
shingle containment at a 0.80 threshold:

- 47 near-duplicate pairs, forming 22 duplicate groups
- 55/1101 chunks (5.0%) belong to a duplicate group
- 33 redundant copies (3.0% of the index): Grade 7 11, Grade 8 15, Grade 9 7,
  Grade 6 0
- **Mean inflation of `total_relevant`: 0.74%** (worst single topic 4.35%)

**Disposition: NOT deduplicated.** The pre-agreed decision rule was to deduplicate
only at 5% or above. Measured inflation is 0.74%, so the index is left as built and
the figure is reported as a limitation. Deduplicating would have changed the corpus
underneath the experiments in exchange for a sub-1% correction.

## FINDING-6 - single-page citations for multi-page chunks (REPAIRED)

**Detection.** A span audit measured, for every chunk, the first and last PDF page
its text actually occupies.

**Measurement of the defect.**

| Grade | 1 page | 2 pages | 3+ pages | Multi-page | Max span |
|---|---|---|---|---|---|
| 6 | 12 | 82 | 62 | **92.3%** | 5 |
| 7 | 31 | 183 | 61 | **88.7%** | 5 |
| 8 | 74 | 212 | 46 | **77.7%** | 4 |
| 9 | 73 | 217 | 48 | **78.4%** | 5 |
| All | 190 | 694 | 217 | **82.7%** | 5 |

A single page number was therefore an incorrect citation for four chunks in five.
Compounding this, a PDF page index is not a number a learner can act on: it appears
nowhere in the printed book, and on a spread page it corresponds to two printed
pages.

**Repair.** `build_index.py` parses the printed folio(s) from the running footer -
which `clean_page_text` discards, so it is read from the raw page text - and stores
`page_label_start` and `page_label_end` alongside the existing numeric page, which is
retained because the harness and the verification probe depend on it. Citations are
rendered from the printed folios, collapsing to a single page when the start and end
folios agree.

**Measurement.**

- Footer parsed on 959/1081 PDF pages (**88.7%**). The folio sequence is perfectly
  monotonic in all seven books - zero decreases - which is strong evidence the parse
  is correct.
- 1011/1101 chunks (**91.8%**) carry both folios; the remaining 8.2% fall back to the
  numeric PDF page rather than risk emitting a wrong folio.
- Resulting citations: 934 ranges (`pp. 1-3`) and 167 single pages (`p. 1`).

**Residual limitation.** On a spread page the two halves cannot be distinguished once
the layout is flattened, so a range may name one folio more than the text truly
occupies. This is deliberately conservative: over-wide by one page is preferable to
precisely wrong.
