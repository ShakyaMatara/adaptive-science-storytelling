# Phase 0 — Survey of the existing system

This document records the state of the codebase at the point the
`feature-expansion` branch was cut (`a37b6a9`, from `evaluation-harness`), the data
already persisted by the system, and the decisions taken where the brief left a
choice open. Every feature added in later phases is a surface over data described
here.

---

## 1. Module summary

### `backend/core/models.py`

Six models, all owned by a learner:

| Model | Purpose | Key fields |
|---|---|---|
| `Learner` | Profile, one-to-one with Django `User` | `user`, `name`, `created_at` |
| `Session` | One run-through of a topic as a multi-chapter story | `learner`, `topic`, `grade`, `difficulty`, `points`, `current_streak`, `chapter_count`, `setting`, `content_level`, `plan` (JSON), `is_complete`, `created_at` |
| `Chapter` | One titled, multi-paragraph scene | `session`, `order`, `title`, `paragraphs` (JSON list), `summary`, `difficulty_at_time`, `sources` (JSON), `created_at` |
| `Question` | One comprehension MCQ attached to a chapter | `chapter`, `order`, `question_text`, `options` (JSON, 4), `correct_index`, `hint`, `concept`, `user_answer_index`, `is_correct`, `response_time_ms`, `created_at` |
| `Badge` | A gamification milestone, scoped to a session | `session`, `name`, `awarded_at` |
| `ConceptStat` | Per-learner mastery of one concept within one topic, aggregated across all sessions | `learner`, `topic`, `concept`, `attempts`, `correct`, `last_seen`; `mastery` property |

Six migrations exist (`0001`–`0006`); `makemigrations --check --dry-run` reports
no drift at the branch point.

### `backend/core/views.py`

Function-based DRF views. Token authentication is the project default and
`IsAuthenticated` is the default permission; `register` and `login` opt out with
`AllowAny`. Endpoints that trigger a paid model call carry burst and daily
throttles.

Ownership is enforced everywhere by filtering on `learner__user=request.user`
inside `get_object_or_404`, so a cross-user request returns 404 rather than 403.

Notable helpers already present and reusable: `_persist_chapter`,
`_question_feedback`, `_chapter_is_answered`, `_answered_state` (rehydrates prior
answers when a story is resumed), `_learner_for`, and the deterministic
anti-cheat similarity gate (`SIMILARITY_THRESHOLD = 0.7`).

### `backend/core/serializers.py`

Two views of the same data. `Presented*` serialisers are the safe subset sent to
the browser while a learner is answering (no `correct_index`, `hint` or
`concept`). The full `ChapterSerializer` / `QuestionSerializer` /
`SessionSerializer` include the answer key and the learner's response, and are
used only by `GET /api/sessions/<id>`.

### `backend/core/urls.py`

Ten routes under `/api/`:

```
auth/register  auth/login  auth/me  me/progress
topics  sessions  sessions/<id>  sessions/<id>/answer
sessions/<id>/next  sessions/<id>/finish  sessions/<id>/ask
```

### `frontend/src/`

Four files only: `App.jsx` (702 lines), `api.js`, `main.jsx`, `styles.css`. No
router, no component directory, no test setup. Dependencies are React 18 and
React-DOM only; Vite 5 is the build tool.

### `backend/evaluation/probes/textbook_toc.md`

371 lines, a stable and highly regular structure:

```
## G6.pdf
1. Wonders of the Living World — 1
   1.1 Characteristics of Organisms — 6
```

Seven files map onto four grades: `G6`, `G7P1`+`G7P2`, `G8P1`+`G8P2`,
`G9P1`+`G9P2`. Chapter numbering continues across the two parts of a grade
(Grade 9 Part 2 begins at chapter 10). Every chapter and sub-section line carries
a printed start page after an em dash, so a page *range* for a sub-section can be
derived from the next sibling's start page.

---

## 2. What the system already persists

**Per learner** (`Learner`, `ConceptStat`): display name, account creation time,
and — across every session that learner has ever run — attempts and correct
counts for each `(topic, concept)` pair, with a last-seen timestamp.

**Per session** (`Session`, `Badge`): topic as free text, grade, current
difficulty, points, the live correct-answer streak, chapters generated so far,
the persistent story setting, the measured content level (`thin` / `moderate` /
`rich`), the full content plan as JSON, completion state, creation time, and the
badges earned in that session.

**Per chapter** (`Chapter`): order, title, the paragraph list, the summary
carried into the next chapter, the difficulty the chapter was generated at, and
the grounding source references.

**Per question** (`Question`): order, text, the four options, the correct index,
the hint, the concept label, and — once answered — the learner's chosen index,
whether it was correct, and the response time in milliseconds.

