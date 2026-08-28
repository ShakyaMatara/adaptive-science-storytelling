# Build log — user-facing capability expansion

Branch `feature-expansion`, cut from `evaluation-harness` at `a37b6a9`.

One entry per phase: what was done, what passed, what failed, and the choice taken
wherever the brief left one open.

---

## Phase 0 — Survey and decide

**Done.** Read `models.py`, `views.py`, `serializers.py`, `urls.py`, `App.jsx`,
`api.js`, `styles.css`, the `frontend/src/` layout, `textbook_toc.md`,
`retrieval.py`, `planning.py`, `adaptation.py`, `llm.py`, `gamification.py`,
`personalization.py`, `constants.py`, `throttles.py`, `settings.py` and
`tests.py`. Inspected the live development database and the built Chroma index
directly. Wrote `PHASE0_SURVEY.md`.

**Passed.** Baseline `python manage.py test core` → 27 tests, OK.
`npm run build` → exit 0. `makemigrations --check --dry-run` → no changes
detected.

**Failed.** Nothing.

**Decisions taken.**

1. *`Chapter.sources` stores page references only, not passage text.* Verified in
   `llm._passage_refs()` and against the stored rows in `db.sqlite3`. Took the
   re-retrieve branch: the provenance viewer recovers text read-only at display
   time and caches it per chapter in memory. No migration to persist text; no
   change to `llm.py`.
2. *Provenance recovery uses two read-only paths.* `retrieval.retrieve()` is the
   primary path named in the brief; `retrieval.get_collection().get(where=…)` is
   an exact fallback on `(source_file, page)` for references the semantic query
   does not return. Needed because the persisted references came from the
   planner's wider `k=40` sweep.
3. *The fallback-disclosure signal must be suppressed in mock mode.* Every mock
   chapter is created with `sources = []`, so the "zero sources" test would
   otherwise fire on every offline chapter and throughout the test suite.
4. *The progress endpoint already exists* (`GET /api/me/progress`) and is covered
   by an existing test. It will be extended in place at the same URL rather than
   duplicated, keeping the `progress` key's shape so the existing test stays
   green as evidence of no behavioural change.
5. *The frontend has no router* — routing is introduced from scratch in Phase 1.
6. *The shared-file protocol is widened* from the three files the brief names to
   six, adding `backend/core/views.py`, `backend/core/serializers.py` and
   `backend/core/models.py`. The fallback disclosure has to touch the view or
   serialiser layer and adds a model, and the progress extension touches
   `views.py`; making all six orchestrator-merged keeps the parallel lanes
   collision-free.

---

## Phase 1 — Navigation shell

**Done.**

* Added `react-router-dom` 6.30 and wrapped the app in a `BrowserRouter`
  (`main.jsx`). Seven routes: `/`, `/browse`, `/library`, `/progress`,
  `/revise`, `/achievements`, `/story/:id`, with an unknown path redirecting to
  `/`.
* Built a persistent, responsive top navigation bar
  (`components/NavBar.jsx`): brand, the six section links, the learner's display
  name and a log-out control. Below 860 px the links collapse behind a menu
  button. It is rendered only inside the authenticated branch of `App.jsx`, so
  the login screen keeps its original plain layout.
* Extracted the story-reading UI from `App.jsx` into
  `components/StoryReader.jsx` as a pure refactor — markup, class names and
  render order are unchanged. The small parts it contained (`StatusBar`,
  `DifficultyDots`, `BadgeList`, `SourceNote`, `QuestionBlock`, `QnAPanel`,
  `optionClass`) are exported so the later pages can reuse them. The generation
  loader moved unchanged to `components/Loading.jsx`; the login form to
  `components/AuthScreen.jsx`.
* Lifted the live story state and its four handlers out of `App.jsx` into a
  `SessionProvider` context (`session.jsx`). The state variables, the update
  order inside each handler and the request payloads are those that were in
  `App.jsx`; only their location changed.
