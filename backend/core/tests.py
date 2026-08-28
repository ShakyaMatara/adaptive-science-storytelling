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
from . import api_curriculum
from .models import (
    Badge, Chapter, ConceptStat, GenerationEvent, Learner, Question, Session,
)
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


class EndToEndSmokeTests(APITestCase):
    """The whole existing learner journey in one test, driven only through HTTP
    with a real token: register -> start -> read -> answer -> next chapter -> ask
    -> resume -> finish.

    It exists as the regression gate for the user-facing expansion: the new pages
    are surfaces over this flow, so if any of them disturbs it this fails.
    """

    def setUp(self):
        os.environ["USE_MOCK_LLM"] = "true"
        cache.clear()

    def test_full_journey_through_the_api(self):
        # 1. Register — this is the only call made unauthenticated.
        reg = self.client.post(
            "/api/auth/register",
            {"username": "amaya", "password": "pw12345!", "display_name": "Amaya"},
            format="json")
        self.assertEqual(reg.status_code, status.HTTP_201_CREATED)
        token = reg.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

        # 2. The token identifies the learner.
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["display_name"], "Amaya")

        # 3. Start a story.
        started = self.client.post(
            "/api/sessions", {"topic": "Water Cycle", "grade": 7}, format="json")
        self.assertEqual(started.status_code, status.HTTP_201_CREATED)
        sid = started.data["session_id"]
        chapter = started.data["chapter"]
        self.assertTrue(chapter["paragraphs"])
        self.assertTrue(chapter["questions"])

        # 4. Read the story back in full.
        full = self.client.get(f"/api/sessions/{sid}")
        self.assertEqual(full.status_code, status.HTTP_200_OK)
        self.assertEqual(len(full.data["chapters"]), 1)
        self.assertEqual(full.data["topic"], "Water Cycle")

        # 5. Answer every question in the chapter, correctly.
        for q in chapter["questions"]:
            ci = Question.objects.get(pk=q["question_id"]).correct_index
            res = self.client.post(
                f"/api/sessions/{sid}/answer",
                {"question_id": q["question_id"], "answer_index": ci, "response_time_ms": 1200},
                format="json")
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertTrue(res.data["is_correct"])
        self.assertTrue(res.data["chapter_complete"])

        # 6. Move to the next chapter.
        nxt = self.client.post(f"/api/sessions/{sid}/next", {}, format="json")
        self.assertEqual(nxt.status_code, status.HTTP_200_OK)
        self.assertFalse(nxt.data["is_complete"])
        chapter2 = nxt.data["chapter"]
        self.assertEqual(chapter2["order"], 2)

        # 7. Ask a grounded question — it must not disturb the session state.
        points_before = nxt.data["points"]
        asked = self.client.post(
            f"/api/sessions/{sid}/ask", {"question": "Why does mist form?"}, format="json")
        self.assertEqual(asked.status_code, status.HTTP_200_OK)
        self.assertTrue(asked.data["answer"])
        self.assertEqual(Session.objects.get(pk=sid).points, points_before)

        # 8. Coming back to the same topic resumes the same story, not a new one.
        before = Session.objects.count()
        resumed = self.client.post(
            "/api/sessions", {"topic": "Water Cycle", "grade": 7}, format="json")
        self.assertEqual(resumed.status_code, status.HTTP_200_OK)
        self.assertTrue(resumed.data["resumed"])
        self.assertEqual(resumed.data["session_id"], sid)
        self.assertEqual(Session.objects.count(), before)

        # 9. Finish the story off and collect the completion badge.
        for q in chapter2["questions"]:
            ci = Question.objects.get(pk=q["question_id"]).correct_index
            self.client.post(
                f"/api/sessions/{sid}/answer",
                {"question_id": q["question_id"], "answer_index": ci}, format="json")
        done = self.client.post(f"/api/sessions/{sid}/next", {}, format="json")
        self.assertTrue(done.data["is_complete"])
        self.assertIn("Water Cycle Explorer", done.data["badges"])
        self.assertGreater(done.data["points"], 0)


