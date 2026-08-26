# Repository audit — submission readiness

**Nothing in this audit has been acted on. No file has been deleted, moved or renamed.**
This is a proposal for review.

Produced 2026-08-26 against commit `d5669e7` on branch `evaluation-harness`.

---

## 1. Security check — the answer first

### Is `backend/.env` tracked by git?

**No.** `git ls-files` matches exactly one `.env`-like path, `backend/.env.example`, which
is the template. `git log --all --full-history -- '*.env' '**/.env'` returns **no commit
that has ever touched a `.env` path**. The live `backend/.env` has never been staged,
committed, or reachable from any ref. It is excluded by `.gitignore:1`.

`backend/.env.example` was checked line by line and is clean: `API_KEY=` is empty, and the
two commented provider examples are truncated placeholders (`sk-or-...`, `cpk_...`) too
short to be keys.

### Is any credential present in any tracked file, or anywhere in history?

Every tracked blob at `HEAD` (143 files) and **every unique blob in all 18 commits across
all refs** (193 blobs) was scanned against patterns for OpenRouter, Anthropic, OpenAI,
AWS, GitHub, Google and Slack credentials, private-key blocks, bearer literals, and
assignments of secret-shaped names to long literals.

**No API key, provider token or external credential was found — not in the working tree
and not in history.**

### One finding you need to decide about

**`backend/config/settings.py:30` — Django `SECRET_KEY`, 66 characters, hardcoded, tracked,
and already on `origin/main`.**

| | |
|---|---|
| What it is | The key Django generated at `startproject`. Not an API key; it signs session cookies, CSRF tokens and password-reset tokens |
| Introduced by | `b65253d Initial Commit` — it predates this evaluation programme |
| Already public? | **Yes, if the GitHub repo is public.** `origin/main` already contains it. `gh` is not installed here so I could not read the repo's visibility — **check whether `github.com/ShakyaMatara/adaptive-science-storytelling` is public before deciding** |
| Practical exposure now | Low. `DEBUG = True`, `ALLOWED_HOSTS = ['localhost', '127.0.0.1']`, no deployment, and the SQLite database holds only development data |
| Why it still matters | Django's own comment two lines above says *"keep the secret key used in production secret"*. If this project is ever deployed with this key, session and password-reset tokens are forgeable by anyone who has read the repo |

**Recommendation (your call, not acted on):** generate a fresh key, read it from the
environment alongside the API key, and leave the old one where it is. Rewriting 18 commits
of history to purge it would break every commit hash the thesis's audit trail refers to,
and buys nothing while the old key is not deployed anywhere. If the repo is public and you
would rather it were not visible at all, the cheap and complete fix is to rotate the key
and never deploy the old one — not to rewrite history.

Nothing else in the repository requires action before a push.

---

## 2. Sizes

| Scope | Size |
|---|---|
| **Whole working tree, including `.git`** | **737 MB** |
| `.git` object store | 1.9 MB (`size-pack` 1.20 MiB, loose 387 KiB) |
| **What actually reaches GitHub on push** | **≈ 1.5 MB** (measured: `git bundle` of all refs) |
| Tracked files checked out at `HEAD` | 2.7 MB, 143 files |

### Top-level

| Directory | Size | Tracked? |
|---|---|---|
| `backend/` | 690 MB | partially |
| `frontend/` | 46 MB | partially |
| `.git/` | 1.9 MB | — |
| `.claude/` | 353 KB | no |
| `*.md`, `.gitignore` | 44 KB | yes |

### `backend/` breakdown

| Path | Size | Tracked? |
|---|---|---|
| `venv/` | **523 MB** | no |
| `textbooks/` | 71 MB | no |
| `chroma_store/` | 50 MB | no |
| `chroma_store_backup_prefix/` | 42 MB | no |
| `evaluation/` | 3.8 MB | partially (allowlisted) |
| `db.sqlite3` | 936 KB | no |
| `core/` | 816 KB | yes (minus `__pycache__`) |
| `config/` | 35 KB | yes |
| `manage.py`, `requirements.txt`, `.env.example` | 3 KB | yes |