* Rewrote `api.js` around a single alphabetical list of endpoint wrappers, with
  the convention documented in a header comment. Added `getSession()`.
* Added the shared component vocabulary in `components/ui.jsx`: `Card`,
  `Button`, `Spinner`, `EmptyState`, `Toast`, `ProgressBar`, `SkeletonBlock`
  (plus `SkeletonLines` and a `useToast` hook). These wrap class names that
  already existed; no visual redesign.
* `App.jsx` fell from 702 lines to 121.

**Passed.** Regression gate, all four parts:

1. `python manage.py test core` → **28 tests, OK** (27 existing + the new smoke
   test).
2. `npm run build` → exit 0, 49 modules.
3. New `EndToEndSmokeTests.test_full_journey_through_the_api` exercises
   register → start → read the full session → answer → next chapter → ask →
   resume → finish, entirely over HTTP with a real token.
4. `git diff --stat a37b6a9 -- retrieval.py planning.py adaptation.py llm.py` →
   empty.

Verified **in the browser** against the live backend, not by compilation: all
seven routes render; the navigation bar highlights the active section; a Grade 6
"Magnets" story generated, rendered with its textbook citation
("Based on: Grade 6 textbook (p. 12, pp. 99-101, pp. 101-102)") and three
questions; answering the first question returned "Correct! You earned 30 points."
and the points pill updated; `/story/1` renders the read-only replay of the
existing completed story with its badges and answer key.

**Failed.** Nothing. The gate passed at the first attempt, so the Phase 1
fallback (building the new pages inside the old `App.jsx`) was not needed and
`PHASE1_ISSUES.md` was not written.

**Decisions taken.**

1. *A read-only story replay was added* (`components/StoryArchive.jsx`).
   `/story/:id` needs to answer for an id that is not the story held in memory —
   after a reload, from a bookmark, or from "read again" in My Stories. Rather
   than rehydrating an interactive session from the server (which would risk
   diverging from the answer-submission path), the route falls back to a printed
   replay built from `GET /api/sessions/<id>`, which the API already served. This
   also gives the export feature a complete story to work from.
2. *Errors moved from an inline banner to the shared toast.* The old start screen
   printed errors in a `.banner-error`; the routed app raises them through one
   `Toast` mounted beside the routes, pinned until dismissed. One mechanism for
   every page is what the later loading-and-error work asks for, and the
   syllabus-gate refusal keeps its full wording.
3. *`/progress` was given the real progress screen rather than a placeholder.*
   It already existed and worked; leaving it live means no existing capability
   regressed during the refactor.
4. *Per-lane stylesheets.* `styles.css` received the shell's own rules in this
   phase, but each later lane writes its page rules to its own file under
   `frontend/src/styles/` and imports it from its page. `styles.css` is a shared
   file in all but name and four concurrent lanes would collide in it.

---

## Phase 2 (setup) — contracts fixed before the lanes started

Four lanes were to run concurrently in one working tree, so the shared surface was
settled first and committed on its own
(`Wire the routes and API client for the feature lanes, with placeholder handlers`).

**Done.**

* All eight new backend routes were added to `urls.py` up front, each pointing at
  a placeholder module the owning lane then replaces wholesale:
  `GET /api/curriculum`, `GET /api/me/library`, `GET /api/me/weak-concepts`,
  `GET /api/me/achievements`, `GET /api/chapters/<id>/provenance`,
  `GET /api/chapters/<id>/generation-status`,
  `POST /api/sessions/<id>/chapters/<id>/retry`, and `GET /api/me/progress`
  re-pointed from `views.me_progress` to `api_progress.me_progress`.
* The matching client functions were added to `api.js` in the alphabetical
  positions the file's convention dictates.
* `api_progress.py` was created as a one-line delegation to the original view, so
  re-pointing the URL changed nothing and the existing progress test kept passing
  while the extension was written.
