"""DRF serializers: convert model instances to JSON for the API responses.

Two views of a Question/Chapter:
  * Presented* — the SAFE subset sent to the browser while answering (no
    correct_index, hint or concept), so answers can't be cheated.
  * full serializers — include the answer key + the learner's response, used only
    by GET /sessions/<id> as evidence that data is being logged.
"""

from rest_framework import serializers

from .models import Badge, Chapter, Question, Session


# --- Presented (safe) shapes sent while the learner is answering ----------------

class PresentedQuestionSerializer(serializers.ModelSerializer):
    question_id = serializers.IntegerField(source="id")
    question = serializers.CharField(source="question_text")

    class Meta:
        model = Question
        fields = ["question_id", "order", "question", "options"]


class PresentedChapterSerializer(serializers.ModelSerializer):
    chapter_id = serializers.IntegerField(source="id")
    questions = PresentedQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Chapter
        fields = ["chapter_id", "order", "title", "paragraphs", "questions"]


# --- Full shapes for the evidence/full-state view ------------------------------

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = [
            "id", "order", "question_text", "options", "correct_index", "hint",
            "concept", "user_answer_index", "is_correct", "response_time_ms", "created_at",
        ]


class ChapterSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Chapter
        fields = [
            "id", "order", "title", "paragraphs", "summary",
            "difficulty_at_time", "sources", "questions", "created_at",
        ]


class BadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = ["name", "awarded_at"]


class SessionSerializer(serializers.ModelSerializer):
    """Full session state with all chapters, questions and badges nested — the
    evidence of data logging used by GET /api/sessions/<id>."""

    learner_name = serializers.CharField(source="learner.name", read_only=True)
    chapters = ChapterSerializer(many=True, read_only=True)
    badges = BadgeSerializer(many=True, read_only=True)

    class Meta:
        model = Session
        fields = [
            "id", "learner_name", "topic", "grade", "difficulty", "points",
            "current_streak", "chapter_count", "setting", "is_complete", "created_at",
            "chapters", "badges",
        ]