**The 737 MB is almost entirely untracked.** 96% of it is `venv`, `textbooks`,
`chroma_store`, the backup and `node_modules` — none of which is in git and none of which
reaches GitHub.

---

## 3. Classification

### KEEP — required by the application, the tests or the thesis

| Path | Why |
|---|---|
| `backend/core/` (all `.py`) | The application. 27 tests exercise it |
| `backend/core/management/commands/build_index.py` | Builds the index every result depends on |
| `backend/core/management/commands/eval_*.py` (11 files) | Produce the evidence; the thesis claims reproducibility from them |
| `backend/config/` | Django project configuration |
| `backend/manage.py`, `requirements.txt`, `.env.example` | Entry point, dependency pins, config template |
| `backend/evaluation/harness.py`, `__init__.py` | Shared measurement code |
| `backend/evaluation/analysis/` (4 scripts + README) | Produce reported figures the commands cannot compute from inside one run |
| `backend/evaluation/probes/` (8 files, 96 KB) | Curated inputs. **Not regenerable** — `in_syllabus.json` was curated against the printed contents pages, `in_syllabus_paraphrased.json` was authored blind, `textbook_toc.md` was transcribed by hand |
| `backend/textbooks/` (71 MB) | Source corpus. **Gitignored and must stay so** — seven government textbooks, third-party copyright |
| `frontend/src/`, `index.html`, `package.json`, `package-lock.json`, `vite.config.js` | The client |
| `README.md`, `ARCHITECTURE.md`, `EVALUATION_README.md`, `.gitignore` | Documentation and exclusions |

### EVIDENCE — cited by the thesis; keep and never regenerate

| Path | Size | Note |
|---|---|---|
| `backend/evaluation/results/*_latest.csv` (51 files) | ~500 KB | Every table in Chapter 7 |
| `backend/evaluation/results/figures/` (9 PNGs) | 952 KB | Regenerable from the CSVs by `eval_charts`, but only while the CSVs survive |
| `backend/evaluation/results/*.md` (7 records) | ~200 KB | `corpus_defects.md`, `midpoint_corrections.md`, `text_quality_impact.md`, `g9p1_coverage_gap.md`, `t1_false_positive_analysis.md`, and this audit and the writing pack |
| `backend/evaluation/results/t4_chapters_latest.json` | 444 KB | **The single most irreplaceable file in the repo.** Prose generated at temperature 0.7; re-running produces different chapters. Without it no T4 figure can be checked |
| `backend/evaluation/results/t4_chapter_dossier_BLIND_latest.md` | 80 KB | Carries the hand-written scoring tables; it is an *input* to `t4_human_validation.py`, not only an output |
| `backend/evaluation/results/*_2026*.{csv,json,md}` (109 CSV + others) | ~1.2 MB | Timestamped audit trail. **Currently NOT tracked** — see §5 |
| `backend/evaluation/results/logs/` | 338 KB | Console output of every command run. **Currently NOT tracked** — see §5 |
| `backend/chroma_store/` | 50 MB | The index every number was computed against. Rebuilding it would not reproduce it exactly: it depends on `g9p1_recovered_pages.json` and on extraction behaviour that has been repaired mid-programme |
| `backend/chroma_store_backup_prefix/` | 42 MB | **Standing instruction: stays until you say otherwise.** It is the pre-repair index and it is the only thing that could substantiate the before/after ingestion figures if challenged |

### REMOVE — safe to delete