class NewSurfaceTests(APITestCase):
    """The endpoints behind the pages added in the capability expansion.

    Every one of them is a read-only surface over data the system already keeps,
    so what matters is that each requires a token, refuses another learner's
    data, returns the shape its page consumes, and behaves sensibly for a learner
    with no history at all.
    """

    def setUp(self):
        os.environ["USE_MOCK_LLM"] = "true"
        cache.clear()
        self.user = User.objects.create_user(username="nimal", password="pw12345!")
        Learner.objects.create(user=self.user, name="Nimal")
        # A second learner, used to prove one learner cannot read another's data.
        self.other = User.objects.create_user(username="amaya", password="pw12345!")
        Learner.objects.create(user=self.other, name="Amaya")
        self.client.force_authenticate(user=self.user)

    def _play_one_chapter(self, topic="Water Cycle", grade=7, correct=True):
        """Start a story and answer its first chapter; return (session_id, chapter)."""
        data = self.client.post(
            "/api/sessions", {"topic": topic, "grade": grade}, format="json").data
        sid, chapter = data["session_id"], data["chapter"]
        for q in chapter["questions"]:
            ci = Question.objects.get(pk=q["question_id"]).correct_index
            self.client.post(
                f"/api/sessions/{sid}/answer",
                {"question_id": q["question_id"],
                 "answer_index": ci if correct else (ci + 1) % 4},
                format="json")
        return sid, chapter

    # --- authentication --------------------------------------------------------

    def test_every_new_endpoint_requires_authentication(self):
        self.client.force_authenticate(user=None)
        for path in ("/api/curriculum", "/api/me/library", "/api/me/progress",
                     "/api/me/weak-concepts", "/api/me/achievements",
                     "/api/chapters/1/provenance", "/api/chapters/1/generation-status"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code,
                                 status.HTTP_401_UNAUTHORIZED)

    # --- cross-user isolation --------------------------------------------------

    def test_another_learners_chapter_is_not_readable(self):
        _, chapter = self._play_one_chapter()
        chapter_id = chapter["chapter_id"]
        self.client.force_authenticate(user=self.other)
        for path in (f"/api/chapters/{chapter_id}/provenance",
                     f"/api/chapters/{chapter_id}/generation-status"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code,
                                 status.HTTP_404_NOT_FOUND)

    def test_library_only_lists_the_requesting_learners_stories(self):
        self._play_one_chapter(topic="Water Cycle")
        self.client.force_authenticate(user=self.other)
        res = self.client.get("/api/me/library")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["stories"], [])   # sees none of Nimal's stories
        self.assertEqual(res.data["count"], 0)

    def test_another_learners_chapter_cannot_be_retried(self):
        sid, chapter = self._play_one_chapter()
        self.client.force_authenticate(user=self.other)
        res = self.client.post(
            f"/api/sessions/{sid}/chapters/{chapter['chapter_id']}/retry", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # --- response shapes -------------------------------------------------------

    def test_curriculum_returns_the_four_grades_with_page_ranges(self):
        res = self.client.get("/api/curriculum")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        grades = res.data["grades"]
        self.assertEqual([g["grade"] for g in grades], [6, 7, 8, 9])
        # Grade 6 is printed as one book of 11 chapters; grade 9 spans two parts
        # and its chapter numbering continues across them.
        g6 = grades[0]
        self.assertEqual(g6["chapter_count"], 11)
        self.assertEqual(g6["chapters"][0]["title"], "Wonders of the Living World")
        g9 = grades[3]
        self.assertEqual([c["number"] for c in g9["chapters"]], list(range(1, 20)))
        # Every section carries a printed page and an honest range flag.
        section = g6["chapters"][0]["sections"][0]
        for key in ("number", "title", "page_start", "page_end", "has_range"):
            self.assertIn(key, section)

    def test_library_reports_progress_for_a_story(self):
        sid, _ = self._play_one_chapter(topic="Photosynthesis", grade=8)
        res = self.client.get("/api/me/library")
        story = next(s for s in res.data["stories"] if s["id"] == sid)
        self.assertEqual(story["topic"], "Photosynthesis")
        self.assertEqual(story["grade"], 8)
        self.assertEqual(story["chapters_completed"], 1)
        self.assertFalse(story["is_complete"])
        self.assertEqual(res.data["in_progress"], 1)

    def test_progress_keeps_its_original_shape_and_gains_counters(self):
        self._play_one_chapter()
        res = self.client.get("/api/me/progress")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # The original contract, unchanged — this is what the older test asserts.
        first = res.data["progress"][0]
        self.assertIn("topic", first)
        for key in ("concept", "attempts", "correct", "mastery"):
            self.assertIn(key, first["concepts"][0])
        # ...and the extension alongside it.
        for key in ("summary", "topics", "strongest", "weakest", "definitions"):
            self.assertIn(key, res.data)
        self.assertEqual(res.data["summary"]["topics_studied"], 1)
        self.assertGreaterEqual(res.data["summary"]["questions_attempted"], 1)

    def test_weak_concepts_lists_only_concepts_that_were_missed(self):
        self._play_one_chapter(correct=False)   # every answer wrong
        res = self.client.get("/api/me/weak-concepts")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.data["count"], 1)
        for concept in res.data["concepts"]:
            self.assertLess(concept["correct"], concept["attempts"])  # missed at least once
            self.assertIn("grade", concept)                           # revisable
        self.assertTrue(res.data["topics"])

    def test_weak_concepts_excludes_a_concept_answered_correctly_every_time(self):
        self._play_one_chapter(correct=True)    # every answer right
        res = self.client.get("/api/me/weak-concepts")
        self.assertEqual(res.data["concepts"], [])

    def test_achievements_reports_badges_earned_and_still_to_earn(self):
        self._play_one_chapter()
        res = self.client.get("/api/me/achievements")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        by_name = {b["name"]: b for b in res.data["badges"]}
        # "On Fire" needs a longer streak than one chapter gives, so it is listed
        # as unearned WITH its criterion — that is the point of the gallery.
        self.assertFalse(by_name["On Fire"]["earned"])
        self.assertTrue(by_name["On Fire"]["criterion"])
        self.assertIn("current", res.data["streaks"])
        self.assertIn("best", res.data["streaks"])
        self.assertGreaterEqual(res.data["totals"]["questions_answered"], 1)

    def test_provenance_is_honest_when_a_chapter_has_no_sources(self):
        # Mock mode attaches no textbook references, which is exactly the
        # "not grounded" case the panel has to report rather than fail on.
        _, chapter = self._play_one_chapter()
        res = self.client.get(f"/api/chapters/{chapter['chapter_id']}/provenance")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["grounded"])
        self.assertEqual(res.data["passages"], [])
        self.assertTrue(res.data["message"])       # says why, rather than erroring

    # --- the fallback disclosure ----------------------------------------------

    def test_mock_chapters_are_never_reported_as_fallbacks(self):
        """The guard that keeps the notice off every offline chapter.

        Mock chapters legitimately carry no sources, so the "no sources" signal
        must not fire here — if it did, every chapter of every offline run would
        be labelled a failure.
        """
        _, chapter = self._play_one_chapter()
        res = self.client.get(f"/api/chapters/{chapter['chapter_id']}/generation-status")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["source_count"], 0)   # genuinely no sources...
        self.assertFalse(res.data["used_fallback"])     # ...but not a fallback
        self.assertFalse(res.data["can_retry"])

    def test_a_chapter_that_did_not_fall_back_cannot_be_retried(self):
        sid, chapter = self._play_one_chapter()
        res = self.client.post(
            f"/api/sessions/{sid}/chapters/{chapter['chapter_id']}/retry", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nothing to retry", res.data["error"])

    def test_no_generation_event_is_recorded_in_mock_mode(self):
        self.assertEqual(GenerationEvent.objects.count(), 0)
        self._play_one_chapter()
        self.assertEqual(GenerationEvent.objects.count(), 0)

    # --- empty states ----------------------------------------------------------

    def test_a_learner_with_no_history_gets_empty_results_not_errors(self):
        for path, keys in (
            ("/api/me/library", ("stories", "count")),
            ("/api/me/progress", ("progress",)),
            ("/api/me/weak-concepts", ("concepts", "count")),
        ):
            with self.subTest(path=path):
                res = self.client.get(path)
                self.assertEqual(res.status_code, status.HTTP_200_OK)
                for key in keys:
                    self.assertFalse(res.data[key])  # empty list or zero, never an error

    def test_achievements_for_a_learner_with_no_history(self):
        res = self.client.get("/api/me/achievements")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["totals"]["points"], 0)
        self.assertEqual(res.data["totals"]["badges_earned"], 0)
        self.assertEqual(res.data["explorer"]["earned"], [])
        # The catalogue is still listed, so the page can show what to aim for.
        self.assertEqual(len(res.data["badges"]), 2)
        self.assertFalse(any(b["earned"] for b in res.data["badges"]))

    # --- revision mode must not write ------------------------------------------

    def test_revision_selection_writes_nothing(self):
        """Revision mode chooses what to study; it must not itself change any
        learner state. Only the ordinary answer and generation endpoints may."""
        sid, _ = self._play_one_chapter(correct=False)
        session = Session.objects.get(pk=sid)
        before = (session.points, session.difficulty, session.current_streak,
                  session.chapter_count)
        stats_before = {
            (s.topic, s.concept): (s.attempts, s.correct)
            for s in ConceptStat.objects.filter(learner=session.learner)
        }

        # Everything the revision page does before a story is started.
        self.client.get("/api/me/weak-concepts")
        self.client.get("/api/me/progress")

        session.refresh_from_db()
        self.assertEqual(
            (session.points, session.difficulty, session.current_streak,
             session.chapter_count), before)
        stats_after = {
            (s.topic, s.concept): (s.attempts, s.correct)
            for s in ConceptStat.objects.filter(learner=session.learner)
        }
        self.assertEqual(stats_after, stats_before)

    def test_revision_starts_an_ordinary_session_on_the_weak_topic(self):
        """The page starts a story through the existing endpoint, so a revision
        session is an ordinary session — resumed if one is already open."""
        sid, _ = self._play_one_chapter(topic="Water Cycle", correct=False)
        weak = self.client.get("/api/me/weak-concepts").data
        topic = weak["topics"][0]
        before = Session.objects.count()

        res = self.client.post(
            "/api/sessions", {"topic": topic["topic"], "grade": topic["grade"]}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)   # resumed, not created
        self.assertTrue(res.data["resumed"])
        self.assertEqual(res.data["session_id"], sid)
        self.assertEqual(Session.objects.count(), before)       # nothing new made


