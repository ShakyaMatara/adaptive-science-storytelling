"""Pedagogical engine: simple, transparent rules that award points and adapt
difficulty. Rule-based (not ML) so it is easy to explain and defend.

Two timescales now:
  * per QUESTION  -> award points and update the correct-answer streak.
  * per CHAPTER   -> nudge difficulty based on how the whole chapter went.
"""

# --- Tunable thresholds (kept together and named so the rules are easy to read) ---
START_DIFFICULTY = 3   # every session starts in the middle of the 1-5 range
MIN_DIFFICULTY = 1     # easiest
MAX_DIFFICULTY = 5     # hardest
MIN_CHAPTERS = 1       # a session is at least this many chapters
MAX_CHAPTERS_CAP = 6   # ...and at most this many (safety bound; the real count comes from the content plan)
POINTS_PER_DIFFICULTY = 10  # a correct answer is worth 10 x (current difficulty)

# Chapter score thresholds for changing difficulty between chapters.
CHAPTER_UP_THRESHOLD = 0.75    # >= this fraction correct -> harder
CHAPTER_DOWN_THRESHOLD = 0.25  # <= this fraction correct -> easier


def points_for_correct(difficulty):
    """Points for a correct answer at the given difficulty (harder = worth more)."""
    return POINTS_PER_DIFFICULTY * difficulty


def score_question(session, is_correct):
    """Per-question update: award points and update the consecutive-correct streak.

    Difficulty does NOT change here — that happens once per chapter (see below).
    Returns the points awarded for this question. Does not save.
    """
    if is_correct:
        points_awarded = points_for_correct(session.difficulty)
        session.points += points_awarded
        session.current_streak += 1
    else:
        points_awarded = 0
        session.current_streak = 0
    return points_awarded


def adjust_difficulty_for_chapter(session, correct, total):
    """Between chapters: nudge difficulty from the chapter score (correct/total).

    >= 75% correct -> one step harder; <= 25% -> one step easier; otherwise hold.
    A chapter with NO questions gives no signal, so difficulty is left unchanged.
    Mutates session.difficulty in place and returns the score (None if no questions).
    Does not save.
    """
    if total == 0:
        return None  # no questions answered -> no signal -> no difficulty change
    score = correct / total
    if score >= CHAPTER_UP_THRESHOLD:
        session.difficulty = min(MAX_DIFFICULTY, session.difficulty + 1)
    elif score <= CHAPTER_DOWN_THRESHOLD:
        session.difficulty = max(MIN_DIFFICULTY, session.difficulty - 1)
    return score