| Path | Size | Reason | What breaks if I am wrong |
|---|---|---|---|
| `__pycache__/` outside `venv` (6 dirs, 44 `.pyc`) | 495 KB | Byte-compiled cache, regenerated on next import | **Nothing.** Python rebuilds them silently |
| `frontend/dist/` | 165 KB | Vite build output, regenerated by `npm run build` | Nothing, until you want a built client — then one command |
| `.claude/worktrees/` | 353 KB | Session worktree for this programme's tooling; untracked, unreferenced by the app | Nothing in the repo. **Remove with `git worktree remove`, not `rm`** — a bare `rm` leaves a stale entry in `.git/worktrees` |
| `frontend/node_modules/` | **45 MB** | Regenerable by `npm ci` from the committed `package-lock.json` | The dev server and build until `npm ci` is run. `package-lock.json` pins exact versions, so recovery is deterministic |
| `backend/venv/` | **523 MB** | Regenerable by `python -m venv venv && pip install -r requirements.txt` | **Every `manage.py` command, every eval script and the 27 tests, until it is recreated.** Recovery needs network access, and `requirements.txt` is not a full lock file, so a rebuilt venv is not guaranteed to resolve to identical versions. **Do this last, after the thesis is submitted** |
| `backend/db.sqlite3` | 936 KB | Development database; no result depends on it — the eval commands create no `Learner`, `Session` or `Chapter` rows | Local dev state and any superuser account. Recreated by `manage.py migrate` |

**Total reclaimable: ≈ 570 MB, of which 568 MB is `venv` plus `node_modules`.** Removing
everything above leaves the repository at roughly **167 MB on disk** and **unchanged at
1.5 MB on GitHub** — because none of it is tracked. **Deleting any of it makes the push
no smaller.** The only reason to delete is local disk space.

### UNCERTAIN — your call

| Path | Why I cannot decide |
|---|---|
| `backend/evaluation/results/*_2026*.{csv,json,md}` (~1.2 MB) | These are the timestamped provenance chain behind every `_latest` file. They are **not tracked**, so they exist only on this machine and would be lost with the directory. Whether the thesis needs the chain or only the endpoints is a supervisor question. My inclination: track them — 1.2 MB is nothing against 1.5 MB of push, and "the audit trail was on one laptop" is a bad answer to a viva question |
| `backend/evaluation/results/logs/` (338 KB) | Same reasoning, and sharper: **`RESULTS_SUMMARY.md` §13 cites `logs/` as an appendix, but zero log files are tracked.** A clone would not contain the appendix the manifest promises. Either track them or amend the manifest |
| `backend/db.sqlite3` | Classified REMOVE above on the basis that no result depends on it. If it holds a demo account or seeded learner you want to show in a demonstration, it is KEEP and I cannot tell from the file |
| `backend/core/management/commands/eval_groundtruth.py`, `eval_index_quality.py` | Both are **KEEP** — their outputs (`ground_truth.csv`, `index_quality_before.csv`, `index_quality_after.csv`) are cited by 7.3 and 7.6. But neither is named in any `.md`, including `EVALUATION_README.md`, which documents the other nine commands. That is a documentation gap, not a deletion candidate. Flagging so it is fixed rather than mistaken for dead code |
| `frontend/dist/` | REMOVE above assumes you rebuild before any demonstration. If your submission process expects a pre-built client in the repo, it is KEEP |

### Explicitly checked and found absent

No superseded scripts, one-off diagnostics or duplicate probe files exist **inside the
repository**. All ~80 diagnostic scripts written during this programme live in the session
scratchpad outside the repo and were never committed. The four scripts in
`evaluation/analysis/` are all current and all produce reported figures. The eight probe
files are distinct: no duplicates, no superseded versions.

---

## 4. `.gitignore` — what it excludes

Exclusion rules, in file order:

```
backend/.env                          frontend/node_modules/
backend/venv/                         frontend/dist/
__pycache__/                          .vscode/  .idea/
*.py[cod]                             .DS_Store  Thumbs.db
backend/db.sqlite3                    backend/evaluation/results/*
backend/textbooks/
backend/chroma_store/
backend/chroma_store_backup_prefix/
```

