# Text-quality defects and their retrieval impact

Measured against the rebuilt Chroma index. Every figure is computed from the chunks actually stored, not from the source PDFs.

Index size at time of measurement: **1122 chunks**.


## Headline

Corruption is measured as the share of a chunk's whitespace tokens that are corrupted. Characters the textbooks use legitimately are excluded: the bullet glyphs (U+00B2 as a list marker, U+2022, U+25CF, U+25AA), the ellipsis runs of fill-in-the-blank exercises, maths operators, and the Greek and Letterlike Symbols blocks, which supply mu for micro and the ohm sign.


| Corrupted share of chunk | Chunks in index | % | Retrieved passages (k=8) | % |
|---|---|---|---|---|
| clean (0%) | 1019 | 90.8% | 287 | 89.7% |
| trace (<2%) | 19 | 1.7% | 3 | 0.9% |
| light (2-10%) | 54 | 4.8% | 17 | 5.3% |
| heavy (>=10%) | 30 | 2.7% | 13 | 4.1% |

**90.8% of the index is entirely clean, and 4.1% of the passages actually retrieved are heavily corrupted** (at least a tenth of their tokens). The heavily-corrupted band is the one that bears on generation quality, because that is where the text stops being usable as grounding.

Corrupted chunks are retrieved at approximately their base rate in the index, so the defects are neither preferentially retrieved nor preferentially avoided.


### Upper bound, for completeness

Counting a chunk as affected when it contains a **single** corrupted token gives a much larger figure. It is reported here only as an upper bound and should not be quoted as the level of corruption, because most chunks it counts are ordinary English prose carrying a short glossary tail or one bold run.


- Chunks containing at least one corrupted token: **103/1122 (9.2%)** - upper bound
- Retrieved passages containing at least one corrupted token: **33/320 (10.3%)** - upper bound
- Probes whose top-8 contained at least one such passage: **25/40** - upper bound


## FINDING-3 - doubled characters from overprinted bold text

The textbooks render bold type by drawing the same glyphs twice with a small offset. `pdfplumber` recovers both impressions, so every character of an affected run appears twice. The defect is invisible in the rendered PDF and surfaces only in the extracted text layer.


**Incidence: 7/1122 chunks (0.6%).**


| Grade | Affected | Total | % |
|---|---|---|---|
| 6 | 0 | 156 | 0.0% |
| 7 | 7 | 275 | 2.5% |
| 8 | 0 | 332 | 0.0% |
| 9 | 0 | 359 | 0.0% |

### Ten affected chunks


**1. G7P1.pdf, pp. 133-134** - section `Images formed by curved mirrors`

> mirrors are used in day-to-day life. CCoonnvveexx MMiirrrroorrss Let us do Activity 9.14 to observe the nature of images formed by convex mirrors. AAccttivivitityy 9 9.1.144


**2. G7P2.pdf, pp. 1-2** - section `Production of sound`

> some of them. Let us do AAccttiivviittyy 1111..11 ttoo fifinndd oouutt mmoorree aabboouutt tthhee ssoouunnddss wwee hheeaarr.. Speaker Activity 11.1 You will need :- A speaker,


**3. G7P2.pdf, pp. 61-62** - section `Composition of soil`

> water. Figure 15.4 Separation of ² TThheenn,, aadddd iitt ttoo tthhee wwaatteerr aallrreeaaddyy pprreesseenntt iinn tthhee components of soil polythene bag and leave to settle. ²


**4. G7P1.pdf, pp. 41-43** - section `Sources of electricity`

> simple cell. Dilute Sulphuric acid Ssiimmppllee cceellll Standard symbol to denote a cell Fig:- 3.9 Direction of current flowing from an electric source


**5. G7P2.pdf, pp. 106-107** - section `Rock weathering`

> texture of things near that lichen ((cchheecckk wwiitthh yyoouurr fifinnggeerrttiippss)) oonnccee iinn ttwwoo wweeeekkss Figure 18.10 Lichen for about six months. on a rock ² Observe


**6. G7P1.pdf, pp. 42-44** - section `Sources of electricity`

> simple cell. Dilute Sulphuric acid Ssiimmppllee cceellll Standard symbol to denote a cell Fig:- 3.9 Direction of current flowing from an electric source Let us connect


