// The live story session, lifted out of App.jsx so that several routed pages can
// read and drive it.
//
// This is a pure refactor: the state variables, the order of the updates inside
// each handler, and the values sent to the API are exactly those that were in
// App.jsx before routing was introduced. Only their location changed.

import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { finishSession, nextChapter, startSession, submitAnswer } from "./api";

const SessionContext = createContext(null);

const EMPTY = {
  sessionId: null,
  chapter: null,       // {chapter_id, order, title, paragraphs, questions}
  totalChapters: 0,    // planned chapters in this story
  answers: {},         // question_id -> {selectedIndex, isCorrect, correctIndex, feedback}
  chapterComplete: false,
  points: 0,
  difficulty: 3,
  badges: [],          // all badge names earned so far
  justEarned: [],      // badges awarded at the last chapter boundary
  sources: [],         // textbook refs for the current chapter (RAG)
  chapterStart: 0,     // for response time
  resumed: false,      // true when continuing an existing story
  topic: "",
  grade: null,
  isComplete: false,
};

export function SessionProvider({ children }) {
  const [state, setState] = useState(EMPTY);
  const [loading, setLoading] = useState(false);       // any in-flight request
  const [generating, setGenerating] = useState(false); // a long LLM call (start / next chapter)
  const [error, setError] = useState("");

  // Swap in a chapter that was regenerated in place. This is the same transition
  // `next` performs, including restarting the response-time clock — timing a
  // retried chapter's answers from the previous chapter's load would put a wrong
  // `response_time_ms` on every one of them.
  const replaceChapter = useCallback((result) => {
    setState((prev) => ({
      ...prev,
      chapter: result.chapter,
      sources: result.sources || [],
      answers: {},
      chapterComplete: result.chapter_complete || false,
      chapterStart: Date.now(),
    }));
  }, []);

  const reset = useCallback(() => {
    setState(EMPTY);
    setError("");
  }, []);

  // Begin (or resume) a session and load its current chapter. Returns the
  // session id on success and null when the topic is refused or the call fails,
  // so the caller can decide whether to navigate.
  const start = useCallback(async (topic, grade) => {
    setError("");
    setLoading(true);
    setGenerating(true);
    try {
      const data = await startSession(topic.trim(), grade);
      // Syllabus gate: the topic isn't in this grade's textbook — explain and stop.
      if (data.in_syllabus === false) {
        setError(
          `"${topic.trim()}" isn't in your Grade ${grade} science syllabus. ` +
            (data.reason || "Try a topic from your textbook.")
        );
        return null;
      }
      setState({
        ...EMPTY,
        sessionId: data.session_id,
        chapter: data.chapter,
        totalChapters: data.total_chapters || 0,
        points: data.points,
        difficulty: data.difficulty,
        badges: data.badges,
        justEarned: [],
        sources: data.sources || [],
        answers: data.answers || {},   // rehydrate prior answers when resuming a story
        chapterComplete: data.chapter_complete || false, // 0-question chapters arrive complete
        resumed: !!data.resumed,
        chapterStart: Date.now(),
        topic: topic.trim(),
        grade,
        isComplete: !!data.is_complete,
      });
      return data.session_id;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setLoading(false);
      setGenerating(false);
    }
  }, []);

  // Submit one question's answer; record per-question feedback.
  const answer = useCallback(async (question, optionIndex) => {
    if (state.answers[question.question_id] || loading) return; // ignore once answered
    setError("");
    setLoading(true);
    try {
      const res = await submitAnswer(state.sessionId, {
        question_id: question.question_id,
        answer_index: optionIndex,
        response_time_ms: Date.now() - state.chapterStart,
      });
      setState((prev) => ({
        ...prev,
        answers: {
          ...prev.answers,
          [question.question_id]: {
            selectedIndex: optionIndex,
            isCorrect: res.is_correct,
            correctIndex: res.correct_index,
            feedback: res.feedback,
          },
        },
        points: res.points,
        chapterComplete: res.chapter_complete,
      }));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [loading, state.answers, state.sessionId, state.chapterStart]);

  // Move to the next chapter (where difficulty adapts + badges are awarded), or finish.
  const next = useCallback(async () => {
    setError("");
    setLoading(true);
    setGenerating(true);
    try {
      const data = await nextChapter(state.sessionId);
      if (data.is_complete) {
        setState((prev) => ({
          ...prev,
          points: data.points,
          badges: data.badges,
          justEarned: data.badges_awarded || [],
          isComplete: true,
        }));
      } else {
        setState((prev) => ({
          ...prev,
          points: data.points,
          badges: data.badges,
          justEarned: data.badges_awarded || [],
          chapter: data.chapter,
          totalChapters: data.total_chapters || prev.totalChapters,
          difficulty: data.difficulty,
          sources: data.sources || [],
          answers: {},
          chapterComplete: data.chapter_complete || false, // 0-question chapters arrive complete
          resumed: false,
          chapterStart: Date.now(),
        }));
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      setGenerating(false);
    }
  }, [state.sessionId]);

  // End the session early (before the planned last chapter) and jump to the results.
  const finish = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const data = await finishSession(state.sessionId);
      setState((prev) => ({
        ...prev,
        points: data.points,
        badges: data.badges,
        isComplete: true,
      }));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [state.sessionId]);

  const value = useMemo(
    () => ({ ...state, loading, generating, error, setError, replaceChapter, reset,
             start, answer, next, finish }),
    [state, loading, generating, error, replaceChapter, reset, start, answer, next, finish]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside a SessionProvider");
  return ctx;
}
