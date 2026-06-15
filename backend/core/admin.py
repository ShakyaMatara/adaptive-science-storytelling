"""Register the models in Django's admin so the saved data can be browsed at
/admin (useful as evidence of data logging during the demo/viva)."""

from django.contrib import admin

from .models import Badge, Chapter, ConceptStat, Learner, Question, Session


@admin.register(Learner)
class LearnerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "created_at")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("id", "learner", "topic", "grade", "difficulty", "points",
                    "current_streak", "chapter_count", "is_complete")


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "order", "title", "difficulty_at_time")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "chapter", "order", "concept", "user_answer_index", "is_correct")


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "name", "awarded_at")


@admin.register(ConceptStat)
class ConceptStatAdmin(admin.ModelAdmin):
    list_display = ("id", "learner", "topic", "concept", "correct", "attempts", "last_seen")
