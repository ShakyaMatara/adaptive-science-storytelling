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
| 2 | Chapter labels absent or wrong in three of four grades | Chapter-label distribution audit | **Repaired** |
| 3 | Doubled characters from overprinted bold text | Page-attribution verification | **Repaired** |
| 4 | Mojibake from legacy Sinhala/Tamil font encodings | Manual spot-check | Documented |
| 5 | Facing-page text captured into a page's extraction | Supervisor spot-check challenge | Documented, impact measured |
| 6 | Citations named the PDF page index rather than the printed page | Span audit, then supervisor verification | **Repaired** |
| 7 | Symbol-font ticks lost to Private Use Area codepoints | Review of worked examples | **Repaired** |
| 8 | Grade 9 Part 1 distributed with image-only pages | Table-of-contents validation | **Repaired** by dual-extraction recovery |

Six defects were repaired with quantified before/after measurement; two are documented
as measured limitations. Two of the repairs (FINDING-2 and FINDING-6) were only
possible once the published tables of contents were transcribed and used as an
authoritative reference independent of the PDFs' text layer, and one (FINDING-8)
required recovering text from page images under a two-source verification procedure.

All eight were found by systematic inspection before any experiment was run. Three
were found only because an earlier conclusion was challenged and re-derived: FINDING-5
and FINDING-6 came out of a failed supervisor spot-check of the citations, and
FINDING-8 out of validating the page mapping against the tables of contents.

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

**Second repair - the regex was abandoned entirely.** Tightening the pattern removed
the false headings but could not create missing ones. Grade 8 still detected no
chapters at all, because its books never use the `NN Title` form in the body: the
chapter number sits alone on a line, where `clean_page_text` discards it as a page
number, and the title wraps across two lines. Grade 9 Part 1 is worse still, since
several of its chapter openers are image-only pages with no text layer whatsoever
(FINDING-8). No pattern applied to extracted text can recover a heading that was
never extracted.

Chapter attribution is therefore no longer derived from the text at all. The
published tables of contents were transcribed from the printed books into
`evaluation/probes/textbook_toc.md`, and a chunk is now assigned the chapter whose
start page is the greatest not exceeding the chunk's printed page. Heading detection
survives only as a paragraph-boundary signal, so chunk boundaries are unchanged.

**Measurement.** Distinct genuine chapter labels per grade, and the share of chunks
carrying one:

| Grade | Distinct chapters before | After | Chunks labelled after |
|---|---|---|---|
| 6 | 0 (124/160 chunks carried a table row as their label) | **11** | 145/156 (92.9%) |
| 7 | 18 | **19** | 258/275 (93.8%) |
| 8 | 0 | **15** | 318/332 (95.8%) |
| 9 | 0 | **19** | 319/338 (94.4%) |

The per-grade totals match the tables of contents exactly (11, 19, 15 and 19
chapters). The 61 chunks (5.5%) still labelled `(document)` are front and back
matter, which precede printed page 1 and belong to no chapter.

**Disagreements between the two methods.** Across all 1101 chunks there is exactly
one, affecting 19 chunks: for `G7P1.pdf` the regex reported `Static Electricity`
where the table of contents gives `Generation of Electricity`. This is chapter 03,
whose heading the regex never detected, so those chunks silently inherited chapter
02's label. The table of contents is correct. Grade 7's count rising from 18 to 19 is
this chapter appearing for the first time.

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

**Incidence: 97/1101 chunks (8.8%)** - Grade 9 35 (10.4%), Grade 8 26 (7.8%),
Grade 6 15 (9.6%), Grade 7 21 (7.6%).

**Detector correction.** An earlier draft of this measurement reported 199/1101
(18.1%) by counting any chunk carrying ten or more non-ASCII characters. That
heuristic was wrong: it swept in characters the books use deliberately - the bullet
glyph U+00B2, the ellipsis runs of fill-in-the-blank exercises, the ohm sign and
Greek mu - and six of ten sampled examples turned out not to be mojibake at all. The
detector now identifies non-ASCII **letters** specifically, excluding the Greek and
Letterlike Symbols blocks. English prose contains no such letters, whereas the
legacy-font output is dense with them. Every one of the ten worked examples in
`text_quality_impact.md` was re-checked as genuine after the change.

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
| clean (0%) | 911 | **82.7%** | 269 | **84.1%** |
| trace (<2%) | 35 | 3.2% | 6 | 1.9% |
| light (2-10%) | 98 | 8.9% | 24 | 7.5% |
| heavy (>=10%) | 57 | **5.2%** | 21 | **6.6%** |