**7. G7P2.pdf, pp. 11-12** - section `Organisational levels of life`

> numerous hexagonal units BuilBduiilndigng uunnitit BuiBludiildningg uunniitt Figure 12.1 Wall made of bricks Figure 12.2 Bee hive The living body contains large number of small building


## FINDING-4 - mojibake from legacy Sinhala and Tamil font encodings

Each chapter closes with a trilingual `Technical Terms` glossary. The Sinhala and Tamil columns use legacy non-Unicode fonts whose bytes are recovered as unrelated Latin characters, and the result is indexed as though it were English prose.


Detection targets non-ASCII **letters** specifically. English prose contains none, whereas the legacy-font output is dense with them. Identifying corruption by non-ASCII characters generally would sweep in the bullet and ellipsis glyphs the books use deliberately, which is why an earlier draft of this measurement overstated the incidence.


**Incidence: 96/1122 chunks (8.6%).**


| Grade | Affected | Total | % |
|---|---|---|---|
| 6 | 15 | 156 | 9.6% |
| 7 | 20 | 275 | 7.3% |
| 8 | 26 | 332 | 7.8% |
| 9 | 35 | 359 | 9.7% |

### Ten affected chunks


**1. G8P2.pdf, pp. 45-46** - section `Chemical effect of electric current`

> Technical Terms Series circuit - fY%aKs.; mßm: - öuõhºa_ØÖ Parallel circuit - iudka;r.; mßm: - \©õ¢uµ©õÚ _ØÖ Electrical appliance - úoHq;a WjdrK - ªß\õuÚ® Tap key


**2. G9P1.pdf, pp. 36-38** - section `Defects of ear`

> C Technical Terms Long sight - ÿr oDIaál;ajh - ÷\´ø©¨ £õºøÁ Short sight - wúÿr oDIaál;ajh - Asø©¨ £õºøÁ Binocular vision - oaúfka;%sl oDIaáh - C¸ÂÈ¨£õºøÁ


**3. G9P2.pdf, pp. 41-42** - section `Natural ecosystems and built environment`

> ecosystem. Technical Terms Bio-diversity - ffcj úúO;ajh - E°º¨ £ÀÁøPø© Ecosystem - mßir moaO;sh - `ÇØöÓõSv Natural ecosystem - iajdNdúl mßir moaO;sh - C¯ØøPa `ÇØöÓõSv Man-made


**4. G9P1.pdf, pp. 14-15** - section `Effects of micro-organisms`

> by micro-organisms. Technical Terms Micro-organism - laIqø Ôúhd - ~sn[Q Microbiology - laIqø Ôj úoHdj - ~sq°›¯À Substrate - Wmia;rh - RÌ¨£øh Industrial microbiology - ld¾ñl


**5. G9P2.pdf, pp. 127-129** - section `Prevention of lightning accidents`

> heated up Technical Terms Discharge - úi¾ckh - ªßÛÓUP® Lightning - wl=K - ªßÚÀ Thunder - .s.=reu - Ci•ÇUP® Inter monsoon - wka;¾ fudaiï - £¸ÁU


**6. G8P1.pdf, pp. 60-62** - section `Utilizing physical properties of matter`

> Discontinous nature - wika;; iajNdjh - öuõhºa]¯ØÓ ußø© Shape - yevh - ÁiÁ® Volume - mßudj - PÚÁÍÄ Compressibility - iïmSvkh - ö|¸UPØÓPÄ Density - >k;ajh


**7. G8P1.pdf, pp. 22-23** - section `Main vertebrate groups`

> Technical Terms Classification - j¾.SlrKh - £õS£õk Radial symmetry - wÍh iuñ;sh - Bøμa \©a^º Bilateral symmetry - oaúmd¾Yaúl iuñ;sh - C¸£UPa \©a^º Morphological features -


**8. G8P2.pdf, p. 96** - section `Information in a label of a food package`

> foods - msßieliqï wdydr - £u¨£kzu¨£mh EnÄPÒ Traditional methods - idïm%odhsl l%u - £õµ®£›¯ •øÓPÒ Technological methods - ;dlaIKsl l%u - öuõÈ~m£