`backend/evaluation/results/*` excludes everything, then **69 `!` rules re-admit the files
the thesis cites**. This is the fragile part: an allowlist fails silently — a cited file is
simply absent from the clone and nothing warns you.

**Verified.** Every file named in the `RESULTS_SUMMARY.md` §13 manifest was cross-checked
against `git ls-files`: **61 of 61 named files are tracked**, and the two apparent misses
(`t1_gate_margins_*_latest.csv`, `t1_gate_counterfactual_*_latest.csv`) are glob patterns
whose four concrete files are all tracked.

**One real gap: `logs/` is cited in the manifest and has zero tracked files.**

Twelve tracked results files are not named in the manifest — the four
`t1_gate_margins`/`counterfactual` files (covered by globs), `index_quality_after.csv`
(cited in a shared cell), and seven run-1/run-2 T4 retention copies. Harmless; worth a
manifest line for the T4 copies so a reader knows why three runs' files are present.

---

## 5. Push readiness

| Check | Result |
|---|---|
| Working tree | **Clean.** No modified, staged or untracked files |
| Branch | `evaluation-harness` |
| Remote | `https://github.com/ShakyaMatara/adaptive-science-storytelling.git` |
| Size on push | **≈ 1.5 MB** |
| Commits ahead of `origin/main` | **17** at `d5669e7`; **18** once the commit adding this audit and the writing pack lands |
| Credentials in the push | **None.** See §1 — with the Django `SECRET_KEY` caveat, which is already on `origin/main` |
| Textbook PDFs in the push | **No.** `backend/textbooks/` is gitignored — important, they are third-party copyright |

### The 17 commits, oldest first

| # | SHA | Subject |
|---|---|---|
| 1 | `63f8360` | Repair page and chapter metadata in the textbook ingestion pipeline |
| 2 | `e874a49` | Cite printed page ranges, and measure three further corpus defects |
| 3 | `5383e47` | Correct the FINDING-4 detector and restructure the text-quality report |
| 4 | `1341406` | Map pages by per-book offset and attribute chapters from the tables of contents |
| 5 | `6fe5688` | Recover 19 image-only pages, and repair the doubled-character and lost-glyph defects |
| 6 | `19b6578` | Add evaluation harness |
| 7 | `8c5a5a0` | Curate the T1 positive probe set against the published tables of contents |
| 8 | `52ee5e0` | Add a paraphrased positive probe set for the second T1 condition |
| 9 | `703fc53` | T1–T3 results |
| 10 | `68e8e47` | FINDING-9: repair the planner's coverage measure, and record the correction trail |
| 11 | `e63d3a4` | Populate the harness price table from live OpenRouter rates |
| 12 | `ae13787` | T6 model benchmark, and fix the token cap that invalidated its first run |
| 13 | `6a1dfe7` | T4–T6 results, and fix the judge token cap that voided T4's first run |
| 14 | `27a8294` | Chapter 7 results summary |
| 15 | `0a9f883` | T4 re-run with judges exchanged, and a statistical honesty pass |
| 16 | `5774b97` | T4: persist the evidence behind the metrics, and re-run (FINDING-10, FINDING-11) |
| 17 | `d5669e7` | T4: human validation of the LLM judge, and three defects it surfaced |

**Not pushed.** Awaiting your instruction.

---

## 6. What I would do, in order

1. **Decide the Django `SECRET_KEY` question** — it is the only item with a security
   dimension, and it turns on whether the GitHub repo is public.
2. **Decide `logs/` and the timestamped results.** They are the audit trail; they are
   currently on one laptop only, and the manifest already promises `logs/` to a reader.
3. **Push.** The push is 1.5 MB and carries no credentials and no copyrighted PDFs.
4. **Delete nothing until the thesis is submitted.** Everything in REMOVE is untracked, so
   removing it does not shrink the push by one byte — it only frees local disk, and
   `venv` in particular is the environment every reproduction step needs.
