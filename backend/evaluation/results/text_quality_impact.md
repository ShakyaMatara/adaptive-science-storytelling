# Text-quality defects and their retrieval impact

Measured against the rebuilt Chroma index. Every figure is computed from the chunks actually stored, not from the source PDFs.

Index size at time of measurement: **1101 chunks**.


## Headline

Corruption is measured as the share of a chunk's whitespace tokens that are corrupted. Characters the textbooks use legitimately are excluded: the bullet glyphs (U+00B2 as a list marker, U+2022, U+25CF, U+25AA), the ellipsis runs of fill-in-the-blank exercises, maths operators, and the Greek and Letterlike Symbols blocks, which supply mu for micro and the ohm sign.


| Corrupted share of chunk | Chunks in index | % | Retrieved passages (k=8) | % |
|---|---|---|---|---|
| clean (0%) | 911 | 82.7% | 269 | 84.1% |
| trace (<2%) | 35 | 3.2% | 6 | 1.9% |
| light (2-10%) | 98 | 8.9% | 24 | 7.5% |
| heavy (>=10%) | 57 | 5.2% | 21 | 6.6% |

**82.7% of the index is entirely clean, and 6.6% of the passages actually retrieved are heavily corrupted** (at least a tenth of their tokens). The heavily-corrupted band is the one that bears on generation quality, because that is where the text stops being usable as grounding.

Corrupted chunks are retrieved at approximately their base rate in the index, so the defects are neither preferentially retrieved nor preferentially avoided.


### Upper bound, for completeness

Counting a chunk as affected when it contains a **single** corrupted token gives a much larger figure. It is reported here only as an upper bound and should not be quoted as the level of corruption, because most chunks it counts are ordinary English prose carrying a short glossary tail or one bold run.


- Chunks containing at least one corrupted token: **190/1101 (17.3%)** - upper bound
- Retrieved passages containing at least one corrupted token: **51/320 (15.9%)** - upper bound
- Probes whose top-8 contained at least one such passage: **29/40** - upper bound


## FINDING-3 - doubled characters from overprinted bold text

The textbooks render bold type by drawing the same glyphs twice with a small offset. `pdfplumber` recovers both impressions, so every character of an affected run appears twice. The defect is invisible in the rendered PDF and surfaces only in the extracted text layer.


**Incidence: 97/1101 chunks (8.8%).**


| Grade | Affected | Total | % |
|---|---|---|---|
| 6 | 0 | 156 | 0.0% |
| 7 | 85 | 275 | 30.9% |
| 8 | 12 | 332 | 3.6% |
| 9 | 0 | 338 | 0.0% |

### Ten affected chunks


**1. G7P2.pdf, pp. 29-30** - section `Layers of atmosphere`

> Therefore, jets fly through this layer. TThhee oozzoonnee llaayyeerr lliieess iinn tthhee ssttrraattoosspphheerree.. TThhiiss iiss aa ssppeecciiaall llaayyeerr wwhhiicchh pprreevveennttss tthhee uullttrraa vviioolleett rraayyss ((UUVV rraayyss))


**2. G7P1.pdf, pp. 56-59** - section `Water as a solvent`

> to heat it. Record your observations. YYoouu wwiillll oobbsseerrvvee ssaalltt rreemmaaiinnss oonn tthhee lliidd aass aa wwhhiittee ppoowwddeerr.. DDiiffffeerreenntt ttyyppeess ooff ssaallttss ooff mmiinneerraallss aarree ddiissssoollvveedd


**3. G7P2.pdf, pp. 52-53** - section `Heat transfer`

> ccllootthheess ttoo mmaaiinnttaaiinn tthheeiirr bbooddyy tteemmppeerraattuurree ((iinn wwiinntteerr)).. AAss wwoooolleenn ccllootthheess aarree ggoooodd hheeaatt iinnssuullaattoorrss,, tthheeyy pprreevveenntt lloossiinngg bbooddyy hheeaatt


**4. G8P1.pdf, pp. 38-39** - section `Diversity and functions of plant roots`

> seen in ………...……… plants. Technical Terms DDiivveerrssiittyy ooff lleeaavveess -- mm;;%j%j,, úúúúOO;;ajajhh -- Cø»PÎß £ÀÁøPø© DDiivveerrssiittyy ooff sstteemmss -- ll||kkajaj,, úúúúOO;;ajajhh -- uskPÎß £ÀÁøPø© DDiivveerrssttiiyy ooff


**5. G8P1.pdf, pp. 67-68** - section `Musical instruments that produce sound by vibrating air columns`

> Activity 5.5 You will need :- TThhrreeee ppeenn ttuubbeess iinn ddiiffffeerreenntt lleennggtthh wwiitthh aa cclloossee eenndd Method :- ² FFiirrsstt bbllooww tthhee sshhoorrtteesstt ppeenn -- ttuubbee


