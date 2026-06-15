"""URL routes for the core API. Included under the /api/ prefix by config/urls.py."""

from django.urls import path

from . import views

urlpatterns = [
    # Authentication
    path("auth/register", views.register),
    path("auth/login", views.login),
    path("auth/me", views.me),
    path("me/progress", views.me_progress),

    # Topics & sessions
    path("topics", views.topics),
    path("sessions", views.create_session),
    path("sessions/<int:session_id>/answer", views.answer),
    path("sessions/<int:session_id>/next", views.next_chapter),
    path("sessions/<int:session_id>/finish", views.finish_session),
    path("sessions/<int:session_id>/ask", views.ask),
    path("sessions/<int:session_id>", views.get_session),
]
