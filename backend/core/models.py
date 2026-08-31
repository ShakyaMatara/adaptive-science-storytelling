"""Data layer: learners (linked to auth users), their sessions, the story
chapters + comprehension questions they answer, and the badges they earn.

A session is now a short continuous story told over several CHAPTERS. Each chapter
is a titled, multi-paragraph scene followed by a few questions; difficulty adapts
between chapters. Everything is persisted so progress is tied to an account and the
data can be analysed later.
"""

from django.conf import settings
from django.db import models


class Learner(models.Model):
    """A learner's profile, linked one-to-one to a Django auth User.

    Authentication itself (username + securely hashed password) lives on Django's
    built-in User model; this holds the app-specific profile and owns the sessions.
    """

    # null=True keeps old dev rows valid and lets a non-app user (e.g. a superuser)
    # get a profile lazily; every account from /api/auth/register has one.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, related_name="learner"
    )
    name = models.CharField(max_length=100)  # display name
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Session(models.Model):
    """One run-through of a topic by a learner: a continuous, multi-chapter story.

    Holds the live state the adaptation and gamification rules read and update:
    current difficulty, points, the consecutive-correct-answer streak, how many
    chapters have been generated, the persistent story `setting` (for continuity),
    and whether the run has finished.
    """

    learner = models.ForeignKey(Learner, on_delete=models.CASCADE, related_name="sessions")
    topic = models.CharField(max_length=100)  # the topic the learner chose, e.g. "Water Cycle"
    grade = models.IntegerField(default=6)    # 6..9; chooses which grade's textbook RAG uses
    difficulty = models.IntegerField(default=3)      # 1 (easiest) .. 5 (hardest)
    points = models.IntegerField(default=0)
    current_streak = models.IntegerField(default=0)  # consecutive correct QUESTIONS (for "On Fire")
    chapter_count = models.IntegerField(default=0)   # chapters generated so far
    setting = models.TextField(null=True, blank=True)  # persistent characters/place for continuity
    # Content-driven plan: how rich the topic is, and the ordered list of
    # section groups (each with its passages + paragraph/question ranges) to cover.
    content_level = models.CharField(max_length=20, blank=True, default="")
    plan = models.JSONField(null=True, blank=True)
    is_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.learner.name} - {self.topic} (session {self.pk})"


class Chapter(models.Model):
    """A titled, multi-paragraph scene in the session's continuous story."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="chapters")
    order = models.IntegerField()  # 1-based position within the session
    title = models.CharField(max_length=200)
    paragraphs = models.JSONField()           # list of paragraph strings (~3)
    summary = models.TextField(blank=True)    # 1-2 sentences carried into the next chapter
    difficulty_at_time = models.IntegerField()  # difficulty this chapter was made at
    sources = models.JSONField(null=True, blank=True)  # RAG textbook refs (empty in mock mode)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Session {self.session_id} - chapter {self.order}: {self.title}"


class Question(models.Model):
    """One comprehension question attached to a chapter (a chapter has a few).

    `correct_index`, `hint` and `concept` are kept server-side and never sent to the
    browser before the learner answers, so answers can't leak. `concept` is a short
    label of what the question tests (e.g. "evaporation") — used to revisit weak
    spots and, later, to track concept mastery.
    """

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="questions")
    order = models.IntegerField()  # 1-based position within the chapter

    question_text = models.TextField()
    options = models.JSONField()           # list of exactly 4 answer strings
    correct_index = models.IntegerField()  # 0..3, index into `options`
    hint = models.TextField(null=True, blank=True)
    concept = models.CharField(max_length=100, blank=True)  # short concept label

    # Learner's response (null until answered)
    user_answer_index = models.IntegerField(null=True, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    response_time_ms = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Chapter {self.chapter_id} - question {self.order}"


class Badge(models.Model):
    """A gamification reward earned during a session.

    Stored per-session for the MVP. It could be promoted to per-Learner later
    (e.g. a ForeignKey to Learner) so achievements persist across sessions.
    """

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="badges")
    name = models.CharField(max_length=100)
    awarded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (session {self.session_id})"


class ConceptStat(models.Model):
    """Per-learner mastery of one concept within a topic, aggregated across ALL of
    that learner's sessions. Updated every time a question with that concept is
    answered. Drives cross-session personalisation: revisiting weak concepts and
    choosing an adaptive starting difficulty for a returning learner.
    """

    learner = models.ForeignKey(Learner, on_delete=models.CASCADE, related_name="concept_stats")
    topic = models.CharField(max_length=100)
    concept = models.CharField(max_length=100)
    attempts = models.IntegerField(default=0)
    correct = models.IntegerField(default=0)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("learner", "topic", "concept")

    @property
    def mastery(self):
        """Fraction correct (0.0-1.0); 0 if never attempted."""
        return (self.correct / self.attempts) if self.attempts else 0.0

    def __str__(self):
        return f"{self.learner.name}: {self.topic}/{self.concept} {self.correct}/{self.attempts}"


class GenerationEvent(models.Model):
    """A record of a chapter whose generation did not go to plan.

    When the model's reply fails schema validation twice, the generator returns a
    canned chapter rather than raising, so the learner is never blocked. That
    fallback is correct behaviour and is kept — but it used to be invisible, and
    the evaluation programme measured it at 2.8% of chapters. This model is what
    makes the rate observable in ordinary use rather than only under measurement:
    one row per chapter that fell back, plus a row for the outcome of any retry
    the learner asked for.
    """

    FALLBACK_SERVED = "fallback_served"
    RETRY_SUCCEEDED = "retry_succeeded"
    RETRY_FAILED = "retry_failed"
    KIND_CHOICES = [
        (FALLBACK_SERVED, "Canned chapter served instead of a generated one"),
        (RETRY_SUCCEEDED, "Retry produced a textbook-grounded chapter"),
        (RETRY_FAILED, "Retry fell back again; the original chapter was kept"),
    ]

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="generation_events")
    chapter = models.ForeignKey(
        Chapter, on_delete=models.CASCADE, related_name="generation_events", null=True, blank=True
    )
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    detail = models.TextField(blank=True)  # a short human-readable note, never an error dump
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} (session {self.session_id}, chapter {self.chapter_id})"
