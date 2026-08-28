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