* `_integration/` directories and `frontend/src/styles/` were created.

**Passed.** `manage.py test core` → 28, OK. All eight routes answered over HTTP
with a real token before any lane started.

**Decisions taken.**

1. *The shared surface was pre-wired rather than merged at the end.* The brief
   has each lane write its route and client additions into a handoff for the
   orchestrator to merge afterwards. Deciding the eight endpoint contracts in
   advance and wiring them to placeholders achieves the same collision-free
   result and buys something the handoff-only approach cannot: every lane can
   exercise its own endpoint over real HTTP and see its own page at its real
   route while building it, instead of waiting for integration to find out
   whether it works. The handoff protocol still stands for everything else, and
   for any endpoint a lane finds it additionally needs.
2. *Per-lane stylesheets under `frontend/src/styles/`.* `styles.css` is shared in
   all but name.
3. *`models.py` and `migrations/` were assigned exclusively to Lane D*, the only
   lane that needs to persist anything (the record of a served fallback). The
   other three were told the file is off limits.
4. *The loading-and-error requirement was made every lane's responsibility rather
   than one lane's.* Skeletons and toasts have to appear inside pages that other
   lanes own, so a single lane could not deliver it without breaking file
   ownership. The shared vocabulary was built in Phase 1 and every lane brief
   requires its use; the orchestrator audits compliance in Phase 4.

---

## Phase 2 — Feature lanes

Four lanes ran concurrently in one working tree, each owning its files
exclusively and writing its shared-file requests to a handoff.

**Lane A — Discovery. Completed by the lane.** Syllabus browser
(`api_curriculum.py`, `BrowsePage.jsx`) and My Stories (`api_library.py`,
`LibraryPage.jsx`). The contents-page parser was checked against the source
file: 64 chapters and 228 sub-sections across the four grades, with Grade 9
correctly presented as one continuous list of chapters 1-19 spanning its two
printed parts. The library endpoint costs four queries regardless of how many
stories a learner has, measured rather than assumed.

**Lane B — Learner insight. Completed by the lane.** Extended progress endpoint
(`api_progress.py`, `ProgressPage.jsx`) and the provenance viewer
(`api_provenance.py`, `ProvenancePanel.jsx`). The original `progress` key was
shown to be byte-identical to the pre-change response. Provenance recovered 3 of
3 references for chapter 1 and 2 of 2 for chapter 2, all by the semantic path;
the exact-lookup fallback and the index-unavailable path were exercised
deliberately, since live data never reaches them.

**Lane C — Study tools. Files delivered; the lane was cut short.** Revision mode
(`api_revision.py`, `RevisePage.jsx`), export (`exportStory.js`), read-aloud
(`useReadAloud.js`) and the mountable `ReaderToolbar.jsx` were all written and
its handoffs recorded before the lane stopped partway through its final
verification. Its own handoff warned that a temporary verification harness in
`RevisePage.jsx` might not have been removed; it had not been, and it was
removed during integration. The remaining verification was completed by the
orchestrator.

**Lane D — Robustness. The lane produced nothing and the work was done by the
orchestrator.** The lane stalled without writing a file. Rather than restart it,
the orchestrator built D1, D2 and D3 directly: `GenerationEvent` and migration
`0007`, `api_fallback.py`, `api_achievements.py`, `FallbackNotice.jsx`,
`AchievementsPage.jsx` and `robustness.css`.

**Passed.** Every endpoint answered over real HTTP with a token, refused an
unauthenticated request with 401, and returned 404 for another learner's data.

**Decisions taken.**

1. *The fallback detection is suppressed in mock mode, and this is load-bearing.*
   Demonstrated directly: with an empty `sources` list, the predicate returns
   `False` with mock mode on and `True` with it off. Without the guard the notice
   would fire on every chapter of every offline demonstration and the whole test
   suite would fail. There is now a test asserting exactly this.