The plan JSON on a session is particularly rich: it holds, per planned chapter,
the section label, the grounding passages **including their text**, and the
paragraph/question ranges. It is written once at session creation.

---

## 3. CRITICAL DECISION — what `Chapter.sources` stores

**Finding: page references only. No passage text is persisted on the chapter.**

`llm._passage_refs()` builds each entry as exactly five keys and deliberately
drops the passage body:

```python
return [{
    "source_file": p.get("source_file"),
    "page": p.get("page"),
    "page_citation": _page_citation(p),
    "chapter": p.get("chapter"),
    "section": p.get("section"),
} for p in passages]
```

Verified against the live development database, where the only stored chapter
carries entries of the form:

```json
{"source_file": "G9P1.pdf", "page": 52, "page_citation": "pp. 40-41",
 "chapter": "Nature and Properties of Matter", "section": "Elements"}
```

**Branch taken: re-retrieve at display time, read-only, cached per chapter in
memory.** No migration is added to persist passage text and `llm.py` is not
modified, in accordance with the brief.

Two read-only recovery paths were confirmed to work against the built Chroma
index (1,122 chunks):

1. `retrieval.retrieve(grade, query, k=…)` — the semantic path named in the
   brief. Returns passages carrying `text` plus the same metadata keys that were
   persisted, so a returned passage can be matched to a stored reference on
   `(source_file, page)`.
2. `retrieval.get_collection().get(where=…)` — an exact metadata lookup on
   `(source_file, page)`. This resolves references the semantic query happens not
   to return, which matters because the persisted references were produced by the
   *planner's* wider sweep (`k=40`) rather than by the query used at display time.

The provenance viewer uses (1) as its primary path and (2) as an exact fallback
for any unmatched reference. Both are pure reads; neither touches
`retrieval.py`'s source, and no frozen constant is involved.

**Consequence for the fallback-disclosure feature (D1):** a chapter with an empty
`sources` list is a reliable signal of the canned fallback *in live mode only*.
In mock mode every chapter is created with `sources = []` by design, so the
detection must be suppressed when `llm_config.use_mock()` is true, or the notice
would fire on every chapter of every offline demonstration and in the whole test
suite.

---

## 4. Does a progress endpoint already exist?

**Yes.** `GET /api/me/progress` (`views.me_progress`) is live and covered by the
existing test `test_progress_endpoint_reports_mastery`. It returns concept
mastery grouped by topic and nothing else:

```json
{"progress": [{"topic": "Water Cycle",
               "concepts": [{"concept": "evaporation", "attempts": 4,
                             "correct": 3, "mastery": 0.75}]}]}
```

FR-17 is therefore partially implemented. It will be **extended, not
duplicated**: the implementation moves to `core/api_progress.py`, the URL is
re-pointed at it, and the response keeps the `progress` key with its existing
shape while gaining headline counters, strongest/weakest concepts, badge and
chapter totals. Keeping `progress` intact means the existing test continues to
pass unchanged, which is the evidence that the extension did not alter behaviour.

## 5. Frontend routing approach

**Single component with conditional rendering.** `App.jsx` holds a `screen`
state variable taking `'start' | 'story' | 'complete' | 'progress'`, plus an
implicit login screen when no token is present. There is no router and
`react-router-dom` is not a dependency. Phase 1 therefore introduces routing from
scratch rather than adapting an existing setup.

## 6. Baseline measurements

| Gate | Result at branch point |
|---|---|
| `python manage.py test core` | **27 passed**, 13.2 s |
| `npm run build` | exit 0, 32 modules, 156 kB JS |
| `makemigrations --check --dry-run` | no changes detected |
| Frozen modules | `retrieval.py`, `planning.py`, `adaptation.py`, `llm.py` unmodified |

Environment: Python 3.14.7 in `backend/venv`, Node 22.2, Django 6.0, Chroma
1.5.9. `backend/.env` is configured for live generation
(`USE_MOCK_LLM=false`) against an OpenAI-compatible proxy; the test suite forces
mock mode for itself.

---

## 7. Decisions carried into later phases

1. **Provenance** re-retrieves rather than persists (section 3).
2. **Progress** is extended in place at the same URL (section 4).
3. **Routing** is introduced with `react-router-dom` in Phase 1 (section 5).
4. **`views.py`, `serializers.py` and `models.py` join the shared-file
   protocol.** The brief names `urls.py`, `App.jsx` and `api.js`; the fallback
   disclosure feature also has to touch the view or serialiser layer and adds a
   model, and the progress extension touches `views.py`. Treating all six as
   orchestrator-merged keeps the parallel lanes collision-free.