**6. G7P1.pdf, pp. 99-100** - section `Light energy`

> a piece of paper, a boiling ttuubbee wwiitthh wwaatteerr,, aa tteesstt ttuubbee hhoollddeerr,, aa ppaaiirr ooff ccrruucciibbllee ttoonnggss Method:- ² Light the candle. ² HHoolldd tthhee


**7. G7P2.pdf, pp. 47-48** - section `Thermometers`

> environment as shown in Figure 14.11. FFiigguurree 1144..1111 MMeeaassuurriinngg ssooiill temperature Assignment 14.4 Measure the soil temperature in the following places and tabulate the readings y


**8. G7P2.pdf, pp. 65-66** - section `Composition of soil`

> iinn bbooiilliinngg wwaatteerr ((MMiiccrroooorrggaanniissmmss iinn tthheemm Boiled milk will be destroyed). Heated ² PPuutt eeqquuaall aammoouunnttss ooff bbooiilleedd mmiillkk iinnttoo tthhee


**9. G7P2.pdf, pp. 115-116** - section `Renewable energy sources`

> Solar power SSoollaarr ppoowweerr ggiivveess uuss lliigghhtt aass wweellll aass hheeaatt.. TThhee rreeaassoonn ffoorr tthhee wwiinndd iinn tthhee aattmmoosspphheerree aanndd wwaavveess iinn


**10. G7P2.pdf, pp. 34-35** - section `Air and its components`

> atmosphere is very essential for the mmaaiinntteennaannccee ooff tthhee hhyyddrroollooggiiccaall ccyyccllee.. • AAttmmoosspphheerree hheellppss ffoorr bbiirrddss aanndd some insects to fly. • IItt ssuuppppoorrttss ffoorr ccoommmmuunniiccaattiioonn


## FINDING-4 - mojibake from legacy Sinhala and Tamil font encodings

Each chapter closes with a trilingual `Technical Terms` glossary. The Sinhala and Tamil columns use legacy non-Unicode fonts whose bytes are recovered as unrelated Latin characters, and the result is indexed as though it were English prose.


Detection targets non-ASCII **letters** specifically. English prose contains none, whereas the legacy-font output is dense with them. Identifying corruption by non-ASCII characters generally would sweep in the bullet and ellipsis glyphs the books use deliberately, which is why an earlier draft of this measurement overstated the incidence.


**Incidence: 97/1101 chunks (8.8%).**


| Grade | Affected | Total | % |
|---|---|---|---|
| 6 | 15 | 156 | 9.6% |
| 7 | 21 | 275 | 7.6% |
| 8 | 26 | 332 | 7.8% |
| 9 | 35 | 338 | 10.4% |

### Ten affected chunks


**1. G8P2.pdf, pp. 44-47** - section `Chemical effect of electric current`

> Technical Terms Series circuit - fY%aKs.; mßm: - öuõhºa_ØÖ Parallel circuit - iudka;r.; mßm: - \©õ¢uµ©õÚ _ØÖ Electrical appliance - úoHq;a WjdrK - ªß\õuÚ® Tap key


**2. G9P1.pdf, pp. 15-18** - section `Effects of micro-organisms`

> - ld¾ñl laIqø Ôj úoHdj - øPzöuõÈß•øÓ ~sq°›¯À Nitrogen fixation - khsg%cka ;sr lsÍu - ø|uμ\ß £vzuÀ Organic food - ldnksl


**3. G9P2.pdf, pp. 40-43** - section `Natural ecosystems and built environment`

> ecosystem. Technical Terms Bio-diversity - ffcj úúO;ajh - E°º¨ £ÀÁøPø© Ecosystem - mßir moaO;sh - `ÇØöÓõSv Natural ecosystem - iajdNdúl mßir moaO;sh - C¯ØøPa `ÇØöÓõSv Man-made


**4. G9P2.pdf, pp. 126-129** - section `Prevention of lightning accidents`

> heated up Technical Terms Discharge - úi¾ckh - ªßÛÓUP® Lightning - wl=K - ªßÚÀ Thunder - .s.=reu - Ci•ÇUP® Inter monsoon - wka;¾ fudaiï - £¸ÁU


**5. G8P1.pdf, pp. 60-62** - section `Utilizing physical properties of matter`

> Discontinous nature - wika;; iajNdjh - öuõhºa]¯ØÓ ußø© Shape - yevh - ÁiÁ® Volume - mßudj - PÚÁÍÄ Compressibility - iïmSvkh - ö|¸UPØÓPÄ Density - >k;ajh


**6. G9P1.pdf, pp. 36-37** - section `Structure and function of the human ear`

> C Technical Terms Long sight - ÿr oDIaál;ajh - ÷\´ø©¨ £õºøÁ Short sight - wúÿr oDIaál;ajh - Asø©¨ £õºøÁ Binocular vision - oaúfka;%sl oDIaáh - C¸ÂÈ¨£õºøÁ


