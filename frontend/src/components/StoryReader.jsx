// The story-reading surface, extracted verbatim from App.jsx.
//
// This is a pure refactor: the markup, the class names, the props and the order
// in which things are rendered are unchanged. The only difference is that the
// pieces now live in a file of their own so the router can mount them at
// /story/:id, and so the small parts (status bar, badges, source note) can be
// reused by the pages added later.

import { useState } from "react";

import { ask } from "../api";

// --- The reader ---------------------------------------------------------------
export default function StoryReader({
  chapter, sessionId, grade, resumed, sources, points, difficulty, totalChapters,
  badges, justEarned, answers, chapterComplete, loading, onAnswer, onNext, onFinish,
  notice = null, toolbar = null, onParagraphClick = null, activeParagraph = null,
}) {
  return (
    <div className="card">
      <StatusBar points={points} difficulty={difficulty} badges={badges} order={chapter.order} total={totalChapters} />

      {resumed && <p className="badge-toast">📖 Continuing your story…</p>}

      {justEarned.length > 0 && (
        <p className="badge-toast">🏅 New badge: {justEarned.join(", ")}</p>
      )}

      {/* Slot for the fallback-disclosure notice (added in a later phase). */}
      {notice}

      <h2 className="chapter-title">{chapter.title}</h2>

      {/* Slot for the reader toolbar: read-aloud and export controls. */}
      {toolbar}

      <div className="story">
        {chapter.paragraphs.map((p, i) => (
          <p
            key={i}
            id={`chapter-paragraph-${i}`}
            className={[
              onParagraphClick ? "story-p-clickable" : "",
              activeParagraph === i ? "story-p-active" : "",
            ].filter(Boolean).join(" ")}
            onClick={onParagraphClick ? () => onParagraphClick(i) : undefined}
          >
            {p}
          </p>
        ))}
      </div>
      <SourceNote grade={grade} sources={sources} />

      {chapter.questions.map((q) => (
        <QuestionBlock
          key={q.question_id}
          question={q}
          answer={answers[q.question_id]}
          loading={loading}
          onAnswer={onAnswer}
        />
      ))}

      {chapterComplete && (
        <div className="feedback feedback-correct chapter-done">
          <p>Chapter complete! 🎉</p>
          <button className="primary-btn" onClick={onNext}>
            {loading ? "Loading…" : "Continue →"}
          </button>
        </div>
      )}

      {/* Keyed by chapter so the panel (and any previous answer) resets per chapter. */}
      <QnAPanel key={chapter.chapter_id} sessionId={sessionId} />

      <div className="finish-early">
        <button className="link-btn" onClick={onFinish} disabled={loading}>
          Finish &amp; see results →
        </button>
      </div>
    </div>
  );
}

// Collapsible "Ask about this topic" panel — grounded Q&A.
// Answers come only from the grade's textbook; never affects points/difficulty.
export function QnAPanel({ sessionId }) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    if (!question.trim() || loading) return;
    setLoading(true);
    setErr("");
    setResult(null);
    try {
      setResult(await ask(sessionId, question.trim()));
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="qna">
      <button className="qna-toggle" onClick={() => setOpen(!open)}>
        💬 Ask about this topic {open ? "▲" : "▼"}
      </button>
      {open && (
        <div className="qna-body">
          <div className="qna-row">
            <input
              className="text-input"
              value={question}
              placeholder="Ask a question about this topic…"
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
            />
            <button className="primary-btn qna-ask" disabled={!question.trim() || loading} onClick={submit}>
              {loading ? "…" : "Ask"}
            </button>
          </div>
          {err && <p className="qna-error">⚠️ {err}</p>}
          {result && (
            <div className={`qna-answer ${result.in_syllabus === false || result.blocked ? "qna-refused" : ""}`}>
              <p>{result.answer}</p>
              {result.sources && result.sources.length > 0 && (
                <p className="sources">
                  📖 Sources: {[...new Set(result.sources.map((s) => s.page_citation || `p. ${s.page}`))].join(", ")}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// One question with its 4 options and per-question feedback.
export function QuestionBlock({ question, answer, loading, onAnswer }) {
  return (
    <div className="question-block">
      <h3 className="question">{question.question}</h3>
      <div className="options">
        {question.options.map((opt, i) => (
          <button
            key={i}
            className={`option-btn ${optionClass(i, answer)}`}
            disabled={!!answer || loading}
            onClick={() => onAnswer(question, i)}
          >
            <span className="option-letter">{String.fromCharCode(65 + i)}</span>
            {opt}
          </button>
        ))}
      </div>
      {answer && (
        <div className={`feedback ${answer.isCorrect ? "feedback-correct" : "feedback-wrong"}`}>
          <p>{answer.feedback}</p>
        </div>
      )}
    </div>
  );
}

// --- Small shared pieces ------------------------------------------------------
export function StatusBar({ points, difficulty, badges, order, total }) {
  return (
    <div className="status-bar">
      <span className="pill pill-points">⭐ {points} pts</span>
      <span className="pill">{total ? `Chapter ${order} of ${total}` : `Chapter ${order}`}</span>
      <span className="pill difficulty">
        Difficulty <DifficultyDots level={difficulty} />
      </span>
      {badges.length > 0 && <BadgeList badges={badges} small />}
    </div>
  );
}

// Five dots, filled up to the current difficulty level (1–5).
export function DifficultyDots({ level }) {
  return (
    <span className="dots">
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} className={`dot ${n <= level ? "filled" : ""}`} />
      ))}
    </span>
  );
}

export function BadgeList({ badges, small }) {
  return (
    <span className={`badges ${small ? "badges-small" : ""}`}>
      {badges.map((b) => (
        <span key={b} className="badge-chip">🏅 {b}</span>
      ))}
    </span>
  );
}

// Small "Based on: Grade X textbook (p.12)" line under a textbook-grounded chapter.
// Renders nothing in mock mode (no sources) or if the chapter wasn't grounded.
export function SourceNote({ grade, sources }) {
  if (!sources || sources.length === 0) return null;
  const pages = [...new Set(sources.map((s) => s.page_citation || (s.page != null ? `p. ${s.page}` : "")).filter(Boolean))];
  const pageText = pages.length ? ` (${pages.join(", ")})` : "";
  return <p className="sources">📖 Based on: Grade {grade} textbook{pageText}</p>;
}

// How an option button should look once its question is answered:
// the correct option turns green; a wrong pick turns red.
export function optionClass(index, answer) {
  if (!answer) return "";
  if (index === answer.correctIndex) return "correct";
  if (index === answer.selectedIndex) return "wrong";
  return "dimmed";
}
