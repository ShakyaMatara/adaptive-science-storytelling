"""Gamification: award badges based on session state.

Badges are simple, motivating milestones, awarded at most once per session. They
are awarded at chapter boundaries (when the learner moves to the next chapter or
finishes), so the caller passes in whether the just-finished chapter had any
correct answer and whether the session is now complete.
"""

from .models import Badge

# Badge names (kept as constants so the rules below read clearly).
FIRST_STEPS = "First Steps"      # first correct answer in the session
ON_FIRE = "On Fire"              # reached a 3-in-a-row correct streak
STREAK_FOR_ON_FIRE = 3
EXPLORER_SUFFIX = "Explorer"     # e.g. "Water Cycle Explorer" on completion


def award_badges(session, had_correct, is_complete):
    """Create Badge rows for any milestones newly reached, and return their names.

    `had_correct` = did the chapter just finished contain at least one correct
    answer (used for "First Steps"). `session.current_streak` must be up to date.
    """
    already_earned = set(session.badges.values_list("name", flat=True))
    newly_awarded = []

    # "First Steps": the learner's first correct answer in the session.
    if had_correct and FIRST_STEPS not in already_earned:
        newly_awarded.append(FIRST_STEPS)

    # "On Fire": a streak of 3 correct answers in a row.
    if session.current_streak >= STREAK_FOR_ON_FIRE and ON_FIRE not in already_earned:
        newly_awarded.append(ON_FIRE)

    # "<Topic> Explorer": finished the whole session.
    if is_complete:
        explorer = f"{session.topic} {EXPLORER_SUFFIX}"
        if explorer not in already_earned:
            newly_awarded.append(explorer)

    for name in newly_awarded:
        Badge.objects.create(session=session, name=name)

    return newly_awarded