**7. G8P1.pdf, pp. 22-23** - section `Main vertebrate groups`

> Technical Terms Classification - j¾.SlrKh - £õS£õk Radial symmetry - wÍh iuñ;sh - Bøμa \©a^º Bilateral symmetry - oaúmd¾Yaúl iuñ;sh - C¸£UPa \©a^º Morphological features -


**8. G8P2.pdf, p. 96** - section `Information in a label of a food package`

> foods - msßieliqï wdydr - £u¨£kzu¨£mh EnÄPÒ Traditional methods - idïm%odhsl l%u - £õµ®£›¯ •øÓPÒ Technological methods - ;dlaIKsl l%u - öuõÈ~m£


**9. G6.pdf, pp. 19-21** - section `Differences between Plants and Animals`

> trip. Technical Terms Living organisms - Ôùka - E°µ[QPÒ Non living things - wcSù øjH - E°µØÓøÁ Environment - mßirh - `ÇÀ Micro-organisms - CIqø cSùka


**10. G7P1.pdf, p. 53** - section `Direct current and alternating current`

> - fldaIh - P»® Battery - negßh - £ØÓ› Dynamo - vhskfudaj - øhÚ÷©õ Electric current - úoHq;a Odrdj - ªß Kmh® Electric generator - úÿ,s


## FINDING-7 - symbol-font glyphs lost to the Private Use Area

Tick and cross marks in comparison tables are drawn from a symbol font (Wingdings and similar) and extract as Private Use Area codepoints such as U+F0FC, which carry no Unicode meaning and render as nothing. A table row reading "Having a mass [tick] / Does not [cross]" reaches the index as "Having a mass - Have not -". This is worse than noise: the distinction the table was teaching is silently deleted while the surrounding sentence still reads as well-formed English. Incidence is small - **27 glyph occurrences across 9/1101 chunks (0.8%)** - and it is recorded for completeness rather than investigated further.


| Grade | Affected chunks |
|---|---|
| 6 | 4 |
| 7 | 2 |
| 8 | 0 |
| 9 | 3 |

## Per-probe retrieval detail

Each in-syllabus probe retrieved at k=8.


| Topic | Grade | Retrieved | Any corruption | Heavily corrupted |
|---|---|---|---|---|
| States of matter | 7 | 8 | 4 | 3 |
| Photosynthesis | 7 | 8 | 3 | 2 |
| Rheostat | 8 | 8 | 3 | 2 |
| The water cycle | 7 | 8 | 4 | 1 |
| Heat and temperature | 7 | 8 | 3 | 1 |
| Magnets and magnetism | 7 | 8 | 2 | 1 |
| The human nervous system | 9 | 8 | 2 | 1 |
| The circulatory system | 9 | 8 | 2 | 1 |
| Classification of plants and animals | 6 | 8 | 1 | 1 |
| Elements compounds and mixtures | 8 | 8 | 1 | 1 |
| Energy and its transformations | 8 | 8 | 1 | 1 |
| Electric circuits | 8 | 8 | 1 | 1 |
| Reproduction in flowering plants | 8 | 8 | 1 | 1 |
| Atomic structure | 9 | 8 | 1 | 1 |
| Chemical reactions and equations | 9 | 8 | 1 | 1 |
| Electromagnetism | 9 | 8 | 1 | 1 |
| The periodic table of elements | 9 | 8 | 1 | 1 |
| Cells and their structure | 7 | 8 | 3 | 0 |
| Force and motion | 7 | 8 | 3 | 0 |
| Properties of matter | 6 | 8 | 2 | 0 |
| Water and its uses | 6 | 8 | 2 | 0 |
| Static electricity | 7 | 8 | 2 | 0 |
| Soil and its composition | 6 | 8 | 1 | 0 |
| Simple machines and levers | 6 | 8 | 1 | 0 |
| Sound and how we hear | 6 | 8 | 1 | 0 |
| Ecosystems and food chains | 7 | 8 | 1 | 0 |
| Respiration in living organisms | 8 | 8 | 1 | 0 |
| Reflection of light and mirrors | 8 | 8 | 1 | 0 |
| Work power and energy | 9 | 8 | 1 | 0 |
| The solar system and the planets | 6 | 8 | 0 | 0 |
| Air and the atmosphere | 6 | 8 | 0 | 0 |
| Light and shadows | 6 | 8 | 0 | 0 |
| The human skeleton | 6 | 8 | 0 | 0 |
| Food and nutrition | 7 | 8 | 0 | 0 |
| Acids bases and indicators | 8 | 8 | 0 | 0 |
| The human digestive system | 8 | 8 | 0 | 0 |
| Solar system phenomena | 8 | 8 | 0 | 0 |
| Heredity and genetics | 9 | 8 | 0 | 0 |
| Environmental pollution | 9 | 8 | 0 | 0 |
| Waves and their properties | 9 | 8 | 0 | 0 |