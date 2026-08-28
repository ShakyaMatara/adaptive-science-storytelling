"""URL routes for the core API. Included under the /api/ prefix by config/urls.py."""

from django.urls import path

from . import (
    api_achievements,
    api_curriculum,
    api_fallback,
    api_library,
    api_progress,
    api_provenance,
    api_revision,
    views,
)

urlpatterns = [
    # Authentication
    path("auth/register", views.register),
    path("auth/login", views.login),
    path("auth/me", views.me),
    path("me/progress", api_progress.me_progress),
    path("me/library", api_library.library),
    path("me/weak-concepts", api_revision.weak_concepts),
    path("me/achievements", api_achievements.achievements),

    # Curriculum
    path("curriculum", api_curriculum.curriculum),

    # Chapter-level surfaces
    path("chapters/<int:chapter_id>/provenance", api_provenance.provenance),
    path("chapters/<int:chapter_id>/generation-status", api_fallback.generation_status),

    # Topics & sessions
    path("topics", views.topics),
    path("sessions", views.create_session),
    path("sessions/<int:session_id>/answer", views.answer),
    path("sessions/<int:session_id>/next", views.next_chapter),
    path("sessions/<int:session_id>/finish", views.finish_session),
    path("sessions/<int:session_id>/ask", views.ask),
    path("sessions/<int:session_id>/chapters/<int:chapter_id>/retry", api_fallback.retry_chapter),
    path("sessions/<int:session_id>", views.get_session),
]
