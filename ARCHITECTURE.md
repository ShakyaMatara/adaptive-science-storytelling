# Architecture

This document maps the **code** to the **conceptual layers** of the project, so the
implementation can be discussed against the design in the report and viva.

A session is a short, continuous, multi-**chapter** story for a logged-in learner.
Each chapter is a titled, multi-paragraph scene grounded in the learner's grade
textbook (RAG), followed by a small set of questions; difficulty adapts between
chapters and the learner's concept mastery carries across sessions.

## Conceptual layers → code

| Conceptual layer | Responsibility | Where it lives |
|---|---|---|
| **Accounts / Identity** | Register, log in, own your data | Django auth (`User`) + DRF token auth; `core/views.py` (register/login/me); `Learner` is the per-user profile |
| **Curriculum / Story Generation** | Turn topic + grade + difficulty into a grounded chapter (3 paragraphs + questions) | `core/llm.py` (`generate_chapter`, prompts, parsing, mock) + `core/mock_content.py` (canned chapters) |
| **Knowledge grounding (RAG)** | Retrieve the few most relevant textbook passages per grade+topic; gate off-syllabus topics; grounded Q&A | `core/retrieval.py` (Chroma query) + `build_index` command; gate/Q&A in `core/llm.py` |
| **Learner Model + Pedagogical Engine** | Track state, plan the story, decide how it adapts | `core/adaptation.py` (per-question scoring + per-chapter difficulty), `core/planning.py` (content-driven plan: chapter count + lengths) on `Session`/`Chapter`/`Question`; `core/personalization.py` (cross-session mastery → weak concepts + adaptive start) on `ConceptStat` |
| **Gamification** | Reward progress with points + badges | `core/gamification.py` + points/streak in `core/adaptation.py`, stored on `Session`/`Badge` |
| **Data Layer** | Persist everything for adaptation + analysis | `core/models.py` (Learner, Session, Chapter, Question, Badge, ConceptStat) on **SQLite** |
| **Presentation** | The learner-facing UI | `frontend/` — React (`src/App.jsx`, `src/api.js`, `src/styles.css`) |

## System diagram

```
        ┌──────────────────────────── Presentation (React) ───────────────────────────┐
        │  Auth screen · Start (typed topic + grade) · Story (chapter + questions +     │
        │  Ask panel) · Complete · Progress     token in localStorage; sent as          │
        │  Authorization: Token <key> on every request                                  │
        └───────────────▲──────────────────────────────────────────────┬───────────────┘
                        │  JSON over fetch (CORS)                        │
                        ▼                                                ▼
        ┌──────────────────────────────── Django REST API ─────────────────────────────┐
        │  core/urls.py → core/views.py   (TokenAuth + IsAuthenticated by default)       │
        │  auth: register / login / me        sessions: create / answer / next / ask     │
        │                                                                                │
        │   ┌─ Story Gen + RAG ─┐  ┌─ Pedagogical Engine ─┐  ┌─ Personalisation ─┐       │
        │   │ llm.generate_     │  │ adaptation.py        │  │ personalization.py │       │
        │   │  chapter / answer_│  │ (points; per-chapter │  │ (weak concepts;    │       │
        │   │  question         │  │  difficulty)         │  │  adaptive start)   │       │
        │   │ retrieval.retrieve│  └──────────┬───────────┘  └─────────┬──────────┘       │
        │   └─────────┬─────────┘             │     ┌─ Gamification ─┐ │                  │
        │             │                       │     │ gamification.py│ │                  │
        │             ▼                       ▼     └───────┬────────┘ ▼                  │
        │        ┌──────────────────────── Data Layer ──────────────────────┐            │
        │        │ models.py + SQLite:  Learner · Session · Chapter ·        │            │
        │        │ Question · Badge · ConceptStat                            │            │
        │        └────────────────────────────────────────────────────────────┘          │
        └───────────────┬───────────────────────────────────────────────┬───────────────┘
                        ▼ (USE_MOCK_LLM=false, server-side only)          ▼
                  OpenRouter API (chat)                          Chroma vector store
                                                                 (local, backend/chroma_store)
```

The OpenRouter API key lives in `backend/.env` and is used **only on the server**;
it never reaches the browser.