2. *Retry regenerates at `chapter.difficulty_at_time`, not `session.difficulty`.*
   The chapter is replaced in place, so it must stay consistent with the
   difficulty already stored on the row.
3. *Retry is refused outright once any question in the chapter has been answered*,
   so a recorded answer can never be discarded.
4. *A retry that falls back again keeps the original chapter* rather than
   swapping one canned chapter for another, and says so plainly.
5. *Best streak is derived, not stored.* `Session.current_streak` holds only the
   run in progress, so the best run is recovered by walking a session's answered
   questions in presentation order. The definition is returned in the payload
   rather than left implicit.

---

## Phase 3 — Integration

**Done.** Merged all eight handoffs into `views.py`, `StoryPage.jsx` and
`StoryArchive.jsx`; the pre-wired routes and client functions meant `urls.py` and
`api.js` needed nothing further. Removed Lane C's temporary harness. Deleted both
`_integration` directories. Added 18 functional tests for the new endpoints.

**Passed.** `manage.py test core` → **46 tests, OK** (27 original + the smoke
test + 18 new, against a target of 12). `npm run build` → exit 0, 58 modules.
`makemigrations --check --dry-run` → no changes detected. The four frozen modules
are byte-identical to the branch point and no frozen constant was altered.

**Failed, and fixed.** Wiring `record_fallback_if_needed` into `views.py`
introduced a circular import — `views` imported `api_fallback`, which imported
`views` for `_chapter_kwargs` — which took the development server down. The
import in `api_fallback` was deferred into the function that needs it. This is
exactly the class of defect the integration step exists to catch: each lane's
module imported cleanly on its own.

**Decisions taken.**

1. *Arbitration between Lanes B and C over the reader's `activeParagraph` prop.*
   Both claimed it — B to mark a clicked paragraph, C to mark the paragraph being
   spoken. `activeParagraph` was given to read-aloud, because a moving highlight
   most naturally means "this is being read now", and the click was left to open
   the provenance panel only. Nothing is lost: provenance is recorded per
   chapter, not per paragraph, so which paragraph was clicked does not change
   what the panel shows.
2. *The fallback notice is mounted in the read-only replay as well as the live
   reader*, per chapter, so a story reread later still discloses which of its
   chapters were not textbook-grounded.
3. *The toolbar in the replay is passed the already-loaded story*, so export
   there costs no second request.

**Verified in the browser** against the live backend: the read-only replay showed
the listening and export controls, the disclosure notice and its honest blocked
reason ("You have already answered a question in this chapter") together on one
page; the live reader showed the toolbar, the citation line
("Based on: Grade 6 textbook (p. 12, pp. 99-101, pp. 101-102)"), no notice for a
grounded chapter, and clicking a paragraph opened the provenance panel
(`role="dialog"`, `aria-modal="true"`) containing the textbook's own wording.

**Throwaway data removed.** A session, chapter, question and two generation
events were created to exercise the fallback and retry paths, including one real
regeneration that produced a genuine textbook-grounded chapter with four page
citations. All of it was deleted afterwards; the database is back to the two real
stories.

---

## Phase 4 — Review and documentation

### Simplification pass

Four reviews were run over the new code — reuse, simplification, efficiency and
altitude — and their findings deduplicated. What was acted on, and what was
declined, is recorded here because the split matters for the write-up.

**Fixed — measured effects.**

* *Achievements did one query per session.* `_best_streak_in` re-queried the
  learner's questions for every session even though the caller had already
  prefetched them, and two aggregate counts re-joined the same three tables. Both
  now read the prefetched rows in one pass. **9 queries falling to 5, and flat
  in the number of stories rather than 7 + N** — 47 queries at forty stories
  before, 5 after.
