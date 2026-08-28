# Features added in the user-facing capability expansion

This document records the ten features added to the ASCALS platform during the
user-facing expansion phase, undertaken on the branch `feature-expansion` from
the branch point `a37b6a9`. The phase was motivated by an assessment that the
system's visible surface understated the capability of its backend: prior to this
work a learner could log in, enter a topic, choose a grade, read a generated
chapter and answer its questions, and no more. The retrieval, planning,
adaptation and generation subsystems — the components against which the
evaluation programme reported — were not observable through the interface at all.

The overriding constraint of the phase was that no behaviour already measured by
that programme could change. Four modules (`retrieval.py`, `planning.py`,
`adaptation.py` and `llm.py`) were treated as frozen and are byte-identical to
the branch point; no tuned constant was altered; every schema change is additive.
Several designs recorded below are shaped by that constraint, and where a
different implementation depth would have been preferable in its absence, this is
stated explicitly.

Each entry records what the feature does, the requirement it satisfies, the files
that implement it, the data it reads, what it writes if anything, and its
limitations.

---

## 1. Syllabus browser

**What it does.** Presents the Grade 6–9 national science curriculum as a
navigable tree of grades, chapters and sub-sections, each annotated with the page
range on which it is printed in the corresponding textbook. A search field
filters the tree by chapter and sub-section title, expanding matches
automatically. Selecting any row begins a story on that material, passing the
contents page's own wording as the topic together with the correct grade.

**Requirement.** Supports FR-01 (topic selection) by replacing free-text entry
with curriculum-anchored selection. It also serves an evidential purpose: it
renders the system's claim of curricular grounding inspectable rather than
asserted, since the tree is parsed from the same transcribed contents pages
against which the retrieval evaluation's probes are graded.

**Implementation.** `backend/core/api_curriculum.py`,
`frontend/src/pages/BrowsePage.jsx`, `frontend/src/styles/discovery.css`. Served
at `GET /api/curriculum`.

**Data read.** `backend/evaluation/probes/textbook_toc.md`, parsed once on first
request and held in a module-level cache under a lock. No database access.

**Data written.** None.

**Limitations.** Page ranges are *derived*, not transcribed: a row is taken to
end one page before its next sibling begins, and a range is never derived across
a book file boundary. Where no end can be established — the final row of a book
file, or a row printed on a single page — the response sets `has_range` to false
and the interface prints a single page reference rather than a spurious range.
Fifty-five of the 292 rows are in this state. The parser recovers 64 chapters and
228 sub-sections, verified against the source file. Because a grade printed in
two parts continues its chapter numbering across the split, chapters are
presented as one continuous list per grade while each retains the book file it
was printed in.

## 2. Story library

**What it does.** Lists every story the authenticated learner has begun, newest
activity first, as a filterable grid of cards showing topic, grade, progress
through the planned chapters, points, score and badges earned. Stories may be
filtered by grade and by completion state. An unfinished story may be resumed in
one action; any story may be reopened for reading.

**Requirement.** Supports FR-16 (session persistence) by making persisted
sessions retrievable by the learner rather than only by the API.

**Implementation.** `backend/core/api_library.py`,
`frontend/src/pages/LibraryPage.jsx`. Served at `GET /api/me/library`.

**Data read.** `Session`, `Chapter`, `Question` and `Badge`, restricted to the
authenticated learner.

**Data written.** None. Resumption is performed through the pre-existing
`POST /api/sessions` endpoint, whose resume branch returns the unfinished session
and writes nothing.

**Progress reporting.** A card reports the chapters whose questions were actually
answered, which is the same measure the reader uses to decide whether a chapter is
finished. Completion does not by itself fill the bar: a story ended before its
planned last chapter is shown as "Ended early — N of M chapters read", because
marking it complete and simultaneously claiming every chapter had been read
misdescribed a story that was abandoned early. Ending a story early is itself
offered only once the current chapter's questions are answered; before that the
reader offers to pause instead, which leaves the story in progress and resumable.

**Limitations.** The endpoint costs four queries irrespective of how many stories
a learner has, but it loads each chapter's full text in order to count questions;
for a learner with a very large history this is more data than the summary
requires. A story created before content-driven planning was introduced reports
no planned chapter total, and the card falls back to the number of chapters
actually generated.

## 3. Progress dashboard

**What it does.** Aggregates the learner's history into headline counters
(topics studied, chapters read, questions attempted and answered correctly,
accuracy, points, badges, stories completed and in progress), per-concept mastery
grouped by topic, and ranked lists of strongest and weakest concepts. A scatter
plot sets mastery against the number of questions answered for each concept, so
that a low score supported by little evidence is distinguishable from a
well-evidenced gap. Every concept displayed is a link to revision.