## API endpoints

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /api/auth/register` | public | Create User + Learner, return token + profile |
| `POST /api/auth/login` | public | Authenticate, return token + profile |
| `GET /api/auth/me` | token | Current user's profile |
| `GET /api/me/progress` | token | Concept mastery grouped by topic (strengths/weaknesses) |
| `GET /api/topics` | token | Topic suggestions `[{slug, title}]` |
| `POST /api/sessions` | token | Start a session; **syllabus-gated** first chapter, or `{in_syllabus:false, reason}` |
| `POST /api/sessions/<id>/answer` | token | Record one question's answer → `{is_correct, correct_index, feedback, points, chapter_complete}` |
| `POST /api/sessions/<id>/next` | token | Adapt difficulty + award badges; return the next chapter or `{is_complete:true}` |
| `POST /api/sessions/<id>/ask` | token | Grounded Q&A from the grade's textbook (does not affect grading; refuses questions matching the chapter's unanswered quiz questions) |
| `GET /api/sessions/<id>` | token | Full session state (chapters/questions/badges) — evidence of logging |

**Answer-secrecy:** chapters/questions shown to the browser use
`PresentedChapterSerializer` / `PresentedQuestionSerializer`, which omit
`correct_index`, `hint` and `concept`. The full serializers (with the answer key)
are used only by `GET /api/sessions/<id>`. Sessions are owned: every session
endpoint filters by `learner__user=request.user`.

## Request flows

**`POST /api/sessions` (start)** — derive the learner from the token →
`personalization.starting_difficulty` + `weak_concepts` (returning learners) →
`llm.generate_chapter(gate=True)` (retrieve grade passages, refuse if off-syllabus,
else write a grounded chapter) → on refusal return `{in_syllabus:false, reason}` and
create nothing → otherwise create Session + first Chapter (+Questions) and return the
presented chapter.

**`POST /api/sessions/<id>/answer`** — record the answer, evaluate correctness,
`adaptation.score_question` (points + streak), update `ConceptStat`, report whether
the chapter is now fully answered. Difficulty does **not** change here.

**`POST /api/sessions/<id>/next`** — require the chapter answered →
`adaptation.adjust_difficulty_for_chapter` (from the chapter score) →
`gamification.award_badges` → finish, or `generate_chapter` for the next chapter
(reusing the `setting`, the previous `summary`, and the learner's weak concepts).

**`POST /api/sessions/<id>/ask`** — `llm.answer_question` retrieves grade passages
(biased by topic) and answers strictly from them, refusing if off-syllabus. Kept
entirely separate from grading.

## Data model (`core/models.py`)

- **Learner** — `user` (OneToOne → auth `User`, null for legacy/superuser), `name`,
  `created_at`. The per-user profile; owns sessions and concept stats.
- **Session** — `learner` FK, `topic` (free text), `grade`, `difficulty`, `points`,
  `current_streak`, `chapter_count`, `setting` (persistent characters/place), `is_complete`.
- **Chapter** — `session` FK, `order`, `title`, `paragraphs` (JSON list), `summary`
  (carried forward), `difficulty_at_time`, `sources` (RAG refs).
- **Question** — `chapter` FK, `order`, `question_text`, `options` (JSON, 4),
  `correct_index`, `hint`, `concept`, `user_answer_index`, `is_correct`, `response_time_ms`.
- **Badge** — `session` FK, `name`, `awarded_at`.
- **ConceptStat** — `learner` FK, `topic`, `concept`, `attempts`, `correct`, `last_seen`,
  `unique_together(learner, topic, concept)`. Mastery aggregated across all sessions.

## Pedagogical / gamification / personalisation rules

- Constants in `adaptation.py`: `START_DIFFICULTY=3`, `MIN=1`, `MAX=5`, `MIN_CHAPTERS=1`,
  `MAX_CHAPTERS_CAP=6`, `POINTS_PER_DIFFICULTY=10`, chapter up/down thresholds `0.75`/`0.25`.
- **Content-adaptive length** (`planning.py` + `retrieval.gather_topic_content`): a
  session's chapter count and each chapter's paragraph/question ranges come from how
  much of the grade's textbook actually covers the topic (thin → short, few/no
  questions; rich → longer, more). The plan is stored on the `Session`; a per-session
  floor guarantees at least one question.
- **Points** (per question): `10 × difficulty` for a correct answer (difficulty is
  constant within a chapter).
- **Difficulty** (per chapter): score = correct/total; ≥0.75 → +1, ≤0.25 → −1, else
  hold. A chapter with **no questions** gives no signal and leaves difficulty unchanged.
- **Streak**: consecutive correct questions; **Badges**: *First Steps* (first correct),
  *On Fire* (3-streak), *“&lt;Topic&gt; Explorer”* (completion).
- **Personalisation** (`personalization.py`): a returning learner's weak concepts
  (lowest mastery) are fed into generation as `revisit_concepts`, and their average
  mastery on a topic maps the **starting difficulty** into the 2–4 band.
- **Story memory**: a `create_session` for a topic with an unfinished story resumes
  that `Session` (same setting/plan/state) instead of starting a new one.

## Key design decisions (for the viva)

- **Rule-based adaptation, not ML** — transparent and easy to defend; isolated in
  `adaptation.py` / `personalization.py` so it can be swapped later.
- **RAG grounding + syllabus gate** — facts come from the grade's textbook; topics it
  doesn't cover are refused rather than hallucinated.
- **Mock mode (`USE_MOCK_LLM`)** — develop, test and demo with no network/key; also the
  safety net if the LLM returns unparseable output. The whole test suite runs in mock.
- **Token auth, server-side key, answer secrecy** — passwords hashed by Django; the LLM
  key never leaves the server; unanswered questions' answers never reach the browser.
- **Q&A anti-cheat (defence in depth)** — a deterministic `difflib` similarity gate in
  `views.ask` refuses near-copies of the chapter's unanswered quiz questions without an
  LLM call; a prompt instruction (`avoid_questions`) catches paraphrases. Answered
  questions become discussable again.
- **Rate limiting (`core/throttles.py`)** — DRF per-user throttles on the paid endpoints
  (create/next: 20/min + 200/day; ask: 15/min + 150/day; login/register: 10/min per IP)
  so loops or rapid clicking can't burn credits; `answer` is free and unthrottled. The
  provider dashboard's spend cap is the true worst-case ceiling.
- **Single `core` app + function-based views** — minimal moving parts for a prototype one
  student must fully understand and extend.

## Out of scope (future work)

- **AI image generation** for chapters — clearly-marked `# TODO` hook in `core/llm.py`.
- Multilingual (Sinhala/Tamil), offline mode.
- Production auth hardening: a token in `localStorage` is the standard teaching approach
  for an SPA; production would use httpOnly cookies + HTTPS + token refresh.
- Docker, deployment, Celery/Redis, real-time features, a cloud vector DB.