* *The read-only replay issued one HTTP request per chapter.* `FallbackNotice`
  asked the server about each chapter's grounding, even though the page had
  already loaded every chapter. `used_fallback` and `can_retry` now travel with
  the chapter on `ChapterSerializer`, and the notice accepts them as a prop.
  **Confirmed in the server log: opening a two-chapter story now makes one
  request where it previously made three.** This matters specifically because the
  deployment context is intermittent connectivity.
* *The progress endpoint counted the same queryset twice* (7 → 6 queries) and
  *pulled every chapter's full prose back to count chapters*; the text columns are
  now deferred. At forty stories that was roughly 450 kB of story text fetched to
  produce one integer.
* *Revision ran a query per session inside a loop* to test for chapters; it is now
  a single annotation (4 → 3 queries).
* *The provenance cache could grow without bound* — every chapter any learner ever
  opened stayed resident for the life of the process at several kilobytes each. It
  is now an LRU bounded at 256 chapters. The cache itself is well justified and was
  kept: 1,020 ms cold against 1.0 ms warm.

**Fixed — defects the reviews surfaced.**

* *`useToast` returned fresh callbacks on every render*, and `Toast` lists
  `onDismiss` among its effect dependencies, so the dismissal timer was cleared
  and restarted on every render — a page re-rendering faster than the timeout
  would never have dismissed its toast at all. Both callbacks and the returned
  object are now stable.
* *The retry path did not restart the response-time clock.* The chapter swap was
  performed through a generic `patch` escape hatch that reimplemented — and had
  already drifted from — the transition `next` performs, so answers to a
  regenerated chapter would have been timed from the previous chapter's load and
  recorded a wrong `response_time_ms`. Replaced with a named `replaceChapter`
  action on the session, and `patch` removed.
* *Half the mastery bars on the progress dashboard were not announced.* The
  per-concept bars were hand-written markup while the per-topic bars used the
  shared component; the concept bars now use it too and carry a
  `role="progressbar"` with a label. Verified: 5 of 5 bars labelled.
* *A human-readable sentence was being used as a wire value.* Provenance returned
  `"semantic match"` / `"exact lookup"` and the panel compared against those
  strings, so a copy edit on the server would have silently flipped every passage
  into the wrong branch. Now stable `"semantic"` / `"exact"` tokens, with the
  wording owned by the component that renders it.

**Fixed — dead and duplicated code.**

* `views.me_progress` deleted: unrouted since the URL was re-pointed, and its two
  copies had already diverged (the old one created a `Learner` row on a GET; the
  new one deliberately does not).
* The reflection over `personalization.weak_concepts`'s signature is gone,
  replaced by a named `REVISIT_LIMIT` constant where the rule lives. The
  reflection's own fallback re-hardcoded the literal it existed to avoid.
* A redundant ownership join in the library query that could never exclude a row.
* An unreachable `toolbar` slot on the read-only replay.
* The panel's bespoke error box, which restated the shared error banner.
* The mastery chart is memoised; it was fully rebuilt whenever a toast appeared or
  the textbook panel opened or closed.
* The curriculum tree (~35 kB) and the fixed topic list are now held after their
  first fetch instead of being re-downloaded on every visit, and cleared on log
  out. The profile is no longer re-fetched immediately after logging in, which
  already returns it.

**Declined, with reasons.**

* *One shared data-fetching hook to replace seven near-identical effects.* A real
  duplication, but it touches eight files at the end of the phase, and two of the
  seven have genuinely different behaviour. The regression risk outweighs the
  tidiness now; recorded as future work.
* *One shared `lifetime_totals(learner)` for the counters computed in both the
  progress and achievements endpoints.* The right change, and a genuine artefact
  of parallel development — but it alters two response-shaping paths at once. The
  N+1 fix already removed the expensive half of the problem.
* *Consolidating the pill and stat-tile CSS across the lane stylesheets.* Visual
  regression risk across four pages for no functional gain.
* *Extracting a shared `ChapterBody` used by both reading surfaces.* Correct in
  principle and the sharpest altitude finding, but a structural refactor of the
  reading experience is not a Phase 4 change.
