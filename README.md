# Science Story Quest — Adaptive Science Storytelling (FYP Midpoint MVP)

An adaptive digital storytelling web app that teaches science to Sri Lankan
middle-school students (Grades 6–9). A learner logs in, picks a grade and types a
topic; the system writes a short, continuous, multi-**chapter** story grounded in that
grade's textbook. Each chapter is a few paragraphs followed by comprehension questions;
difficulty adapts between chapters, points and badges reward progress, and the learner's
concept mastery carries across sessions. Everything is saved for later analysis.

Key features: **accounts** (login/registration), **chapters** with question sets,
**textbook-grounded** generation with an off-syllabus **refusal gate**, **cross-session
personalisation** (revisit weak concepts + adaptive starting difficulty), and a
**grounded Q&A** side-panel.

- **Backend:** Python · Django · Django REST Framework · SQLite · DRF token auth
- **Frontend:** React (Vite, JavaScript)
- **LLM:** OpenRouter (server-side via the OpenAI-compatible SDK), with a built-in
  **mock mode** so the whole app runs offline with no API key.
- **RAG:** stories and Q&A are grounded in the Grade 6–9 science textbooks via a local
  Chroma vector index (see section 4).

> The app ships in **mock mode** (`USE_MOCK_LLM=true`), so you can run and demo it
> immediately without any API key or internet. Switch to the real LLM later (see below).

---

## Prerequisites

- **Python 3.12** (any 3.10+ works)
- **Node.js 18+** (tested on Node 22)
- Windows (commands below are for PowerShell; macOS/Linux equivalents noted where relevant)

---

## 1. Backend — Django API (run on port 8000)

Open a terminal in the `backend/` folder.

```powershell
cd backend

# Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1
# (Command Prompt instead of PowerShell:  venv\Scripts\activate.bat)
# (macOS/Linux:                           source venv/bin/activate)

# If PowerShell blocks the activation script, allow it for this user once:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# Install dependencies
pip install -r requirements.txt

# Create your local config from the template
copy .env.example .env          # macOS/Linux: cp .env.example .env
# The default .env runs in MOCK mode — no key needed to start.

# Set up the database
python manage.py migrate

# (optional) create an admin login to browse saved data at /admin
python manage.py createsuperuser

# Start the API
python manage.py runserver
```

The API is now at **http://localhost:8000/api/**.

### Verify the backend

```powershell
# Run the automated tests (uses mock mode, no network needed)
python manage.py test core
```

Or hit it directly (PowerShell). Session endpoints require a token, so register first:

```powershell
# Register -> returns an auth token
$reg = Invoke-RestMethod -Method Post http://localhost:8000/api/auth/register `
  -Body '{"username":"amaya","password":"pw12345!"}' -ContentType application/json
$headers = @{ Authorization = "Token $($reg.token)" }

# Start a session (topic is free text; grade is 6, 7, 8 or 9)
$body = '{"topic":"Photosynthesis","grade":7}'
Invoke-RestMethod -Method Post http://localhost:8000/api/sessions -Headers $headers -Body $body -ContentType application/json
```

---

## 2. Frontend — React app (run on port 5173)

Open a **second** terminal in the `frontend/` folder (keep the backend running).

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser. The first screen is **login /
registration** — create an account, then pick a grade, type a topic, and start. The
frontend talks to the backend at `http://localhost:8000` (allowed via CORS).

---

## 3. Switching from mock content to the real LLM

1. Get a free API key from <https://openrouter.ai/keys>.
2. Edit `backend/.env`:

   ```env
   PROXY_URL=https://openrouter.ai/api/v1
   MODEL=meta-llama/llama-3.3-70b-instruct
   API_KEY=sk-or-...your key...
   USE_MOCK_LLM=false
   ```

   You can point at **any OpenAI-compatible provider/proxy** by changing these three
   values (see `core/llm_config.py` for examples, e.g. Chutes). `PROXY_URL` may be the
   base URL or the full `…/chat/completions` endpoint.

3. Restart `python manage.py runserver`.

**About the model:** OpenRouter's list of free models changes over time. If a call
fails because the model is unavailable, the API returns a clear message telling you
to update `MODEL` — just set it to any current model (e.g. another
`:free` variant) and restart.

The API key is read **only on the server** (via `python-dotenv`) and is never sent
to the browser.

---

## 4. (Optional) Textbook-grounded stories with RAG

In **live mode**, stories can be grounded in the real Sri Lankan Grade 6–9 science
textbooks using Retrieval-Augmented Generation (RAG): at request time the backend
retrieves the few most relevant textbook passages for the student's grade + topic
and tells the model to base its facts on them. Everything runs locally — Chroma
stores the index on disk and embeds with a built-in local model (no embedding API).