Corrupted chunks are retrieved at approximately their base rate, so the defects are
neither preferentially retrieved nor avoided. **82.7% of the index is entirely clean,
and 6.6% of passages actually reaching the generator are heavily corrupted.** That
last figure is the one that bears on generation quality and it is the one reported in
Chapter 7.

As an upper bound, 190/1101 chunks (17.3%) and 51/320 retrieved passages (15.9%)
contain at least one corrupted token. That figure counts a chunk as affected for a
single bad token and should not be quoted as the level of corruption.

## FINDING-7 - symbol-font glyphs lost to the Private Use Area (DOCUMENTED)

Tick and cross marks in comparison tables are drawn from a symbol font (Wingdings and
similar) and extract as Private Use Area codepoints such as U+F0FC, which carry no
Unicode meaning and render as nothing. A table row reading
"Having a mass [tick] / Does not [cross]" reaches the index as
"Having a mass -  Have not -". This is worse than noise: the distinction the table
was teaching is silently deleted while the surrounding sentence still reads as
well-formed English, so neither the retriever nor the generator has any signal that
information is missing. Incidence is 27 glyph occurrences across 9/1101 chunks
(0.8%) - Grade 6 four chunks, Grade 9 three, Grade 7 two. Found while reviewing the
worked examples for FINDING-4, recorded for completeness, and not investigated
further.

## FINDING-5 - facing-page text captured into a page's extraction (DOCUMENTED, impact measured)

**Detection.** A supervisor spot-check reported a phrase two pages later than the
metadata claimed. Re-derivation showed the metadata was correct and that the PDFs'
text extraction was the actual cause.

**Cause.** A page's extracted text frequently includes material belonging to the
facing page - most visibly the facing page's running footer, so a footer can read
`12 Science | Animal Classification Science | Animal Classification 13` on a page
that is printed page 12 or printed page 13. Body text is captured across the fold in
the same way, which is why a heading that genuinely begins on printed page 13 also
appears in the extraction of printed page 12.

**Correction to an earlier reading of this defect.** It was first recorded here as
evidence that each PDF page carried a two-page *spread*. That was wrong, and the
error propagated into the citation repair before being caught. Page arithmetic
disproves it: for every book, (PDF pages) minus front matter minus trailing blanks
equals the last printed page exactly, so the mapping is strictly one PDF page to one
printed page. Two-folio footers are an extraction artefact, not a layout fact. See
FINDING-6.

| Book | PDF pages whose footer carries two folios |
|---|---|
| G6.pdf | 0/190 (0%) |
| G7P1.pdf | 42/160 (26%) |
| G7P2.pdf | 0/140 (0%) |
| G8P1.pdf | 94/137 (69%) |
| G8P2.pdf | 78/152 (51%) |
| G9P1.pdf | 13/122 (11%) |
| G9P2.pdf | 158/180 (88%) |

The duplicate-content measurement below is a separate matter and stands unchanged: it
was computed from chunk text, not from the spread hypothesis.

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

**First repair attempt, and why it failed.** The printed folio was initially parsed
out of the running footer. Its folio sequence was perfectly monotonic in all seven
books and 88.7% of pages parsed, which looked like strong evidence. It was not.
Monotonicity survives a systematic left/right bias, and that is exactly what the
implementation had: on a two-folio footer it always took the left value. Supervisor
verification against the physical books failed all three sample citations, with
ranges systematically over-wide and one wrong start page.

**Root cause.** There are no spreads (FINDING-5). Because a page's extraction picks up
the facing page's footer, choosing between the two folios is a coin toss. Measured
across the corpus, the left folio was correct on 193 such pages and the right on 192.

**Repair.** Footer parsing was removed. `build_index.py` now maps PDF page to printed
page with a per-book constant: `printed = pdf_page - offset`, with pages outside each
book's content range carrying no printed number. The numeric PDF page is retained
because the harness and the verification probe depend on it.

| Book | Offset | Valid PDF pages |
|---|---|---|
| G6.pdf | 14 | 15-189 |
| G7P1.pdf | 12 | 13-160 |
| G7P2.pdf | 12 | 13-139 |
| G8P1.pdf | 10 | 11-137 |
| G8P2.pdf | 10 | 11-152 |
| G9P1.pdf | 12 | 13-121 |
| G9P2.pdf | 12 | 13-180 |