* *Consolidating `pct`/`formatDate` helpers across pages.* Partially addressed via
  the shared bar; the rest is churn.
* Suggestions to remove explanatory comments were declined outright: the prose is
  part of the deliverable.

**One review claim was wrong and is worth noting**: the efficiency review reported
`api_library` at "5 queries, not the 4 the comment claims". The comment describes
the summarising path, which is 4; the fifth is the learner lookup that precedes
it. The comment is accurate and was left alone.

**Passed after the pass.** 46 tests OK, build exit 0, no migration drift, the four
frozen modules still byte-identical.

### Manual verification pass

Every one of the ten features was exercised in a browser against the live
backend. Evidence, feature by feature:

| Feature | What was observed |
|---|---|
| Syllabus browser | Tree renders with page badges; searching "photosynth" reported "1 chapter and 1 sub-section match"; selecting `11.1 Photosynthesis pp. 46–50` arrived at the start flow with the topic and Grade 8 filled in |
| Story library | Grade filters offered only the grades the learner owns; Resume opened the live reader at `/story/2`; Read again opened the replay |
| Progress dashboard | Eight counters, the mastery-against-practice plot, per-topic bars, and a revision link on every concept |
| Provenance viewer | `role="dialog"`, `aria-modal="true"`, containing the textbook's own wording cited to its printed page |
| Revision mode | Two concepts across one topic, weakest first |
| Story export | An 8,965-character document containing both chapters, three marked answers, five citations and its print stylesheet — inspected without opening a print dialogue |
| Read-aloud | Engine reported speaking; controls tracked its real state through Listen, Pause, Resume and Stop; paragraph 0 of 4 highlighted while spoken |
| Fallback disclosure | Notice rendered above a fallback chapter with its retry blocked and the reason given; all three guards refused correctly |
| Loading and error states | Skeletons and toasts on every asynchronous view |
| Achievements | Earned badges dated, "On Fire" shown unearned with its criterion, streaks and totals |

Two honest qualifications. Read-aloud does not highlight in the read-only replay,
which renders every chapter at once and has no current paragraph — a deliberate
choice, not a defect. The verification machine has no speech voices installed, so
the engine was observed accepting and tracking utterances but no audio was heard;
audio output on a device with voices remains unverified.

### Documentation

`FEATURES_ADDED.md` written: ten entries, each recording the feature, its
requirement, its files, what it reads, what it writes and its limitations, in
formal impersonal prose. Two entries state explicitly what the implementation
depth would have been had the frozen modules been editable — persisting passage
text for provenance, and reporting the fallback as a fact rather than inferring
it from an absence — since that distinction belongs in the evaluation chapter.

### Screenshot checklist

The sequence below is ordered as a demonstration, so the same run produces both
the thesis figures and the live walk-through. Sign in beforehand; the account
needs at least one completed story and one story in progress, and at least one
concept answered incorrectly, or the insight screens will be empty. Capture at a
desktop width, then repeat the starred items at 375 px to evidence the responsive
layout.

1. **Login screen** — the unauthenticated state, with no navigation bar.
2. **Home** — the topic field, suggestion chips and grade selector.
3. **Syllabus browser, collapsed*** — the four grades with their chapter and
   sub-section counts. *The single most important figure of the phase: it is the
   evidence that grounding is curricular rather than asserted.*
4. **Syllabus browser, one grade expanded** — chapters with page ranges, one
   chapter expanded to its sub-sections.
5. **Syllabus browser, searching** — a term such as "magnet", showing the match
   count, the filtered tree and the highlighted matches.
6. **Home, pre-filled from the syllabus** — topic and grade carried over. Capture
   immediately after step 5 so the hand-off is visible as a pair.
