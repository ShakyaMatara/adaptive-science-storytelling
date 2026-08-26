"""LLM service: turns a topic + grade + difficulty into a story CHAPTER — a
titled, multi-paragraph scene followed by a few comprehension questions. This is
the "Curriculum / Story Generation" layer.

Two modes:
  * USE_MOCK_LLM=true  -> pre-written canned chapters (no network). For dev/demos.
  * USE_MOCK_LLM=false -> any OpenAI-compatible provider/model (configured in
                          core/llm_config.py via .env), called server-side only
                          (the API key never reaches the browser).

The public entry point is generate_chapter(...). In live mode it first retrieves
the most relevant textbook excerpts for the grade + topic (RAG) and tells the model
to base its facts on them; it also carries the story `setting` and the previous
chapter's summary forward for narrative continuity.
"""

import json
import re

from openai import (
    OpenAI,
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
)

from . import llm_config
from .mock_content import get_mock_chapter

# Provider config (base URL / API key / model) lives in core/llm_config.py and is
# read from .env at call time — switch providers by editing .env only.
# A ceiling, not a wait: fast models (Gemini Flash-Lite class) answer in seconds;
# slower or reasoning models can need a minute or more before we give up.
REQUEST_TIMEOUT_SECONDS = 120

# Short hints that help the model pitch each difficulty level appropriately.
DIFFICULTY_GUIDE = {
    1: "very simple words and short sentences; concrete everyday examples; no jargon",
    2: "simple language; introduce one key science word and explain it plainly",
    3: "clear middle-school language; use correct science terms with brief explanations",
    4: "richer vocabulary; expect the student to connect two ideas together",
    5: "the most challenging level; precise terminology and questions needing real reasoning",
}


class LLMError(Exception):
    """Raised when the LLM cannot be reached or used (timeout, rate limit,
    bad/missing key, unavailable model). Carries a message that is safe and
    helpful to show the user; the views turn it into a friendly JSON error
    instead of a 500.
    """


# --- Prompt building ------------------------------------------------------------

def _format_passages(passages):
    """Render retrieved textbook passages as a numbered block for the prompt."""
    blocks = []
    for i, p in enumerate(passages, start=1):
        ref = f"p.{p.get('page')}"
        if p.get("section"):
            ref += f", {p['section']}"
        blocks.append(f"[{i}] ({ref}) {p['text']}")
    return "\n\n".join(blocks)


