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
