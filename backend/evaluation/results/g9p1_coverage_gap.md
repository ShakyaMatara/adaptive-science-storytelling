# FINDING-8: Grade 9 Part 1 coverage gap

`G9P1.pdf` is distributed with pages that carry no text layer. `pdfplumber` returns an empty string for them, so their content never reaches the index. This is missing content rather than corrupted content: nothing downstream can detect it, and a topic taught only on those pages is absent from the corpus however well the retrieval gate performs.


## Extent

- **19 of 109 content pages (17.4%)** yield no extractable text.
- Every other book in the corpus is at 0.0%; corpus-wide the figure is 19/996 content pages (1.9%), entirely confined to this one book.
- Blank PDF pages: 14, 25, 28, 29, 45, 54, 65, 66, 68, 71, 84, 86, 96, 101, 102, 103, 115, 117, 118
- Blank printed pages: 2, 13, 16, 17, 33, 42, 53, 54, 56, 59, 72, 74, 84, 89, 90, 91, 103, 105, 106


## Affected sections

A section is FULLY MISSING when every page of its range is blank, MARGINAL when a single page at one edge of its range is blank, and PARTIALLY MISSING otherwise.


| Level | No. | Title | Printed range | Pages | Blank | Classification |
|---|---|---|---|---|---|---|
| chapter | 1 | Applications of Micro-organisms | 1-2 | 2 | 2 | **MARGINAL** |
| section | 1.1 | Micro-organisms | 1-2 | 2 | 2 | **MARGINAL** |
| section | 1.3 | Effects of micro-organisms | 4-15 | 12 | 13 | **PARTIALLY MISSING** |
| chapter | 2 | Eye and Ear | 16-21 | 6 | 16, 17 | **PARTIALLY MISSING** |
| section | 2.1 | Structure and function of the human eye | 16-21 | 6 | 16, 17 | **PARTIALLY MISSING** |
| section | 2.5 | Defects of ear | 33-37 | 5 | 33 | **MARGINAL** |
| section | 3.1 | Elements | 39-43 | 5 | 42 | **PARTIALLY MISSING** |
| section | 4.2 | Magnitude of force | 53-53 | 1 | 53 | **FULLY MISSING** |
| section | 4.3 | Direction of force and point of application | 54-55 | 2 | 54 | **MARGINAL** |
| section | 4.4 | Graphical representation of force | 56-59 | 4 | 56, 59 | **PARTIALLY MISSING** |
| chapter | 6 | The Human Circulatory System | 72-72 | 1 | 72 | **FULLY MISSING** |
| section | 6.1 | Structure of the human heart | 72-72 | 1 | 72 | **FULLY MISSING** |
| section | 6.2 | Arteries, veins and capillaries | 73-74 | 2 | 74 | **MARGINAL** |
| chapter | 7 | Plant Growth Substances | 83-85 | 3 | 84 | **PARTIALLY MISSING** |
| section | 7.1 | Introduction to plant growth substances | 83-85 | 3 | 84 | **PARTIALLY MISSING** |
| chapter | 8 | Support and Movements of Organisms | 89-89 | 1 | 89 | **FULLY MISSING** |
| section | 8.1 | Support and movements of animals | 89-89 | 1 | 89 | **FULLY MISSING** |
| section | 8.2 | Bones, muscles and joints | 90-91 | 2 | 90, 91 | **FULLY MISSING** |
| section | 9.3 | Evolution | 102-106 | 5 | 103, 105, 106 | **PARTIALLY MISSING** |

## Summary

- FULLY MISSING: **6** sections
- PARTIALLY MISSING: **8** sections
- MARGINAL: **5** sections

## Consequence for the evaluation

Sections classified FULLY MISSING are excluded from the Phase 2 in-syllabus probe set. The curation rule admits a topic only if it demonstrably appears in that grade's textbook, and a section with no text layer demonstrably does not appear in the index; scoring it as a false negative would attribute a distribution defect to the retrieval gate. PARTIALLY MISSING and MARGINAL sections are retained, since enough of their content is indexed to be found. Each exclusion is recorded in the probe file with this document as its evidence.

More broadly, this is a result in its own right. National curriculum PDFs distributed with image-only pages are a genuine obstacle to retrieval-grounded tutoring in this setting: no amount of tuning recovers content that was never text. Closing the gap would require OCR over the affected pages, which was out of scope here.