**This is optional.** Without it the app still runs (mock mode with canned content,
or live mode generating from the model's general knowledge).

To enable it:

1. Put the textbook PDFs in `backend/textbooks/`, named by grade (and part):
   `G6.pdf`, `G7P1.pdf`, `G7P2.pdf`, `G8P1.pdf`, `G8P2.pdf`, `G9P1.pdf`, `G9P2.pdf`.
   (`P1`/`P2` are just the two parts of a grade's book; both map to that grade.)

2. Build the index once (re-run any time the PDFs change):

   ```powershell
   python manage.py build_index
   ```

   This extracts, cleans, chunks and embeds the books, printing a per-grade chunk
   summary; the index is saved to `backend/chroma_store/`. The first run downloads
   the small local embedding model (~80 MB) once.

3. Run in live mode (section 3). When a story is grounded, the API response includes
   a `sources` list and the UI shows a line like *"Based on: Grade 7 textbook (p.16)"*.

> **The textbook PDFs are not distributed with this code.** They are copyright
> material published by the Sri Lankan Educational Publications Department, and they
> are excluded from the repository and from every submission archive. `build_index`
> expects them at `backend/textbooks/`, named as in step 1; obtain them from the
> Department's own site and place them there before building the index. Everything
> else — the code, the probe sets, the evaluation results and the figures — is
> present.
>
> The built index (`backend/chroma_store/`) is also git-ignored. The extra
> dependencies (`pdfplumber`, `chromadb`) are already in `requirements.txt`.

---

## Project structure

```
adaptive-science-storytelling/
├─ backend/                 # Django project + the single "core" app
│  ├─ config/               # Django project settings & root URLs
│  ├─ core/                 # all app code (see ARCHITECTURE.md)
│  │  ├─ models.py          # Learner, Session, Chapter, Question, Badge, ConceptStat
│  │  ├─ llm.py             # chapter generation + grounded Q&A (OpenRouter + mock + RAG)
│  │  ├─ mock_content.py    # canned chapters for mock mode
│  │  ├─ adaptation.py      # points + per-chapter difficulty (pedagogical engine)
│  │  ├─ personalization.py # cross-session concept mastery (weak concepts, adaptive start)
│  │  ├─ planning.py        # content-driven session plan (chapter count + per-chapter lengths)
│  │  ├─ gamification.py    # badge logic
│  │  ├─ throttles.py       # per-user rate limits on the paid LLM endpoints
│  │  ├─ serializers.py     # DRF response shapes (presented vs full)
│  │  ├─ views.py           # API endpoints: auth + story loop + Q&A
│  │  ├─ urls.py            # /api routes
│  │  ├─ constants.py       # topic suggestions
│  │  ├─ retrieval.py       # RAG: query the textbook vector index
│  │  ├─ management/commands/build_index.py  # RAG: ingest textbooks → index
│  │  └─ tests.py           # end-to-end tests (mock mode)
│  ├─ textbooks/            # (git-ignored) source PDFs: G6.pdf, G7P1.pdf, …
│  ├─ chroma_store/         # (git-ignored) the built vector index
│  ├─ .env.example          # config template (copy to .env)
│  └─ requirements.txt
├─ frontend/                # Vite + React app
│  └─ src/
│     ├─ App.jsx            # screens: auth / start / story / complete / progress
│     ├─ api.js             # fetch wrappers for the API
│     └─ styles.css         # all styling
├─ README.md
└─ ARCHITECTURE.md          # how the code maps to the project's conceptual layers
```

---

## How the adaptation works (quick reference)

- **Content-adaptive length:** how long the story runs is driven by how much the
  grade's textbook actually covers the topic — thin topics give a short story with
  few/no questions; rich topics give several longer chapters with more (1–6 chapters).
- **Points:** a correct answer earns `10 × difficulty`; the **streak** counts
  consecutive correct answers.
- **Difficulty** (1–5) adapts **between chapters** from the chapter score:
  ≥75% correct → harder, ≤25% → easier (a chapter with no questions doesn't change it).
- **Personalisation:** a returning learner revisits weak concepts and starts at a
  difficulty matched to their mastery of the topic.
- **Story memory:** returning to an unfinished topic **continues the same story**
  (same characters, preserved points/difficulty); a finished topic starts fresh.
- **Badges:** *First Steps* (first correct), *On Fire* (3-in-a-row streak),
  *“&lt;Topic&gt; Explorer”* (finishing the session).

## Safety & cost controls

- **Q&A anti-cheat:** pasting one of the current chapter's *unanswered* quiz questions
  into the "Ask about this topic" panel is refused without calling the model (a
  `difflib` similarity gate in `views.ask`; threshold in `SIMILARITY_THRESHOLD`).
  As a backstop, the model is also told not to answer those questions even when
  paraphrased. Once a question has been answered, discussing it is allowed again.
- **Rate limits (DRF throttling):** the endpoints that trigger paid LLM calls are
  capped per user — story generation `20/min` + `200/day`, Q&A `15/min` + `150/day` —
  and login/register at `10/min` per IP. Rates live in `settings.py`
  (`DEFAULT_THROTTLE_RATES`); classes in `core/throttles.py`. Over the limit returns
  HTTP 429 with a "try again in N seconds" message. The `answer` endpoint is not
  throttled (it makes no LLM call).
- **Provider spend cap (not in code):** set a credit/spend limit on your API key in
  the provider's dashboard (e.g. OpenRouter) — throttling lowers the risk; the spend
  cap bounds the worst case.

See **ARCHITECTURE.md** for the full mapping of code to conceptual layers.

---

## Building the submission archive

`scripts/make_submission_zip.ps1` produces `CB011725_ASCALS_code.zip`: all source, the
configuration templates, and the complete `backend/evaluation/` directory including
probes, results, figures and run logs.

```powershell
pwsh ./scripts/make_submission_zip.ps1 -Force
```

The evaluation output is thesis evidence and is **not regenerable** — the chapters
scored in T4 were sampled at temperature 0.7, so re-running produces different text and
different numbers. It ships in full.

Excluded: `venv/`, `node_modules/`, `__pycache__/`, `chroma_store/`,
`chroma_store_backup_prefix/`, `textbooks/`, `db.sqlite3`, `frontend/dist/`, `.git/` and
`.env`. The script refuses to build if a `.env` or any PDF reaches the staging area.