7. **Generation in progress** — the loading animation with its cycling message.
8. **Story reader** — chapter title, prose, the "Based on: Grade N textbook"
   citation line, the listening and export controls, and the questions.
9. **A question answered** — the correct option green, the feedback line, the
   points pill updated.
10. **Provenance panel open*** — triggered by selecting a paragraph. Ensure the
    textbook extract, its page citation and the "printed exactly as it appears"
    label are all legible. *The second headline figure.*
11. **Read-aloud active** — the highlighted paragraph with the Pause control
    showing, so the highlight and the control state appear together.
12. **Grounded Q&A panel** — a question answered from the textbook, with sources.
13. **Q&A refusal** — a question too close to an unanswered quiz question, showing
    the anti-cheat refusal.
14. **Chapter complete** — the continue control and any badge notification.
15. **Session complete** — final points and badges.
16. **My Stories*** — the card grid with both filters visible, one story in
    progress and one complete.
17. **Read-only replay** — a completed story with the answer key shown.
18. **Print preview of the export** — the browser's own preview, showing the
    chapters, questions, citations and the source-textbook footer.
19. **Progress dashboard, upper*** — the headline counters and the
    mastery-against-practice plot.
20. **Progress dashboard, lower** — mastery bars by topic and the strengths and
    gaps panel.
21. **Revision page** — weak concepts ranked with their mastery, and the
    explanatory copy stating what revision does.
22. **Achievements** — earned badges with dates beside an unearned badge showing
    its criterion, plus streaks and totals.
23. **Fallback disclosure notice** — above a chapter with no textbook grounding,
    with the retry control. Hard to obtain naturally at a 2.8% rate; it can be
    staged by clearing one chapter's stored references in a scratch database.
24. **An empty state** — any insight page for a newly registered learner, to show
    the system invites a first story rather than presenting an empty grid.
25. **Navigation bar collapsed*** — the mobile menu open, evidencing the
    responsive shell.

Figures 3, 10 and 19 are the three that carry the phase's argument: curriculum
made navigable, grounding made inspectable, and learning made measurable.

---

## Post-review defect fix — badge awarding

Two defects reported from use, both in `gamification.py` (which is not one of the
frozen modules, so the rules themselves could be corrected rather than worked
around).

**Defect 1 — a badge was re-earned on every run.** `award_badges` checked
`session.badges`, the badges of the *current* session, so a returning learner
started every story with an empty badge set and earned everything again. A
learner who completed the water cycle three times collected three "Water Cycle
Explorer" badges, and "First Steps" — nominally the first correct answer they
ever gave — was re-earned once per story. The check now spans every session the
learner has ever run.

Topic names are free text, so the comparison is case-insensitive: "water cycle"
and "Water Cycle" are one topic for this purpose, matching the `topic__iexact`
rule `create_session` already uses when deciding whether to resume. The badge
keeps whichever spelling was earned first rather than being rewritten.

*Deliberately not done:* fuzzy matching of similar-but-not-identical topics
("Water Cycle" against "The Water Cycle"). It would risk suppressing a genuinely
different topic, and exact-ignoring-case is the identity rule the rest of the
system already applies to topics.

**Defect 2 — completing a story earned its badge with no work done.**
`finish_session` ends a story at any point and awarded the explorer badge purely
on completion, so starting a story and immediately ending it earned one. The
badge now additionally requires at least one answered question in that session.
The bar is engagement, not correctness — a wrong answer still counts — because
"Explorer" marks having worked through the topic, which is what "First Steps"
and "On Fire" measure the quality of.

**Consequential fix — the gallery mis-rendered existing duplicates.** The
achievements endpoint listed one tile per badge *row*, so a duplicated badge
produced two tiles sharing a React key. Rows created before the rule was enforced
still exist in any database that ran the old code, so the endpoint now collapses
badges to one entry per distinct name, keeping the earliest award, and
`badges_earned` counts distinct badges. Verified against a database still holding
the duplicates: five rows, correctly presented as three badges.