def _build_chapter_messages(topic, grade, difficulty, setting, story_so_far,
                            revisit_concepts, passages, gate=False,
                            min_paragraphs=3, max_paragraphs=4, min_questions=1, max_questions=2):
    """Build the chat messages instructing the model to write one story chapter.

    When `gate` is True, the model is first asked to judge whether the topic is
    covered by the grade's textbook (using the excerpts) and to refuse if not.
    """
    level_note = DIFFICULTY_GUIDE.get(difficulty, DIFFICULTY_GUIDE[3])
    grade_label = f"Grade {grade}" if grade else "Grade 6-9"

    system = (
        "You are a friendly science teacher who writes short, engaging stories that teach "
        "science to Sri Lankan middle-school students (Grades 6-9). You are scientifically "
        "accurate and age-appropriate. You ALWAYS respond with a single valid JSON object and "
        "nothing else."
    )

    user = (
        f"Write ONE chapter of a continuing science story that teaches the topic \"{topic}\" to "
        f"a Sri Lankan {grade_label} student.\n"
        f"Difficulty level: {difficulty} out of 5 ({level_note}).\n\n"
        f"The chapter must have a short title and between {min_paragraphs} and {max_paragraphs} "
        f"paragraphs forming one continuous narrative. Choose the length that fits how much the "
        f"excerpts below actually contain — keep it short if there is little material, longer if "
        f"there is a lot. Weave the science naturally into the story; you may use Sri Lankan names "
        f"and settings.\n"
    )

    # Syllabus gate (first chapter only): refuse topics the grade's book doesn't cover.
    if gate:
        user += (
            f"\nIMPORTANT: First judge, using ONLY the textbook excerpts below, whether the topic "
            f"\"{topic}\" is actually part of the {grade_label} science syllabus. If the excerpts do "
            f"NOT cover this topic for {grade_label}, respond with ONLY this JSON and nothing else: "
            f'{{"in_syllabus": false, "reason": "<one short, friendly sentence>"}}. '
            f"Otherwise set \"in_syllabus\": true and produce the chapter below.\n"
        )

    # Narrative continuity: reuse the established setting and follow on from the
    # previous chapter's summary.
    if setting:
        user += f"\nUse this established setting (keep the same characters and place): {setting}\n"
    else:
        user += "\nInvent a consistent setting (the characters and place) for the whole story.\n"
    if story_so_far:
        user += f"This chapter continues the story. Previously: {story_so_far}\n"

    # Reinforce concepts the learner has struggled with (within-session + Phase 4).
    if revisit_concepts:
        user += (
            "\nThe learner has struggled with these concepts — gently revisit and reinforce them "
            f"in this chapter: {', '.join(revisit_concepts)}.\n"
        )

    if max_questions <= 0:
        question_instr = (
            "\nDo NOT include any comprehension questions for this chapter; the \"questions\" array "
            "must be empty ([]).\n"
        )
    else:
        question_instr = (
            f"\nThen write between {min_questions} and {max_questions} multiple-choice comprehension "
            f"questions about this chapter — choose the number that fits how much the excerpts contain "
            f"(use {min_questions} if there is little to test). Each question must have EXACTLY 4 "
            f"options, the index of the correct option, a one-sentence hint, and a short 'concept' "
            f"label naming what it tests (e.g. \"evaporation\").\n"
        )

    in_syllabus_key = '"in_syllabus": true, ' if gate else ""
    user += question_instr + (
        f"\nRespond with ONLY a JSON object using exactly these keys:\n"
        f'{{{in_syllabus_key}"setting": string, "title": string, "paragraphs": [string, ...], '
        f'"summary": string, "questions": [{{"question": string, "options": [4 strings], '
        f'"correct_index": integer 0-3, "hint": string, "concept": string}}]}}\n'
        f'"summary" must be 1-2 sentences capturing this chapter, to continue the story next time.'
    )

    # RAG grounding: base the facts on the retrieved textbook excerpts.
    if passages:
        user += (
            "\n\nBase all scientific facts in the story and the questions strictly on the following "
            "textbook excerpts for this grade. Do not introduce facts that contradict them. If the "
            "excerpts don't cover something, keep the story general rather than inventing specifics.\n\n"
            "TEXTBOOK EXCERPTS:\n" + _format_passages(passages)
        )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# --- Response parsing -----------------------------------------------------------