**Requirement.** FR-17 (progress reporting), which was partially implemented
before this phase.

**Implementation.** `backend/core/api_progress.py`,
`frontend/src/pages/ProgressPage.jsx`, `frontend/src/styles/insight.css`. Served
at the pre-existing `GET /api/me/progress`.

**Data read.** `ConceptStat`, `Session`, `Chapter`, `Question`, `Badge`.

**Data written.** None. The learner profile is looked up without creating one,
in contrast to the superseded implementation, which created a profile row on a
`GET`.

**Syllabus placement.** A learner types a topic freely, so the mastery list
originally read as an inventory of whatever wording had been entered —
"Light emitting diode" is not a heading in any of the books. Each topic is
therefore resolved to the section of the printed syllabus its story was actually
grounded in, and the list is grouped under that section: the example above is
presented as *8.5 Electronic Appliances*, under *8. Electricity for a Comfortable
Life*, with the learner's own wording retained beneath it.

The resolution is a lookup, not a guess about wording. Each stored source
reference carries a printed page citation, and the contents pages record the page
at which every chapter and sub-section begins, so the section that owns a page is
determined by the same artefact the syllabus browser is built from. The vote is
taken in two stages — the chapter first, then the sub-section within it — because
a story typically draws on several sub-sections and no single one of them holds a
majority; deciding the chapter first finds the part of the book the story came
from and keeps the placement stable. The response reports how many of the stored
references supported the placement, so the interface can be honest about how much
of the grounding agreed.

This deliberately does *not* trust the vector index's own `chapter` and `section`
metadata, which is unreliable: a Grade 6 chunk citing pp. 99-101 — squarely inside
chapter 7, "Magnets" — carries the section label "Applications of Light", and some
chunks carry the placeholder label "(document)". The contents pages are the
authority, and the lookup corrects those errors rather than propagating them.

The topic string itself is never rewritten. It is the key that concept mastery,
story resumption and badges are recorded against, so the placement annotates it
rather than replacing it. A topic whose story carried no page references, or whose
citations could not be resolved, is reported as unplaced and grouped separately
rather than being filed under a section it did not come from.

**Limitations.** The endpoint was extended rather than replaced: its original
`progress` key retains its exact prior shape, ordering and rounding, and the
pre-existing test asserting that contract passes unchanged. This is the evidence
that the extension altered no measured behaviour. The definitions used for
"strongest" and "weakest" are returned in the response body rather than being
implied by the interface. Concepts are grouped by the topic string as the learner
typed it, so two spellings of one topic are reported separately. No charting
dependency was added; the plot is inline SVG.

## 4. Provenance viewer

**What it does.** Opens, from any chapter, a panel showing the textbook passages
on which that chapter was grounded, each reproduced verbatim with its printed
page citation, textbook chapter and section, and grade. The extract is
typographically distinguished from the generated narrative and labelled as the
textbook's own wording, with a plain-language explanation for a reader unfamiliar
with retrieval-augmented generation.

**Requirement.** Evidences NFR-06 (curricular fidelity) and supports FR-05
(textbook-grounded generation) by making the grounding directly inspectable.

**Implementation.** `backend/core/api_provenance.py`,
`frontend/src/components/ProvenancePanel.jsx`. Served at
`GET /api/chapters/<id>/provenance`.

**Data read.** `Chapter.sources`, and the Chroma vector index by way of
`retrieval.retrieve()` and a metadata lookup on the same collection. Both are
pure reads.

**Data written.** None.

**Limitations, and a design constraint.** `Chapter.sources` persists page
references only; the passage text itself is not stored, because the function that
would have to store it is in a frozen module. The passages are therefore
*recovered* at display time — first by a semantic sweep, then by an exact lookup
on `(source_file, page)` for any reference the sweep does not return — and cached
per chapter in memory, bounded to 256 chapters. The response states which path
recovered each passage and how many stored references could not be recovered at
all, so the viewer never implies more provenance than it has. On the development
corpus all references were recovered semantically; the exact path and the
index-unavailable path were exercised deliberately. Recovery is not guaranteed:
if the index is rebuilt with different chunk boundaries, references recorded
against the previous build may no longer resolve, and the panel reports this
rather than failing. **Were `llm.py` editable, the correct design would be to
persist the passage text at generation time**, which would remove the recovery
step and the possibility of an unrecoverable reference entirely.

## 5. Revision mode

