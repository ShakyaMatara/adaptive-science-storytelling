# T1 false positives: which mechanism produces them

A false positive is an off-syllabus topic the retrieval gate accepts. These are the most informative failures available to the chapter, so none was removed from the probe set. This document asks a single bounded question: how many of them are produced by FINDING-4, the untranslated Sinhala and Tamil glossary text that sits in the index as unrelated Latin characters.


Gate threshold in force: `GATE_MAX_DISTANCE = 1.15`. A topic is accepted when its closest chunk is nearer than this.


**10 of 160 off-syllabus probe/grade combinations are accepted.**


## Method

For each accepted negative the top eight chunks were retrieved and classified as FINDING-4 affected when they contain at least one token carrying a non-ASCII letter that is not legitimate scientific notation. The gate decision was then recomputed with those chunks removed. If the topic is refused once they are gone, the defect caused the failure; if it is still accepted, something else did.


## Result

| Topic | Family | Grade | Best distance | Mojibake chunks in top 8 | Best clean chunk | Still accepted without them |
|---|---|---|---|---|---|---|
| Astrology and planetary influence on personality | pseudo-scientific | 8 | 1.0056 | 0/8 | 1.0056 | yes |
| Food delivery supply chains | adversarial | 8 | 1.0662 | 1/8 | 1.0662 | yes |
| Food delivery supply chains | adversarial | 9 | 1.0004 | 0/8 | 1.0004 | yes |
| Perpetual motion machines that create free energy | pseudo-scientific | 7 | 1.0148 | 0/8 | 1.0148 | yes |
| Rules and scoring in cricket | other-subject | 8 | 1.1333 | 2/8 | 1.1333 | yes |
| Sinhala grammar and sentence construction | other-subject | 6 | 1.1155 | 2/8 | 1.3893 | **NO - defect caused it** |
| Sinhala grammar and sentence construction | other-subject | 7 | 1.1252 | 3/8 | 1.3816 | **NO - defect caused it** |
| Sinhala grammar and sentence construction | other-subject | 8 | 1.1233 | 4/8 | 1.4064 | **NO - defect caused it** |
| Sinhala grammar and sentence construction | other-subject | 9 | 1.1119 | 2/8 | 1.2136 | **NO - defect caused it** |
| Solar panel installation business models | adversarial | 7 | 1.0103 | 0/8 | 1.0103 | yes |

**4 of 10 false positives disappear when FINDING-4 chunks are excluded; 6 survive.**


## Per-passage detail for the Sinhala-grammar probe

This probe is accepted at all four grades, which is why it was the suspected case.


**Grade 6** - best distance 1.1155

| Rank | Distance | Provenance | Mojibake share | Opening text |
|---|---|---|---|---|
| 1 | 1.1155 | text_layer | 4% | SCIENCE Grade 6 Educational Publications Department First Print 2014 S |
| 2 | 1.3893 | text_layer | 0% | Lecturer Department of Education University of Peradeniya 3. Dr. Perat |
| 3 | 1.4124 | text_layer | 1% | u fu;a lreKd .=fKkS fj<S iu.s oñkS rka ñKs uq;= fkd |
| 4 | 1.4166 | text_layer | 0% | country, the government has taken steps to change curriculum to suit |
| 5 | 1.4248 | text_layer | 0% | Anuradhapura 1.8 27.8 80 Badulla 0.0 30.1 50 Batticaloa 0.0 32.4 |
| 6 | 1.4646 | text_layer | 0% | Malaka Lalanajeewa - Graphic Designer Technical Assistance 1. Asanka A |
| 7 | 1.5488 | text_layer | 0% | along with a development of conduct and attitudes, to develop values |
| 8 | 1.5594 | text_layer | 0% | sun light. This energy is transferred among animals through food chain |

**Grade 7** - best distance 1.1252

