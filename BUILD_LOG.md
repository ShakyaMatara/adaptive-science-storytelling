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