**Validation.** Three independent checks, none of which reuses the others' assumptions:

1. **Page arithmetic.** For all seven books, (PDF pages) minus front matter minus
   trailing blanks equals the last printed page **exactly**.
2. **Tables of contents.** Every TOC title was located in the extracted text and its
   PDF page converted through the offset. **272 of 272 locatable entries (100.0%)
   appear as a heading on exactly the predicted page, in all seven books, with no
   exceptions.** The remaining 20 of 292 entries could not be located as a heading at
   all - image-only pages (FINDING-8), display titles interleaved with body text, or
   wording variance - and are unverifiable rather than failures.
3. **Footer cross-check.** On the 574 pages carrying a single folio, the offset agrees
   with it **574 times and disagrees zero times**. On the 385 pages carrying two, the
   offset always matches one of them - never neither - split 193 left to 192 right,
   which is the signature of the 1:1 model and of nothing else.

**Measurement.**

- 1040/1101 chunks (**94.5%**) carry printed folios; the remaining 61 (5.5%) are front
  and back matter and fall back to the PDF page.
- Citations: 857 ranges (77.8%) and 244 single pages (22.2%). Ranges are now derived
  from the chunk's actual first and last page and are therefore exact rather than
  conservative. Printed-page spans: 183 chunks span one page, 658 two, 186 three, 12
  four and 1 five.

## FINDING-8 - Grade 9 Part 1 distributed with image-only pages (DOCUMENTED)

**Detection.** During the table-of-contents validation, twelve of the twenty
unlocatable entries were all from `G9P1.pdf`. The pages they should occupy extract
zero characters.

**Extent.** 19 of 109 content pages (**17.4%**) of `G9P1.pdf` carry no text layer.
Every other book in the corpus is at 0.0%; corpus-wide the figure is 19/996 content
pages (1.9%), entirely confined to this one book. It also explains why `G9P1.pdf`
contributes only 123 chunks from 109 content pages while `G9P2.pdf` contributes 215
from 168.

This is materially more serious than the other text-quality defects because it is
*missing* content rather than corrupted content. Nothing downstream can detect it: a
topic taught only on those pages is simply absent from the corpus, however well the
retrieval gate performs, and would otherwise be scored as a gate failure.

**Affected sections.** Enumerated in `g9p1_coverage_gap.md`: 19 chapters and
sub-sections overlap the blank pages - **6 fully missing, 8 partially missing, 5
marginal**. The six fully missing are `4.2 Magnitude of force`,
`6 The Human Circulatory System`, `6.1 Structure of the human heart`,
`8 Support and Movements of Organisms`, `8.1 Support and movements of animals` and
`8.2 Bones, muscles and joints`.

**Consequence for the evaluation.** Fully missing sections are excluded from the
Phase 2 in-syllabus probe set, with this document as the stated evidence: the
curation rule admits a topic only where it demonstrably appears in that grade's
textbook, and a section with no text layer demonstrably does not appear in the index.
Partially missing and marginal sections are retained. Not repaired - closing the gap
would require OCR over the affected pages, which was out of scope.

**As a result in its own right.** National curriculum PDFs distributed with
image-only pages are a genuine obstacle to retrieval-grounded tutoring in this
setting. No amount of threshold tuning recovers content that was never text, and a
system evaluated without checking for it would attribute a distribution defect to its
own retrieval layer.

---

## Repairs applied after the defect survey

FINDING-3, FINDING-7 and FINDING-8 were initially documented as limitations and were
subsequently repaired. Their entries above record the original measurement; the
outcome of each repair is below.

### FINDING-3 - doubled characters (REPAIRED)

**Repair.** Deduplication is applied to the CHARACTER stream, not to the flattened
string: `page.dedupe_chars(tolerance=1.0)` removes a glyph when an identical glyph in
the same font and size sits at the same position, which is what overprinted bold
produces. A regex over doubled letters was rejected outright because it would destroy
`letter`, `book` and `cell`.

**Tolerance.** Chosen empirically. The recovered text is identical for any value from
0.5 to 3.0, so the choice is not delicate, and 1.0 is pdfplumber's own default. Larger
values were tested and rejected: at 8.0 the residual barely improves while legitimate
English is destroyed - across the two worst-affected books `letter` falls 5 to 0,
`book` 7 to 0, `cell` 30 to 0, `little` 4 to 0 and `different` 57 to 6.

**Measurement.**

