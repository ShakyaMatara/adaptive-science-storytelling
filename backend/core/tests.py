"""End-to-end API tests, run against MOCK mode so they need no network or key.

These double as the "does it work?" verification for the backend and as a record
of the expected story-loop / adaptation / gamification behaviour.
"""

import os
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from . import adaptation
from .models import ConceptStat, Learner, Question, Session
from .throttles import AskThrottle, StoryGenThrottle


class StoryLoopTests(APITestCase):
    def setUp(self):
        # Force canned content so tests are deterministic and offline.
        os.environ["USE_MOCK_LLM"] = "true"
        # Throttle history lives in the (process-wide) cache and is keyed by user pk,
        # which SQLite reuses across tests — clear it so tests can't 429 each other.
        cache.clear()
        # All session endpoints require auth; log a learner in for the tests.
        self.user = User.objects.create_user(username="nimal", password="pw12345!")
        Learner.objects.create(user=self.user, name="Nimal")
        self.client.force_authenticate(user=self.user)

    # --- helpers ---------------------------------------------------------------

    def _start(self, topic="Water Cycle", grade=7):
        res = self.client.post(
            "/api/sessions", {"topic": topic, "grade": grade}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        return res.data

    def _answer_chapter(self, session_id, chapter, correct=True):
        """Answer every question in a chapter; return the last answer response."""
        last = None
        for q in chapter["questions"]:
            ci = Question.objects.get(pk=q["question_id"]).correct_index
            ans = ci if correct else (ci + 1) % 4
            last = self.client.post(
                f"/api/sessions/{session_id}/answer",
                {"question_id": q["question_id"], "answer_index": ans},
                format="json",
            ).data
        return last

    def _next(self, session_id):
        return self.client.post(f"/api/sessions/{session_id}/next", {}, format="json").data

    def _play_session(self, topic, correct):
        """Play a whole session through to completion, all correct or all wrong."""
        data = self._start(topic=topic)
        session_id = data["session_id"]
        chapter = data["chapter"]
        for _ in range(10):  # safety bound
            self._answer_chapter(session_id, chapter, correct=correct)
            nxt = self._next(session_id)
            if nxt["is_complete"]:
                break
            chapter = nxt["chapter"]
        return session_id

    # --- story structure -------------------------------------------------------

    def test_start_returns_a_chapter(self):
        data = self._start()
        self.assertIn("session_id", data)
        chapter = data["chapter"]
        self.assertIn("chapter_id", chapter)
        self.assertTrue(chapter["title"])
        self.assertGreaterEqual(len(chapter["paragraphs"]), 1)   # multi-paragraph
        self.assertGreaterEqual(len(chapter["questions"]), 1)
        q0 = chapter["questions"][0]
        self.assertEqual(len(q0["options"]), 4)
        # The answer key / concept must NOT be leaked to the client.
        self.assertNotIn("correct_index", q0)
        self.assertNotIn("hint", q0)
        self.assertNotIn("concept", q0)
        self.assertEqual(data["sources"], [])  # mock mode = no RAG
        self.assertFalse(data["chapter_complete"])  # this chapter has questions to answer

    def test_answer_marks_chapter_complete_when_all_answered(self):
        data = self._start()
        chapter = data["chapter"]
        questions = chapter["questions"]
        # Answer all but the last -> not complete; last -> complete.
        for q in questions[:-1]:
            res = self.client.post(
                f"/api/sessions/{data['session_id']}/answer",
                {"question_id": q["question_id"], "answer_index": 0}, format="json").data
            self.assertFalse(res["chapter_complete"])
        last_q = questions[-1]
        res = self.client.post(
            f"/api/sessions/{data['session_id']}/answer",
            {"question_id": last_q["question_id"], "answer_index": 0}, format="json").data
        self.assertTrue(res["chapter_complete"])

    def test_next_requires_chapter_to_be_finished(self):
        data = self._start()
        res = self.client.post(f"/api/sessions/{data['session_id']}/next", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_full_correct_run_completes_with_points_and_badges(self):
        data = self._start(topic="Photosynthesis")
        session_id = data["session_id"]
        chapter = data["chapter"]
        awarded = []
        last_next = None

        for _ in range(10):  # safety bound; should finish in MAX_CHAPTERS
            self._answer_chapter(session_id, chapter, correct=True)
            last_next = self._next(session_id)
            awarded += last_next.get("badges_awarded", [])
            if last_next["is_complete"]:
                break
            chapter = last_next["chapter"]

        self.assertTrue(last_next["is_complete"])
        self.assertIsNone(last_next["chapter"])
        self.assertEqual(last_next["difficulty"], 5)  # all-correct climbs and caps at 5
        # Mock plan = 2 chapters x 2 correct, answered at difficulties 3 then 4 -> 60 + 80 = 140.
        self.assertEqual(last_next["points"], 140)
        self.assertIn("First Steps", awarded)
        self.assertIn("On Fire", awarded)
        self.assertIn("Photosynthesis Explorer", awarded)

        # Full-state endpoint shows all chapters/questions answered (data logging).
        full = self.client.get(f"/api/sessions/{session_id}").data
        self.assertEqual(len(full["chapters"]), 2)
        self.assertTrue(full["is_complete"])

    def test_wrong_chapter_lowers_difficulty(self):
        data = self._start()
        chapter = data["chapter"]
        self._answer_chapter(data["session_id"], chapter, correct=False)
        nxt = self._next(data["session_id"])
        self.assertEqual(nxt["difficulty"], 2)  # 3 -> 2 after a 0% chapter

    # --- content-adaptive length (Phase B) -------------------------------------

    def test_zero_question_chapter_keeps_difficulty(self):
        # A chapter with no questions gives no signal -> difficulty must not change.
        sess = Session(difficulty=3)
        result = adaptation.adjust_difficulty_for_chapter(sess, correct=0, total=0)
        self.assertIsNone(result)
        self.assertEqual(sess.difficulty, 3)

    def test_zero_question_chapter_is_immediately_continuable(self):
        thin = {"setting": "S", "title": "Thin topic", "paragraphs": ["p1", "p2"],
                "summary": "s", "questions": [], "sources": [], "in_syllabus": True}
        with patch("core.views.generate_chapter", return_value=thin):
            data = self._start(topic="Rheostat")
        self.assertEqual(data["chapter"]["questions"], [])   # no questions rendered
        self.assertTrue(data["chapter_complete"])            # ...but Continue is available

    # --- auth ------------------------------------------------------------------

    def test_register_returns_token_and_profile(self):
        res = self.client.post(
            "/api/auth/register",
            {"username": "amaya", "password": "pw12345!", "display_name": "Amaya"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", res.data)
        self.assertEqual(res.data["profile"]["display_name"], "Amaya")

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        res = self.client.post(
            "/api/sessions", {"topic": "water-cycle", "grade": 7}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cannot_access_another_users_session(self):
        data = self._start()
        other = User.objects.create_user(username="mara", password="pw12345!")
        Learner.objects.create(user=other, name="Mara")
        self.client.force_authenticate(user=other)
        res = self.client.get(f"/api/sessions/{data['session_id']}")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # --- syllabus gate (Phase 3) -----------------------------------------------

    def test_empty_topic_is_rejected(self):
        res = self.client.post("/api/sessions", {"topic": "", "grade": 7}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_off_syllabus_topic_is_refused_without_creating_a_session(self):
        before = Session.objects.count()
        refusal = {"in_syllabus": False, "reason": "Black holes aren't in the Grade 7 syllabus."}
        # The gate is live-only, so simulate the model's refusal deterministically.
        with patch("core.views.generate_chapter", return_value=refusal):
            res = self.client.post(
                "/api/sessions", {"topic": "Black holes", "grade": 7}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["in_syllabus"])
        self.assertIn("reason", res.data)
        self.assertEqual(Session.objects.count(), before)  # nothing was created

    # --- personalisation (Phase 4) ---------------------------------------------

    def test_concept_stats_recorded_on_answer(self):
        data = self._start(topic="Water Cycle")
        sid = data["session_id"]
        qs = data["chapter"]["questions"]
        q0 = Question.objects.get(pk=qs[0]["question_id"])
        self.client.post(f"/api/sessions/{sid}/answer",
                         {"question_id": q0.id, "answer_index": q0.correct_index}, format="json")
        q1 = Question.objects.get(pk=qs[1]["question_id"])
        self.client.post(f"/api/sessions/{sid}/answer",
                         {"question_id": q1.id, "answer_index": (q1.correct_index + 1) % 4}, format="json")
        s0 = ConceptStat.objects.get(learner__user=self.user, topic="Water Cycle", concept=q0.concept)
        self.assertEqual((s0.attempts, s0.correct), (1, 1))
        s1 = ConceptStat.objects.get(learner__user=self.user, topic="Water Cycle", concept=q1.concept)
        self.assertEqual((s1.attempts, s1.correct), (1, 0))

    def test_returning_learner_starts_easier_after_a_poor_session(self):
        self._play_session("Water Cycle", correct=False)  # mastery -> 0
        data2 = self._start(topic="Water Cycle")
        self.assertEqual(data2["difficulty"], 2)

    def test_returning_learner_starts_harder_after_a_strong_session(self):
        self._play_session("Photosynthesis", correct=True)  # mastery -> 1.0
        data2 = self._start(topic="Photosynthesis")
        self.assertEqual(data2["difficulty"], 4)

    def test_progress_endpoint_reports_mastery(self):
        self._play_session("Water Cycle", correct=True)
        res = self.client.get("/api/me/progress")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        topics = [p["topic"] for p in res.data["progress"]]
        self.assertIn("Water Cycle", topics)
        self.assertTrue(any(c["attempts"] >= 1 for p in res.data["progress"] for c in p["concepts"]))

    # --- grounded Q&A (Phase 5) ------------------------------------------------

    def test_ask_returns_answer_without_changing_session_state(self):
        data = self._start(topic="Water Cycle")
        sid = data["session_id"]
        res = self.client.post(
            f"/api/sessions/{sid}/ask", {"question": "What is evaporation?"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("answer", res.data)
        self.assertIn("in_syllabus", res.data)
        self.assertIn("sources", res.data)
        # Asking must NOT change grading state.
        s = Session.objects.get(pk=sid)
        self.assertEqual(s.points, data["points"])
        self.assertEqual(s.difficulty, data["difficulty"])

    def test_ask_requires_a_question(self):
        data = self._start()
        res = self.client.post(
            f"/api/sessions/{data['session_id']}/ask", {"question": ""}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # --- cross-session story memory (Phase C) ----------------------------------

    def test_returning_to_unfinished_topic_resumes_same_session(self):
        data = self._start(topic="Water Cycle")
        sid = data["session_id"]
        q0 = data["chapter"]["questions"][0]
        ci = Question.objects.get(pk=q0["question_id"]).correct_index
        self.client.post(f"/api/sessions/{sid}/answer",
                         {"question_id": q0["question_id"], "answer_index": ci}, format="json")
        before = Session.objects.count()

        res = self.client.post("/api/sessions", {"topic": "Water Cycle", "grade": 7}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)   # resumed, not created (201)
        self.assertTrue(res.data.get("resumed"))
        self.assertEqual(res.data["session_id"], sid)           # the same story
        self.assertEqual(Session.objects.count(), before)       # no new session created
        self.assertEqual(res.data["points"], 30)                # preserved (1 correct at difficulty 3)
        self.assertIn(q0["question_id"], res.data["answers"])    # prior answer rehydrated

    def test_start_reports_total_chapters(self):
        data = self._start()
        self.assertEqual(data["total_chapters"], 2)  # mock plan = 2 chapters

    def test_finish_early_completes_session_and_awards_badge(self):
        data = self._start(topic="Water Cycle")
        sid = data["session_id"]
        # Make a little progress so there are points and a badge.
        q0 = data["chapter"]["questions"][0]
        ci = Question.objects.get(pk=q0["question_id"]).correct_index
        self.client.post(f"/api/sessions/{sid}/answer",
                         {"question_id": q0["question_id"], "answer_index": ci}, format="json")

        res = self.client.post(f"/api/sessions/{sid}/finish", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_complete"])
        self.assertEqual(res.data["points"], 30)                 # preserved (1 correct at difficulty 3)
        self.assertIn("Water Cycle Explorer", res.data["badges"])  # completion badge awarded
        self.assertTrue(Session.objects.get(pk=sid).is_complete)
        # Finishing again is rejected.
        again = self.client.post(f"/api/sessions/{sid}/finish", {}, format="json")
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)

    def test_completed_topic_starts_a_fresh_story(self):
        sid1 = self._play_session("Water Cycle", correct=True)  # play it to completion
        res = self.client.post("/api/sessions", {"topic": "Water Cycle", "grade": 7}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)  # a brand-new run
        self.assertNotEqual(res.data["session_id"], sid1)
        self.assertFalse(res.data.get("resumed", False))

    # --- Q&A anti-cheat ----------------------------------------------------------

    def test_ask_blocks_an_active_quiz_question(self):
        data = self._start(topic="Water Cycle")
        sid = data["session_id"]
        quiz_text = data["chapter"]["questions"][0]["question"]
        res = self.client.post(f"/api/sessions/{sid}/ask", {"question": quiz_text}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get("blocked"))                 # refused by the gate
        self.assertIn("best try", res.data["answer"])            # friendly refusal text
        self.assertEqual(res.data["sources"], [])                # normal response shape

    def test_ask_allows_a_quiz_question_after_it_is_answered(self):
        data = self._start(topic="Water Cycle")
        sid = data["session_id"]
        # Answer every question in the chapter, then ask one of them.
        self._answer_chapter(sid, data["chapter"], correct=True)
        quiz_text = data["chapter"]["questions"][0]["question"]
        res = self.client.post(f"/api/sessions/{sid}/ask", {"question": quiz_text}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data.get("blocked", False))         # no longer gated

    def test_ask_allows_an_unrelated_question(self):
        data = self._start(topic="Water Cycle")
        res = self.client.post(
            f"/api/sessions/{data['session_id']}/ask",
            {"question": "Why do farmers in Kandy grow rice in paddy fields?"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data.get("blocked", False))

    # --- rate limiting -------------------------------------------------------------

    def test_ask_is_rate_limited(self):
        data = self._start(topic="Water Cycle")
        sid = data["session_id"]
        # Tighten the burst rate to 2/min for this test only (rates are read from the
        # class attribute at each request, so patching it takes effect immediately).
        with patch.object(AskThrottle, "THROTTLE_RATES", {"ask": "2/min"}):
            for q in ("Why does mist form?", "Where does rain go?"):
                ok = self.client.post(f"/api/sessions/{sid}/ask", {"question": q}, format="json")
                self.assertEqual(ok.status_code, status.HTTP_200_OK)
            blocked = self.client.post(
                f"/api/sessions/{sid}/ask", {"question": "What are clouds made of?"}, format="json")
        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        cache.clear()  # drop this test's throttle history

    def test_session_creation_is_rate_limited(self):
        with patch.object(StoryGenThrottle, "THROTTLE_RATES", {"story_gen": "1/min"}):
            first = self.client.post(
                "/api/sessions", {"topic": "Water Cycle", "grade": 7}, format="json")
            self.assertEqual(first.status_code, status.HTTP_201_CREATED)
            second = self.client.post(
                "/api/sessions", {"topic": "Photosynthesis", "grade": 8}, format="json")
        self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        cache.clear()  # drop this test's throttle history