**What it does.** Identifies the concepts the learner has most often answered
incorrectly — across every story and topic, ranked by lowest mastery — groups
them by topic, and offers to begin a story on the topic in which they will be
revisited.

**Requirement.** FR-15 (cross-session personalisation), surfaced to the learner.

**Implementation.** `backend/core/api_revision.py`,
`frontend/src/pages/RevisePage.jsx`, `frontend/src/styles/study.css`. Served at
`GET /api/me/weak-concepts`.

**Data read.** `ConceptStat` and `Session`.

**Data written.** None by the feature itself. This is verified by a test that
records points, difficulty, streak and every `ConceptStat` row before and after
the revision surface is exercised, and asserts they are unchanged.

**Limitations, and an honest statement of the mechanism.** Revision mode selects
what to study; it does not implement a distinct pedagogy. The emphasis mechanism
is pre-existing: `views.create_session` and `views.next_chapter` already call
`personalization.weak_concepts()` and pass the result to the generator, so a
story begun on a topic the learner is weak at is already a targeted story. The
feature therefore issues exactly the request the home page issues, and the page
says so in plain terms rather than implying a separate mode. The number of
concepts a story revisits is bounded by `personalization.REVISIT_LIMIT`, which
the interface reads rather than restates. A concept leaves the list once the
learner stops answering it incorrectly; the list cannot distinguish a concept
never attempted from one always answered correctly, since neither is weak.

## 6. Story export

**What it does.** Produces a complete, self-contained printable document for a
story: title, grade, learner name and date; every chapter with its paragraphs and
textbook citation; every question with its four options, the correct answer and
the learner's own answer marked; points and badges; and a footer naming the
source textbook and grade.

**Requirement.** Supports NFR-04 (usability under intermittent connectivity). The
deployment context is the justification: a learner retains the story offline and
a teacher can print it for classroom use.

**Implementation.** `frontend/src/utils/exportStory.js`, reached from
`frontend/src/components/ReaderToolbar.jsx`.

**Data read.** `GET /api/sessions/<id>`, fetched on demand, or the already-loaded
story when the calling page has one.

**Data written.** None.

**Limitations.** The document is rendered into a hidden same-origin frame and
printed from there, rather than by generating a PDF file directly; the learner
therefore obtains a PDF through the browser's own print dialogue. No dependency
was added — an alternative implementation using a PDF library was considered and
rejected on size grounds. The document was verified to contain both chapters,
three marked answers, five page citations and its print stylesheet, at 8,965
characters for a two-chapter story.

## 7. Read-aloud

**What it does.** Reads the current chapter aloud through the browser's speech
synthesis engine, paragraph by paragraph, highlighting the paragraph being
spoken, with play, pause, resume and stop controls whose labels reflect the
engine's actual state rather than an assumed one.

**Requirement.** NFR-05 (accessibility). The justification is specific to the
setting: the learners are studying science in a second language, and hearing the
text alongside reading it supports comprehension.

**Implementation.** `frontend/src/hooks/useReadAloud.js`, reached from
`frontend/src/components/ReaderToolbar.jsx`.

**Data read.** The chapter paragraphs already in the page. No network access.

**Data written.** None.

**Limitations.** Where the browser exposes no speech engine the controls are not
rendered at all, silently. Speech is cancelled when the component unmounts and
when the chapter changes, so it cannot outlive the text it is reading. Long
paragraphs are spoken in chunks and chained, because single long utterances are
unreliable in several browsers. The paragraph highlight is available in the
interactive reader only; the read-only replay renders every chapter at once and
has no single current paragraph. Voice availability is a property of the host
system: on a machine with no installed voices the controls operate and the engine
accepts the utterances, but no audio is produced.

## 8. Disclosure of fallback generation

**What it does.** Detects a chapter that was served from canned standby content
rather than generated from the textbook, tells the learner so in non-alarming
terms, offers another attempt, and records the occurrence for later review.

**Requirement.** Remedies a defect identified by the evaluation programme:
when generation fails schema validation twice the system returns a canned chapter
so that the learner is never blocked — correct behaviour, retained — but did so
silently, with no page references and no indication that anything had occurred.
The measured rate was 2.8% of chapters.

**Implementation.** `backend/core/api_fallback.py`,
`frontend/src/components/FallbackNotice.jsx`,
`frontend/src/styles/robustness.css`, the `GenerationEvent` model and migration
`0007`, and a single call site in `views._persist_chapter`. Served at
`GET /api/chapters/<id>/generation-status` and
`POST /api/sessions/<id>/chapters/<id>/retry`.