**9. G6.pdf, pp. 19-21** - section `Differences between Plants and Animals`

> trip. Technical Terms Living organisms - Ôùka - E°µ[QPÒ Non living things - wcSù øjH - E°µØÓøÁ Environment - mßirh - `ÇÀ Micro-organisms - CIqø cSùka


**10. G7P1.pdf, p. 53** - section `Direct current and alternating current`

> - fldaIh - P»® Battery - negßh - £ØÓ› Dynamo - vhskfudaj - øhÚ÷©õ Electric current - úoHq;a Odrdj - ªß Kmh® Electric generator - úÿ,s


## FINDING-7 - symbol-font glyphs lost to the Private Use Area

Tick and cross marks in comparison tables are drawn from a symbol font (Wingdings and similar) and extract as Private Use Area codepoints such as U+F0FC, which carry no Unicode meaning and render as nothing. A table row reading "Having a mass [tick] / Does not [cross]" reaches the index as "Having a mass - Have not -". This is worse than noise: the distinction the table was teaching is silently deleted while the surrounding sentence still reads as well-formed English. Incidence is small - **0 glyph occurrences across 0/1122 chunks (0.0%)** - and it is recorded for completeness rather than investigated further.


| Grade | Affected chunks |
|---|---|
| 6 | 0 |
| 7 | 0 |
| 8 | 0 |
| 9 | 0 |

## Per-probe retrieval detail

Each in-syllabus probe retrieved at k=8.


| Topic | Grade | Retrieved | Any corruption | Heavily corrupted |
|---|---|---|---|---|
| Rheostat | 8 | 8 | 3 | 2 |
| The human nervous system | 9 | 8 | 2 | 1 |
| The circulatory system | 9 | 8 | 2 | 1 |
| Classification of plants and animals | 6 | 8 | 1 | 1 |
| States of matter | 7 | 8 | 1 | 1 |
| Elements compounds and mixtures | 8 | 8 | 1 | 1 |
| Electric circuits | 8 | 8 | 1 | 1 |
| Reproduction in flowering plants | 8 | 8 | 1 | 1 |
| Atomic structure | 9 | 8 | 1 | 1 |
| Chemical reactions and equations | 9 | 8 | 1 | 1 |
| Electromagnetism | 9 | 8 | 1 | 1 |
| The periodic table of elements | 9 | 8 | 1 | 1 |
| Properties of matter | 6 | 8 | 2 | 0 |
| Water and its uses | 6 | 8 | 2 | 0 |
| Cells and their structure | 7 | 8 | 2 | 0 |
| Static electricity | 7 | 8 | 2 | 0 |
| Soil and its composition | 6 | 8 | 1 | 0 |
| Simple machines and levers | 6 | 8 | 1 | 0 |
| Sound and how we hear | 6 | 8 | 1 | 0 |
| Magnets and magnetism | 7 | 8 | 1 | 0 |
| Ecosystems and food chains | 7 | 8 | 1 | 0 |
| The water cycle | 7 | 8 | 1 | 0 |
| Respiration in living organisms | 8 | 8 | 1 | 0 |
| Reflection of light and mirrors | 8 | 8 | 1 | 0 |
| Work power and energy | 9 | 8 | 1 | 0 |
| The solar system and the planets | 6 | 8 | 0 | 0 |
| Air and the atmosphere | 6 | 8 | 0 | 0 |
| Light and shadows | 6 | 8 | 0 | 0 |
| The human skeleton | 6 | 8 | 0 | 0 |
| Photosynthesis | 7 | 8 | 0 | 0 |
| Heat and temperature | 7 | 8 | 0 | 0 |
| Food and nutrition | 7 | 8 | 0 | 0 |
| Force and motion | 7 | 8 | 0 | 0 |
| Acids bases and indicators | 8 | 8 | 0 | 0 |
| Energy and its transformations | 8 | 8 | 0 | 0 |
| The human digestive system | 8 | 8 | 0 | 0 |
| Solar system phenomena | 8 | 8 | 0 | 0 |
| Heredity and genetics | 9 | 8 | 0 | 0 |
| Environmental pollution | 9 | 8 | 0 | 0 |
| Waves and their properties | 9 | 8 | 0 | 0 |