| Rank | Distance | Provenance | Mojibake share | Opening text |
|---|---|---|---|---|
| 1 | 1.1252 | text_layer | 4% | SCIENCE Part - I Grade 7 Educational Publications Department First Pri |
| 2 | 1.2027 | text_layer | 4% | SCIENCE SCIENCE Part - II Part - II Grade 7 Grade |
| 3 | 1.3816 | text_layer | 0% | Chamila Ukwatta - Teacher Service D.S. Senanayaka College, Colombo 07  |
| 4 | 1.3823 | text_layer | 0% | Panel of Editors 1. M. P. Vipulasena - Director (Science) Ministry |
| 5 | 1.3900 | text_layer | 0% | education is crucial in deciding the future of a country, the |
| 6 | 1.4035 | text_layer | 2% | jk wm fuu ksjfia fid¢k isáh hq;= fõ ieug u fu;a |
| 7 | 1.4130 | text_layer | 0% | necessary knowledge out of it. The government in turn is able |
| 8 | 1.4605 | text_layer | 0% | (Development) Educational Publications Department Co-ordination K. D.  |

**Grade 8** - best distance 1.1233

| Rank | Distance | Provenance | Mojibake share | Opening text |
|---|---|---|---|---|
| 1 | 1.1233 | text_layer | 4% | SCIENCE Part - II Grade 8 Educational Publications Department First Pr |
| 2 | 1.1269 | text_layer | 4% | SCIENCE Part - I Grade 8 Educational Publications Department First Pri |
| 3 | 1.4064 | text_layer | 0% | Teacher Service Neluwa National School, Neluwa 4. L. Gamini Jayasooriy |
| 4 | 1.4067 | text_layer | 0% | Teacher Service Neluwa National School, Neluwa 4. L. Gamini Jayasooriy |
| 5 | 1.4139 | text_layer | 0% | it. The government in turn is able to provide free textbooks |
| 6 | 1.4250 | text_layer | 0% | of it. The government in turn is able to provide free |
| 7 | 1.5323 | text_layer | 1% | fj<S iu.s oñkS rka ñKs uq;= fkd j th u h |
| 8 | 1.5398 | text_layer | 1% | iu.s oñkS rka ñKs uq;= fkd j th u h iem;d |

**Grade 9** - best distance 1.1119

| Rank | Distance | Provenance | Mojibake share | Opening text |
|---|---|---|---|---|
| 1 | 1.1119 | text_layer | 4% | SCIENCE Part - II Grade 9 Educational Publications Department First Pr |
| 2 | 1.1333 | text_layer | 7% | SCIENCE Part - I Grade 9 Educational Publications Department First Pri |
| 3 | 1.2136 | ocr_vision | 0% | balance? 1. a 2. b 3. c 4. d 5. Consider |
| 4 | 1.2715 | text_layer | 0% | Education (retired) 10. M. A. P. Munasinghe - Chief Project Officer |
| 5 | 1.3819 | text_layer | 0% | htahnagte tchuer riecduulucmat ioton siusi t crthuec iaral piind dchea |
| 6 | 1.4339 | text_layer | 0% | of the editorial and writer boards as well as on the |
| 7 | 1.4359 | text_layer | 0% | future. In such an environment, with a new technological and intellect |
| 8 | 1.4651 | text_layer | 0% | should be used with maximum efficiency. Selection of timber, according |

## Reading

For 4 of the 10 accepted negatives the acceptance is traceable to FINDING-4. The mechanism is direct: the trilingual `Technical Terms` glossaries are indexed as though they were English prose, and a query in or about Sinhala lands near them because nothing else in the corpus resembles that character distribution. This is a corpus defect surfacing as a gate failure, and the two should be reported together rather than separately.


The 6 that survive are ordinary semantic near-misses: the topic genuinely shares vocabulary with the syllabus. `Solar panel installation business models` overlaps the energy chapters, `Perpetual motion machines that create free energy` overlaps energy and forces, and `Food delivery supply chains` overlaps food and preservation. These are the cases the threshold sweep is for, and they are not fixable by cleaning the corpus.