**Data read.** `Chapter.sources` and the mock-mode configuration flag.

**Data written.** One `GenerationEvent` row per chapter that fell back, created
idempotently, and one per retry outcome. The retry, when accepted, rewrites that
chapter's title, paragraphs, summary, sources and questions. It does not alter
points, difficulty, the streak, the chapter count, the session plan, the
chapter's position, the difficulty it was generated at, or concept mastery.

**Limitations, and a design constraint.** The detection is an *inference from an
absence*: a chapter carrying no source references is taken to be a fallback,
because the generator itself could not be modified to report the fact. This
inference is sound only when the system is generating for real — in mock mode
every chapter legitimately has no sources — so the detection is suppressed when
mock mode is active. This qualification is load-bearing rather than incidental:
without it the notice would appear on every chapter of every offline
demonstration and the entire test suite would fail. A test asserts the
suppression directly. Retry is refused if the chapter did not fall back, if the
story has finished, or if any question in the chapter has been answered, so no
recorded answer can be discarded; a retry that falls back again keeps the
original chapter rather than exchanging one canned chapter for another.
**Were `llm.py` editable, the generator would report the fallback as a fact and
it would be stored in a column**, which would remove both the inference and the
need for the mock-mode qualification.

## 9. Loading and error states

**What it does.** Provides a shared vocabulary of interface states — skeleton
placeholders, a spinner, an empty state and a dismissible toast — and applies it
to every asynchronous view added in this phase, so that no failure is silent and
no wait is unexplained. A failed load is distinguished from an absence of data,
which are otherwise easy to confuse: a learner whose progress request fails is
told the request failed, not that they have made no progress.

**Requirement.** NFR-04 (usability).

**Implementation.** `frontend/src/components/ui.jsx` and the additions to
`frontend/src/styles.css`, applied throughout the pages listed above.

**Data read and written.** None.

**Limitations.** The pre-existing generation animation is deliberately untouched.
The vocabulary is intentionally thin: each component wraps class names that
already existed, so the visual language of the application is unchanged.

## 10. Achievements

**What it does.** Presents the badge gallery — badges earned, with the date they
were first earned, alongside badges not yet earned with their criteria stated —
together with the current and best answer streaks and lifetime totals.

**Requirement.** FR-14 (gamification), surfaced across sessions rather than
within one.

**Implementation.** `backend/core/api_achievements.py`,
`frontend/src/pages/AchievementsPage.jsx`. Served at `GET /api/me/achievements`.

**Data read.** `Badge`, `Session`, `Chapter` and `Question`.

**Data written.** None.

**Limitations.** Badge criteria are read from `gamification.py` rather than
restated, so the gallery cannot advertise a rule the awarding logic does not
apply. Two defects in the awarding rules were corrected after the feature was
first built: a badge was checked only against the current session, so returning
to a topic earned its badge again on every run, and completing a story awarded
its topic badge even when the learner had answered nothing in it. Badges are now
earned once per learner — compared case-insensitively, matching the rule the
system already uses to decide whether two topic strings are the same topic — and
the topic badge additionally requires at least one answered question. The
endpoint also collapses duplicate rows created before that change, so a database
carrying them still presents one badge per achievement; `manage.py dedupe_badges`
removes them from the data. Two badges have fixed names and can therefore be shown as unearned; the
third, awarded once per topic completed, has no fixed list and is presented as a
family with its criterion stated once. Best streak is *derived* rather than
stored, since the data model retains only the streak currently in progress: it is
recovered by walking a session's answered questions in presentation order. Both
streaks are scoped to a single story, because a streak is reset by a wrong answer
and does not carry between stories; the response states this definition rather
than leaving it to be inferred.

---

## Verification

All ten features were exercised in a browser against a live backend, not merely
compiled. The backend endpoints were additionally exercised over HTTP with a
token, without a token, and with a second learner's token, confirming that each
requires authentication and returns 404 rather than another learner's data.

The test suite grew from 27 tests to 46: the 27 pre-existing tests are unmodified
and pass, one end-to-end test exercises the complete pre-existing learner journey
through the API as a regression gate, and 18 cover the new endpoints —
authentication, cross-learner isolation, response shape, empty-state behaviour,
the mock-mode suppression of fallback detection, and the assertion that the
revision surface writes nothing.

## Constraints observed

* `retrieval.py`, `planning.py`, `adaptation.py` and `llm.py` are byte-identical
  to the branch point.
* No tuned constant was altered.
* The one migration added, `0007_generationevent`, creates a new model and
  removes or repurposes nothing; it is reversible.
* `makemigrations --check` reports no drift.