class BadgeAwardingTests(APITestCase):
    """Badges must mean something: earned once per learner, and only for work
    actually done. Both rules below were defects found in use — a learner who
    revisited a topic collected the same explorer badge again and again, and a
    story that was started and immediately ended earned one for no work at all.
    """

    def setUp(self):
        os.environ["USE_MOCK_LLM"] = "true"
        cache.clear()
        self.user = User.objects.create_user(username="nimal", password="pw12345!")
        Learner.objects.create(user=self.user, name="Nimal")
        self.client.force_authenticate(user=self.user)

    def _start(self, topic="Water Cycle", grade=7):
        return self.client.post(
            "/api/sessions", {"topic": topic, "grade": grade}, format="json").data

    def _play_to_completion(self, topic="Water Cycle", grade=7):
        """Answer every question of every chapter until the story ends."""
        data = self._start(topic=topic, grade=grade)
        sid, chapter = data["session_id"], data["chapter"]
        awarded = []
        for _ in range(10):  # safety bound
            for q in chapter["questions"]:
                ci = Question.objects.get(pk=q["question_id"]).correct_index
                self.client.post(
                    f"/api/sessions/{sid}/answer",
                    {"question_id": q["question_id"], "answer_index": ci}, format="json")
            nxt = self.client.post(f"/api/sessions/{sid}/next", {}, format="json").data
            awarded += nxt.get("badges_awarded", [])
            if nxt["is_complete"]:
                break
            chapter = nxt["chapter"]
        return sid, awarded

    # --- earned once per learner ----------------------------------------------

    def test_replaying_a_topic_does_not_award_the_explorer_badge_again(self):
        _, first = self._play_to_completion(topic="Water Cycle")
        self.assertIn("Water Cycle Explorer", first)

        _, second = self._play_to_completion(topic="Water Cycle")
        self.assertNotIn("Water Cycle Explorer", second)
        self.assertEqual(
            Badge.objects.filter(session__learner__user=self.user,
                                 name="Water Cycle Explorer").count(), 1)

    def test_the_same_topic_typed_differently_is_still_one_explorer_badge(self):
        self._play_to_completion(topic="Water Cycle")
        _, second = self._play_to_completion(topic="water cycle")
        self.assertEqual(second, [])   # nothing new to earn
        explorers = Badge.objects.filter(
            session__learner__user=self.user, name__endswith="Explorer")
        self.assertEqual(explorers.count(), 1)
        self.assertEqual(explorers.first().name, "Water Cycle Explorer")  # first spelling kept

    def test_first_steps_is_earned_once_not_once_per_story(self):
        _, first = self._play_to_completion(topic="Water Cycle")
        self.assertIn("First Steps", first)
        _, second = self._play_to_completion(topic="Photosynthesis", grade=8)
        self.assertNotIn("First Steps", second)
        self.assertEqual(
            Badge.objects.filter(session__learner__user=self.user,
                                 name="First Steps").count(), 1)

    def test_a_different_topic_still_earns_its_own_explorer_badge(self):
        """The dedup must not suppress a genuinely different topic."""
        self._play_to_completion(topic="Water Cycle")
        _, second = self._play_to_completion(topic="Photosynthesis", grade=8)
        self.assertIn("Photosynthesis Explorer", second)

    # --- earned only for work actually done ------------------------------------

    def test_finishing_without_answering_anything_earns_no_explorer_badge(self):
        data = self._start(topic="Water Cycle")
        sid = data["session_id"]
        self.assertTrue(data["chapter"]["questions"])   # there was something to answer

        res = self.client.post(f"/api/sessions/{sid}/finish", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_complete"])
        self.assertEqual(res.data["badges_awarded"], [])
        self.assertEqual(res.data["badges"], [])
        self.assertEqual(res.data["points"], 0)
        self.assertFalse(Badge.objects.filter(session_id=sid).exists())

    def test_answering_one_question_then_finishing_does_earn_it(self):
        """The bar is engagement, not perfection: one answer is enough, and the
        answer does not have to be correct."""
        data = self._start(topic="Water Cycle")
        sid = data["session_id"]
        q0 = data["chapter"]["questions"][0]
        wrong = (Question.objects.get(pk=q0["question_id"]).correct_index + 1) % 4
        self.client.post(f"/api/sessions/{sid}/answer",
                         {"question_id": q0["question_id"], "answer_index": wrong},
                         format="json")

        res = self.client.post(f"/api/sessions/{sid}/finish", {}, format="json")
        self.assertIn("Water Cycle Explorer", res.data["badges"])


class SyllabusPlacementTests(APITestCase):
    """Placing a freely-typed topic in the printed syllabus.

    A learner types whatever they want to learn about, so the topic is rarely a
    chapter heading. The passages the story was grounded on do have printed page
    numbers, and the contents pages say which section owns those pages, so the
    placement is a lookup rather than a guess about wording.
    """

    def setUp(self):
        os.environ["USE_MOCK_LLM"] = "true"
        cache.clear()
        self.user = User.objects.create_user(username="nimal", password="pw12345!")
        Learner.objects.create(user=self.user, name="Nimal")
        self.client.force_authenticate(user=self.user)

    def _ref(self, book, printed, pdf_page):
        """A stored source reference as `llm._passage_refs` writes them."""
        return {"source_file": book, "page": pdf_page,
                "page_citation": f"p. {printed}", "chapter": "", "section": ""}

    # --- the lookup ------------------------------------------------------------

    def test_a_page_resolves_to_its_printed_sub_section(self):
        """The worked example: a Grade 6 story about light emitting diodes is
        grounded around printed page 122, which the contents pages place in
        8.5 Electronic Appliances, under 8. Electricity for a Comfortable Life."""
        found = api_curriculum.locate_page("G6.pdf", 122)
        self.assertEqual(found["grade"], 6)
        self.assertEqual(found["chapter"]["number"], 8)
        self.assertEqual(found["chapter"]["title"], "Electricity for a Comfortable Life")
        self.assertEqual(found["section"]["number"], "8.5")
        self.assertEqual(found["section"]["title"], "Electronic Appliances")

    def test_a_page_before_the_first_sub_section_is_a_chapter_opening(self):
        # Grade 6 chapter 7 "Magnets" starts at 99; its first sub-section at 100.
        found = api_curriculum.locate_page("G6.pdf", 99)
        self.assertEqual(found["chapter"]["number"], 7)
        self.assertIsNone(found["section"])

    def test_a_page_in_the_second_part_of_a_grade_resolves(self):
        # Grade 9 part 2 carries chapters 10 onwards.
        found = api_curriculum.locate_page("G9P2.pdf", 11)
        self.assertEqual(found["grade"], 9)
        self.assertEqual(found["chapter"]["number"], 11)
        self.assertEqual(found["chapter"]["title"], "Density")

    def test_an_unknown_book_does_not_resolve(self):
        self.assertIsNone(api_curriculum.locate_page("NotABook.pdf", 12))
        self.assertIsNone(api_curriculum.locate_page("G6.pdf", None))

    # --- the citation guard ----------------------------------------------------

    def test_a_citation_that_is_really_the_pdf_index_is_not_trusted(self):
        """About 11% of pages have no parsable footer, and the citation falls back
        to the PDF page index. Mapping that as a printed page would place the
        story in the wrong section, so it is treated as unresolvable."""
        # Citation and PDF page agree -> ambiguous, refused.
        self.assertIsNone(api_curriculum._printed_page(
            {"page_citation": "p. 12", "page": 12}))
        # Citation differs from the PDF index -> a real folio.
        self.assertEqual(api_curriculum._printed_page(
            {"page_citation": "pp. 99-101", "page": 113}), 99)

    # --- the vote --------------------------------------------------------------

    def test_placement_votes_on_the_chapter_before_the_sub_section(self):
        """A story usually draws on several sub-sections, so no one of them holds
        a majority. Deciding the chapter first keeps the placement stable."""
        sources = [
            self._ref("G6.pdf", 36, 50),    # 3.1 States of Water
            self._ref("G6.pdf", 48, 62),    # 3.5 Water, a Limited Resource
            self._ref("G6.pdf", 144, 158),  # 9.3, a different chapter entirely
        ]
        placed = api_curriculum.place_sources(sources)
        self.assertEqual(placed["chapter"]["number"], 3)      # two refs agree
        self.assertEqual(placed["matched"], 2)
        self.assertEqual(placed["total"], 3)

    def test_placement_is_none_when_nothing_can_be_resolved(self):
        self.assertIsNone(api_curriculum.place_sources([]))
        self.assertIsNone(api_curriculum.place_sources(
            [{"source_file": "G6.pdf", "page": 12, "page_citation": "p. 12"}]))

    # --- through the progress endpoint -----------------------------------------

    def test_progress_places_a_freely_typed_topic_in_the_syllabus(self):
        data = self.client.post(
            "/api/sessions", {"topic": "Light emitting diode", "grade": 6}, format="json").data
        sid, chapter = data["session_id"], data["chapter"]

        # Mock mode attaches no references, so stand in the ones a live run would
        # have stored for a story grounded in the electronics pages.
        row = Chapter.objects.get(pk=chapter["chapter_id"])
        row.sources = [self._ref("G6.pdf", 122, 136), self._ref("G6.pdf", 123, 137)]
        row.save(update_fields=["sources"])

        for q in chapter["questions"]:
            ci = Question.objects.get(pk=q["question_id"]).correct_index
            self.client.post(f"/api/sessions/{sid}/answer",
                             {"question_id": q["question_id"], "answer_index": ci},
                             format="json")

        topics = self.client.get("/api/me/progress").data["topics"]
        entry = next(t for t in topics if t["topic"] == "Light emitting diode")
        placed = entry["syllabus"]
        self.assertIsNotNone(placed)
        self.assertEqual(placed["chapter"]["title"], "Electricity for a Comfortable Life")
        self.assertEqual(placed["section"]["number"], "8.5")
        # The learner's own wording is kept — the placement annotates it, and the
        # topic remains the key that mastery and resumption are recorded against.
        self.assertEqual(entry["topic"], "Light emitting diode")

    def test_an_ungrounded_topic_is_reported_as_unplaced_rather_than_guessed(self):
        data = self.client.post(
            "/api/sessions", {"topic": "Water Cycle", "grade": 7}, format="json").data
        for q in data["chapter"]["questions"]:
            ci = Question.objects.get(pk=q["question_id"]).correct_index
            self.client.post(f"/api/sessions/{data['session_id']}/answer",
                             {"question_id": q["question_id"], "answer_index": ci},
                             format="json")

        topics = self.client.get("/api/me/progress").data["topics"]
        entry = next(t for t in topics if t["topic"] == "Water Cycle")
        self.assertIsNone(entry["syllabus"])   # no references, so no claim made