| | Before | After |
|---|---|---|
| Chunks containing doubled words | 97/1101 (8.8%) | **7/1122 (0.6%)** |
| Grade 7 (worst affected) | 85/275 (30.9%) | 7/275 (2.5%) |
| Grade 8 | 12/332 (3.6%) | 0 |

**Safety check - passed.** Every required word survives, and several rise because
previously-doubled instances now read correctly: `letter` 23 to 27, `book` 55 to 62,
`coffee` 3 to 4, `needed` 44 to 51, `cell` 140 to 181, `little` 27 to 29, `different`
345 to 409, `immediately` 8 to 9, `assessment` 2. (`success` does not occur in these
books, before or after.)

**Chunk boundaries are unaffected.** Deduplication removes characters but not
whitespace tokens, and chunking is by word count, so every book outside G9P1 produces
exactly the same number of chunks as before.

**Residual limitation.** Seven chunks (0.6%), all in Grade 7, still contain doubled
runs where the overprint offset exceeds the tolerance - for example
`CCoonnvveexx MMiirrrroorrss` on G7P1 p.145. Raising the tolerance to clear them
damages legitimate English, as measured above, so they are left as they are.

### FINDING-7 - symbol-font glyphs (REPAIRED)

**Repair.** Private Use Area codepoints are mapped to their Unicode equivalents during
page cleaning. Each mapping was identified from at least two contexts in the books
rather than assumed from a font table:

| Codepoint | Mapped to | Evidence |
|---|---|---|
| U+F0FC | ✓ | `Having a mass - [F0FC]` / `1' pen [F0FC] [F0FC]` |
| U+F0FB | ✗ | `Have not - [F0FB]` / `3' sunlight [F0FB] [F0FB]` |
| U+F050 | ✓ | `Mark true ([F050]) or false ([F04F])` |
| U+F04F | ✗ | same line, and `put a ([F050]) and if wrong put a ([F04F])` |
| U+F03D | • | bullet marker in Activity 1.3 lists |
| U+F001 | (removed) | decorative glyph beside a signature in the foreword |

**Measurement.** Chunks containing meaningless PUA codepoints: **9/1101 (0.8%) to
0/1122 (0.0%)**. Sixteen tick and cross marks are now present in the index. The G6
p.35 comparison table, which previously indexed as `1' pen` and `3' sunlight` with the
entire answer key deleted, now reads `1' pen ✓ ✓` and `3' sunlight ✗ ✗`.

### FINDING-8 - Grade 9 Part 1 coverage gap (REPAIRED)

Full detail in `g9p1_coverage_gap.md`; per-page figures in `ocr_dual_extraction.csv`.

**Repair.** All 19 image-only pages were rendered at 300 DPI and extracted twice by
independent means - Tesseract v5.5.3 for verification, vision transcription for
content - because text recovered from an image becomes citable as a textbook page, and
one extraction is an assertion rather than evidence.

**Measurement.** All 19 pages pass a three-part gate: at least 100 characters
(695-1,970), dictionary-word ratio at least 0.60 (0.738-0.956), and A/B token
agreement at least 0.70 (**0.782-0.990, mean 0.924**). Every substantive divergence is
Tesseract missing or garbling text, never the transcription introducing content.
Independently, 8 of 8 pages that open a contents-listed section reproduce that heading
verbatim on exactly the predicted printed page.

**Outcome.** 25,006 characters recovered; `G9P1.pdf` 123 to 144 chunks, Grade 9 338 to
359, corpus 1,101 to 1,122. No section remains fully missing, so the Phase 2 exclusion
list is empty.

## Provenance of recovered text

Every chunk drawing on recovered text carries `source_type="ocr_vision"` and
`ocr_agreement`, the lowest A/B agreement among the recovered pages it uses;
text-layer chunks carry `source_type="text_layer"` and no agreement value. **36 chunks
(3.2% of the index) are flagged.**

An earlier implementation tagged a chunk by its starting page and flagged only 21. A
chunk routinely spans several pages, so that left 15 chunks which *contained*
recovered text looking like pure text layer - quietly defeating the exclusion the flag
exists to permit. A chunk is now flagged when any of its words came from a recovered
page.

Any Chapter 7 result can therefore be recomputed with recovered content excluded, and
the chapter is to report what proportion of its results rest on recovered text. Where
a result does depend on it, the conditional reading in `g9p1_coverage_gap.md` applies:
excluding recovered chunks restores the six originally fully-missing sections.