def _strip_to_json(text):
    """Pull the JSON object out of a model reply that may include code fences or
    stray prose around it."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    return text


def _validate_question(q):
    """Validate and normalise one question dict. Raises ValueError if malformed."""
    options = q.get("options")
    if not isinstance(options, list) or len(options) != 4:
        raise ValueError("each question needs exactly 4 options")
    try:
        idx = int(q.get("correct_index"))
    except (TypeError, ValueError):
        raise ValueError("correct_index must be an integer")
    if not 0 <= idx <= 3:
        raise ValueError("correct_index must be between 0 and 3")
    if not str(q.get("question", "")).strip():
        raise ValueError("question text must not be empty")
    return {
        "question": str(q["question"]).strip(),
        "options": [str(o) for o in options],
        "correct_index": idx,
        "hint": str(q.get("hint") or "").strip(),
        "concept": str(q.get("concept") or "").strip(),
    }


def _validate_chapter(payload):
    """Check the parsed chapter has the right shape; normalise it. Raises
    ValueError if anything essential is off, so the caller can retry or fall back.
    """
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("missing title")

    paragraphs = payload.get("paragraphs")
    if not isinstance(paragraphs, list):
        raise ValueError("paragraphs must be a list")
    paragraphs = [str(p).strip() for p in paragraphs if str(p).strip()]
    if not paragraphs:
        raise ValueError("paragraphs must not be empty")

    questions = payload.get("questions")
    if questions is None:
        questions = []
    if not isinstance(questions, list):
        raise ValueError("questions must be a list")
    # 0 questions is allowed now (content-adaptive); validate any that are present.
    questions = [_validate_question(q) for q in questions]

    return {
        "setting": str(payload.get("setting") or "").strip(),
        "title": title,
        "paragraphs": paragraphs,
        "summary": str(payload.get("summary") or "").strip(),
        "questions": questions,
    }


# --- Provider call (any OpenAI-compatible API) -----------------------------------

def _call_llm(messages, max_tokens=1200):
    """Make one chat-completion call to the configured provider and return the raw
    text. Translates SDK exceptions into a friendly LLMError.
    """
    client = OpenAI(
        base_url=llm_config.get_base_url(),
        api_key=llm_config.get_api_key(),
        timeout=REQUEST_TIMEOUT_SECONDS,
        default_headers={
            "HTTP-Referer": "http://localhost:5173",
            "X-Title": "Adaptive Science Storytelling",
        },
    )
    try:
        response = client.chat.completions.create(
            model=llm_config.get_model(),
            messages=messages,
            temperature=0.7,
            max_tokens=max_tokens,  # scales with the target chapter length
        )
    except APITimeoutError:
        raise LLMError("The AI service timed out. Please try again in a moment.")
    except RateLimitError:
        raise LLMError("The AI service is busy (rate limited). Please wait a few seconds and try again.")
    except AuthenticationError:
        raise LLMError("Invalid or missing API key. Check API_KEY in backend/.env.")
    except NotFoundError:
        raise LLMError(
            f"The model '{llm_config.get_model()}' is unavailable. Update MODEL in backend/.env "
            f"to a currently-available model."
        )
    except (APIConnectionError, APIError) as exc:
        status = getattr(exc, "status_code", None)
        if status == 404:
            raise LLMError(
                f"The model '{llm_config.get_model()}' is unavailable. Update MODEL in backend/.env "
                f"to a currently-available model."
            )
        raise LLMError("Could not reach the AI service. Check your connection and try again.")

    return response.choices[0].message.content or ""


def _page_citation(passage):
    """Human-readable page citation for one retrieved passage.

    The PRINTED folio is what a learner holding the book can turn to; the PDF page
    index is not, and in these books one PDF page frequently carries a two-page
    spread. A chunk also usually runs past the page it starts on, so a range is
    emitted whenever the start and end folios differ. Falls back to the numeric PDF
    page when the footer could not be parsed (about 11% of pages).
    """
    start = (passage.get("page_label_start") or "").strip()
    end = (passage.get("page_label_end") or "").strip()
    if start and end:
        return f"p. {start}" if start == end else f"pp. {start}-{end}"
    page = passage.get("page")
    return f"p. {page}" if page is not None else ""


def _passage_refs(passages):
    """Compact page/chapter refs (no full text) to store on the Chapter and return
    to the frontend as the chapter's `sources`."""
    return [{
        "source_file": p.get("source_file"),
        "page": p.get("page"),
        "page_citation": _page_citation(p),
        "chapter": p.get("chapter"),
        "section": p.get("section"),
    } for p in passages]


def _max_tokens_for(max_paragraphs, max_questions):
    """Scale the token cap with the target chapter length so long chapters aren't
    truncated. The cap is deliberately generous and model-agnostic: unused headroom
    costs nothing (billing is per token actually generated), and some models spend
    part of the budget on hidden "thinking" tokens before the visible JSON —
    GPT-5-class minis do this by default; Gemini/DeepSeek when thinking is enabled.
    """
    estimate = 1600 + max_paragraphs * 250 + max_questions * 200
    return max(2400, min(4500, estimate))


# --- Public entry point ---------------------------------------------------------

