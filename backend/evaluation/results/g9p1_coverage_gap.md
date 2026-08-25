# FINDING-8: Grade 9 Part 1 coverage gap, and its recovery

`G9P1.pdf` is distributed with pages that carry no text layer. Both PDF engines
available here agree: `pdfminer` (via pdfplumber) and `pdfium` each return zero
characters for all 19, while a control page on the same book returns 1,938. This was
missing content rather than corrupted content, and nothing downstream could have
detected it: a topic taught only on those pages would simply have been absent from
the corpus, and would have been scored as a retrieval failure.

## Extent of the original gap

- **19 of 109 content pages (17.4%)** of `G9P1.pdf` yielded no extractable text.
- Every other book in the corpus was at 0.0%; corpus-wide the figure was 19/996
  content pages (1.9%), entirely confined to this one book.
- Blank PDF pages: 14, 25, 28, 29, 45, 54, 65, 66, 68, 71, 84, 86, 96, 101, 102, 103,
  115, 117, 118.
- Blank printed pages: 2, 13, 16, 17, 33, 42, 53, 54, 56, 59, 72, 74, 84, 89, 90, 91,
  103, 105, 106.

It also explained why `G9P1.pdf` contributed only 123 chunks from 109 content pages
while `G9P2.pdf` contributed 215 from 168.

## Sections that were affected

| Level | No. | Title | Printed range | Pages | Blank | Original classification |
|---|---|---|---|---|---|---|
| chapter | 1 | Applications of Micro-organisms | 1-2 | 2 | 2 | MARGINAL |
| section | 1.1 | Micro-organisms | 1-2 | 2 | 2 | MARGINAL |
| section | 1.3 | Effects of micro-organisms | 4-15 | 12 | 13 | PARTIALLY MISSING |
| chapter | 2 | Eye and Ear | 16-21 | 6 | 16, 17 | PARTIALLY MISSING |
| section | 2.1 | Structure and function of the human eye | 16-21 | 6 | 16, 17 | PARTIALLY MISSING |
| section | 2.5 | Defects of ear | 33-37 | 5 | 33 | MARGINAL |
| section | 3.1 | Elements | 39-43 | 5 | 42 | PARTIALLY MISSING |
| section | 4.2 | Magnitude of force | 53 | 1 | 53 | **FULLY MISSING** |
| section | 4.3 | Direction of force and point of application | 54-55 | 2 | 54 | MARGINAL |
| section | 4.4 | Graphical representation of force | 56-59 | 4 | 56, 59 | PARTIALLY MISSING |
| chapter | 6 | The Human Circulatory System | 72 | 1 | 72 | **FULLY MISSING** |
| section | 6.1 | Structure of the human heart | 72 | 1 | 72 | **FULLY MISSING** |
| section | 6.2 | Arteries, veins and capillaries | 73-74 | 2 | 74 | MARGINAL |
| chapter | 7 | Plant Growth Substances | 83-85 | 3 | 84 | PARTIALLY MISSING |
| section | 7.1 | Introduction to plant growth substances | 83-85 | 3 | 84 | PARTIALLY MISSING |
| chapter | 8 | Support and Movements of Organisms | 89 | 1 | 89 | **FULLY MISSING** |
| section | 8.1 | Support and movements of animals | 89 | 1 | 89 | **FULLY MISSING** |
| section | 8.2 | Bones, muscles and joints | 90-91 | 2 | 90, 91 | **FULLY MISSING** |
| section | 9.3 | Evolution | 102-106 | 5 | 103, 105, 106 | PARTIALLY MISSING |

Originally 6 fully missing, 8 partially missing, 5 marginal.

## Recovery by dual extraction

All 19 pages were rendered to PNG at 300 DPI and extracted twice by independent
means, because text recovered from an image becomes citable as a textbook page and a
single extraction is an assertion rather than evidence:

- **Extraction A** - Tesseract v5.5.3, English, `--psm 3`.
- **Extraction B** - vision transcription, verbatim: prose, headings, figure captions,
  diagram labels, table cells and question numbers that are *written* on the page.
  Nothing depicted is described, nothing is corrected or inferred, and the Sinhala and
  Tamil glossary columns are marked rather than transcribed.

Extraction B is what is indexed, because it preserves reading order and table
structure. Tesseract's role is verification only.

### Gate results - all 19 pages pass

| Criterion | Threshold | Result |
|---|---|---|
| characters recovered | >= 100 | 695 - 1,970 |
| dictionary-word ratio | >= 0.60 | 0.738 - 0.956 |
| A/B token agreement | >= 0.70 | **0.782 - 0.990, mean 0.924** |

Per-page figures are in `ocr_dual_extraction.csv`. The dictionary check uses a lexicon
built from the corpus's own text-layer chunks, so science vocabulary is not penalised.

### Where the two extractions diverged

Every substantive divergence is Tesseract missing or garbling text, never extraction B
introducing content. Vision tokens that also appear in Tesseract's output run
0.928-1.000 across the 19 pages.

- **printed p.2** (agreement 0.782) - Tesseract dropped the table row header
  `Protozoa` and the figure labels.
- **printed p.59** (0.824) - Tesseract produced garbage from the Sinhala and Tamil
  glossary columns (`8dd0na`, `acod`, `8as`), which is why its token overlap is lowest
  here; extraction B marked those columns instead of transcribing them.
- **printed p.13** (0.859) - Tesseract missed the photograph captions `Bread` and
  `Milk`, and rendered bullet glyphs as `e` and `o`.

Tesseract also mangled display type in ways that are immediately visible, for example
`The Human Circ / System` and `SS) Structure of the human heart`. That it fails
loudly is precisely what makes it useful as a check.

### Independent corroboration from the tables of contents

Eight of the 19 pages open a section listed in the published contents. In **8 of 8**
cases the transcription reproduces that heading verbatim, on exactly the printed page
the contents predicts - including all four of the previously fully-missing sections.
The tables of contents were transcribed from the physical books, so this is a check
against the printed source rather than against the PDF.

## Outcome

- **25,006 characters and 4,027 words recovered** across 19 pages.
- `G9P1.pdf` rises from 123 to 144 chunks; Grade 9 from 338 to 359; the corpus from
  1,101 to 1,122.
- **No section remains fully missing.** The Phase 2 exclusion list is empty.

## Provenance

Every chunk drawing on recovered text carries `source_type="ocr_vision"` and
`ocr_agreement` set to the lowest A/B agreement among the recovered pages it uses;
text-layer chunks carry `source_type="text_layer"` and no agreement value.

**36 chunks (3.2% of the index) are flagged**, not 21. A chunk routinely spans several
pages, so tagging by its starting page alone left 15 chunks that *contained* recovered
text looking like pure text layer - which would have quietly defeated the exclusion
the flag exists to permit. A chunk is therefore flagged when *any* of its words came
from a recovered page.

Any Chapter 7 result can be recomputed with recovered content excluded, and the
proportion of results resting on recovered text is to be reported.

## Conditional reading

The conclusion that no section is fully missing depends on the recovered text being
accepted. If recovered chunks are excluded from an analysis, the original six fully
missing sections apply to that analysis and should be excluded from its positive
probe set: `4.2 Magnitude of force`, `6 The Human Circulatory System`,
`6.1 Structure of the human heart`, `8 Support and Movements of Organisms`,
`8.1 Support and movements of animals`, `8.2 Bones, muscles and joints`.

## As a result in its own right

National curriculum PDFs distributed with image-only pages are a genuine obstacle to
retrieval-grounded tutoring in this setting. No amount of threshold tuning recovers
content that was never text, and a system evaluated without checking for it would
attribute a distribution defect to its own retrieval layer. Recovery is possible, but
only with a verification procedure strong enough that the recovered text can be cited
with the same confidence as the text layer.