**Passed.** 52 tests (46 + 6 new), build exit 0, no migration drift, frozen
modules still byte-identical.

**The regression tests were verified to fail without the fix.** Running the six
new tests against the original `gamification.py` produces four failures, each
reproducing a reported symptom exactly — `['Water Cycle Explorer']` awarded for a
story with nothing answered; the same badge awarded a second time on a replay;
`'water cycle Explorer'` created as a badge distinct from `'Water Cycle
Explorer'`; and `'First Steps'` earned again in a second story. The remaining two
tests pass both before and after, and exist to catch over-correction: a genuinely
different topic must still earn its own badge, and one answer must still be
enough.

**Not done: existing duplicate rows are not cleaned up.** The fix prevents new
duplicates; it does not delete the ones already awarded. The gallery presents
them correctly regardless, so this is cosmetic in the database rather than in the
interface, and deleting a learner's badge history is not a change to make
unprompted.

---

## Post-review change — syllabus placement for freely-typed topics

**Reported.** The progress dashboard's "Mastery by topic" listed topics as the
learner had typed them, so entries appeared that are not headings anywhere in the
syllabus. A Grade 6 story on "Light emitting diode" should read as
*8.5 Electronic Appliances*, under *8. Electricity for a Comfortable Life*.

**Done.** Topics are now resolved to a section of the printed syllabus and the
mastery list is grouped by it. The resolution is a page lookup, not a text match:
every stored source reference carries a printed page citation, and the contents
pages record where each chapter and sub-section begins, so the owning section
follows from the pages the story was actually grounded on.
`api_curriculum.locate_page()` and `place_sources()` do the lookup;
`api_progress` attaches the result to each topic; `ProgressPage` groups by it.

**Verified live, on the reported case.** A Grade 6 "Light emitting diode" story
was generated against the real model, grounded on pp. 123-125, and appears as:

```
8.5 Electronic Appliances
Grade 6 · 8. Electricity for a Comfortable Life
   Light emitting diode        (2/2 references agreed)
```

**Decisions taken.**

1. *The contents pages are the authority, not the vector index's metadata.* The
   index's own `section` labels are wrong in places — a Grade 6 chunk citing
   pp. 99-101, inside chapter 7 "Magnets", is labelled "Applications of Light",
   which is 5.5 and begins at page 78 — and some carry the placeholder
   "(document)". The page lookup corrects these rather than propagating them; the
   Magnets topic now resolves to chapter 7 as it should.
2. *A two-stage vote, chapter before sub-section.* A single vote across
   sub-sections is brittle: a water cycle story draws on 3.1, 3.5 and 9.3, so no
   sub-section holds a majority and the winner would come down to storage order.
   Voting on the chapter first raised that placement from 1 of 3 references to
   2 of 3, and made it stable.
3. *A citation equal to its own PDF page index is treated as unresolvable.* The
   citation falls back to the PDF index when a page footer could not be parsed,
   for about 11% of pages, and that is indistinguishable from a genuine folio
   except by this test. Refusing it costs the occasional real coincidence and
   avoids placing a story in the wrong section — the right trade, since a chapter
   carries several references and only needs a majority.
4. *The typed topic is never rewritten.* It is the key concept mastery, story
   resumption and badges are recorded against, so the placement annotates it. The
   learner's own wording stays visible beneath the syllabus heading.
5. *An unplaceable topic is grouped separately and labelled*, rather than being
   hidden or filed under a section it did not come from.

**Passed.** 61 tests (52 + 9 new), build exit 0, no migration drift, frozen
modules byte-identical.

**Data repair.** `manage.py dedupe_badges` added — a dry run by default, `--apply`
to delete. Run against the development database: two duplicate rows removed
("Atomic structure Explorer" and "Water Cycle Explorer", each held twice), the
earliest award of each kept so the date shown is the date it was first earned.
Three badges remain.