def generate_chapter(topic, grade, difficulty, passages=None, *,
                     min_paragraphs=3, max_paragraphs=4, min_questions=1, max_questions=2,
                     setting=None, story_so_far=None, revisit_concepts=None, gate=False):
    """Return one story chapter as a dict:
        {setting, title, paragraphs (list), summary, questions [..], sources, in_syllabus}.

    Each question is {question, options (4), correct_index (0-3), hint, concept}.
    `sources` is the list of textbook page/chapter refs the chapter was grounded on
    (empty in mock mode, when the index isn't built, or on fallback).

    When `gate` is True (the first chapter, in live mode) the model first checks
    whether the topic is covered by the grade's textbook; if not, this returns
    {"in_syllabus": False, "reason": ...} INSTEAD of a chapter. Successful chapters
    carry "in_syllabus": True.

    `passages` are the textbook excerpts to ground THIS chapter in (from the session
    plan); if None it retrieves for the topic itself (legacy/fallback). The
    paragraph/question ranges come from the plan and the model picks exact counts.

    In mock mode returns a canned chapter (no retrieval, gate skipped). Otherwise it
    grounds on the supplied passages, asks the model to base its facts on them, and
    parses the reply robustly: it retries once asking for valid JSON, then falls back
    to a safe canned chapter rather than crashing. API/network problems raise
    LLMError, which the views surface as a friendly message.
    """
    # 1) Mock mode — no network/retrieval/scaling; trim canned questions to budget.
    if llm_config.use_mock():
        chapter = get_mock_chapter(topic, difficulty)
        chapter["sources"] = []  # RAG applies to live mode only
        chapter["in_syllabus"] = True
        chapter["questions"] = chapter["questions"][:max(0, max_questions)]
        return chapter

    # 2) Real mode needs a key.
    if not llm_config.get_api_key():
        raise LLMError(
            "No API_KEY set. Add it to backend/.env, or set USE_MOCK_LLM=true "
            "to develop without the network."
        )

    # Use the plan's passages for this chapter; only retrieve if none were supplied
    # (legacy/fallback). A retrieval problem must never break generation.
    if passages is None:
        from .retrieval import retrieve  # local import so mock mode never needs chromadb
        try:
            passages = retrieve(grade, topic, k=4)
        except Exception:
            passages = []

    # Gate: if nothing in this grade's textbook matches at all, refuse up front.
    if gate and not passages:
        return {
            "in_syllabus": False,
            "reason": f"We couldn't find \"{topic}\" in the Grade {grade} science textbook.",
        }

    messages = _build_chapter_messages(
        topic, grade, difficulty, setting, story_so_far, revisit_concepts or [], passages, gate,
        min_paragraphs, max_paragraphs, min_questions, max_questions,
    )
    max_tokens = _max_tokens_for(max_paragraphs, max_questions)

    # Try at most twice: once normally, once with a stern "JSON only" reminder.
    for attempt in range(2):
        if attempt == 1:
            messages = messages + [{
                "role": "user",
                "content": "Your previous reply was not valid JSON. Reply with ONLY the JSON object.",
            }]
        raw = _call_llm(messages, max_tokens=max_tokens)  # may raise LLMError
        try:
            payload = json.loads(_strip_to_json(raw))
        except json.JSONDecodeError:
            continue  # malformed — retry once, then fall back below

        # A gate refusal is a valid (non-error) outcome — return it without retrying.
        if gate and isinstance(payload, dict) and payload.get("in_syllabus") is False:
            return {
                "in_syllabus": False,
                "reason": str(payload.get("reason") or f"\"{topic}\" isn't in the Grade {grade} syllabus."),
            }

        try:
            result = _validate_chapter(payload)
        except ValueError:
            continue
        result["sources"] = _passage_refs(passages)  # attach grounding refs
        result["in_syllabus"] = True
        # If no setting was established yet, keep whatever the model invented.
        if not result["setting"] and setting:
            result["setting"] = setting
        return result

    # 3) Both attempts produced unparseable output: fall back to a canned chapter
    #    (trim questions to budget; treated as in-syllabus so the learner continues).
    chapter = get_mock_chapter(topic, difficulty)
    chapter["sources"] = []
    chapter["in_syllabus"] = True
    chapter["questions"] = chapter["questions"][:max(0, max_questions)]
    return chapter


# --- Grounded Q&A (Phase 5) -----------------------------------------------------

def answer_question(topic, grade, question, avoid_questions=None):
    """Answer a free question using ONLY the grade's textbook (RAG).

    Returns {answer, in_syllabus, sources}. Kept entirely separate from grading —
    callers must not let this change difficulty/points/streak/mastery. Off-syllabus
    questions are refused (in_syllabus False).

    `avoid_questions` (optional) is the anti-cheat backstop: the current chapter's
    still-unanswered quiz questions. The deterministic similarity gate in views.ask
    blocks near-verbatim copies before we get here; this instruction catches
    paraphrases of them, telling the model to explain the concept instead of
    handing over the answer.
    """
    if llm_config.use_mock():
        return {
            "answer": ("Grounded Q&A works in live mode (set USE_MOCK_LLM=false), where I answer "
                       "only from your grade's textbook. (This is a canned mock reply.)"),
            "in_syllabus": True,
            "sources": [],
        }

    if not llm_config.get_api_key():
        raise LLMError(
            "No API_KEY set. Add it to backend/.env, or set USE_MOCK_LLM=true."
        )

    from .retrieval import retrieve
    # Bias retrieval toward the session's topic by including it in the query.
    query = f"{topic}: {question}" if topic else question
    try:
        passages = retrieve(grade, query, k=4)
    except Exception:
        passages = []

    if not passages:
        return {
            "answer": f"I can only answer from the Grade {grade} science textbook, and I couldn't "
                      f"find this in it.",
            "in_syllabus": False,
            "sources": [],
        }

    system = (
        "You are a science teacher for Sri Lankan Grade 6-9 students. Answer the question ONLY "
        "using the provided textbook excerpts. If the excerpts do not contain the answer, say it "
        "is not covered in this grade's material. You ALWAYS respond with a single JSON object."
    )
    user = (
        f"Question: \"{question}\"\n\n"
        f"Answer for a Grade {grade} student using ONLY the excerpts below. If they do not cover "
        f"it, set in_syllabus to false and say so politely.\n\n"
        f"Respond with ONLY: {{\"in_syllabus\": boolean, \"answer\": \"2-4 clear sentences\"}}\n"
    )
    if avoid_questions:
        user += (
            "\nIMPORTANT: Do NOT reveal or directly answer any of these comprehension questions. "
            "If the user is clearly asking one of them, explain the underlying concept to help "
            "them reason it out, without giving the answer:\n- "
            + "\n- ".join(avoid_questions) + "\n"
        )
    user += "\nTEXTBOOK EXCERPTS:\n" + _format_passages(passages)

    # Generous cap (free unless used): leaves room for models that spend hidden
    # "thinking" tokens before the short visible answer.
    raw = _call_llm([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], max_tokens=2000)
    refs = _passage_refs(passages)
    try:
        payload = json.loads(_strip_to_json(raw))
        answer = str(payload.get("answer") or "").strip()
        if answer:
            return {"answer": answer, "in_syllabus": bool(payload.get("in_syllabus", True)), "sources": refs}
    except json.JSONDecodeError:
        pass
    # Fallback: a plain-text reply is still a usable answer for Q&A.
    return {"answer": raw.strip() or "Sorry, I couldn't answer that just now.",
            "in_syllabus": True, "sources": refs}


# --- TODO (future work): AI image generation -----------------------------------
# A future version could generate an illustration for each chapter to make it more
# engaging for younger learners. This is intentionally NOT built for the MVP — it is
# left here only as a clearly-marked hook. A real implementation would call an image
# model and store the result URL on the Chapter (a new field), then show it on screen.
#
# def generate_chapter_image(paragraphs):
#     """Return an illustration for the chapter. Not implemented yet."""
#     raise NotImplementedError("Image generation is future work, out of scope for the MVP.")
