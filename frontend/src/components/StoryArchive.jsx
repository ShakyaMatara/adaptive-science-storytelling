// A read-only replay of a story the learner has already worked through.
//
// The interactive reader only exists for the story currently held in memory, so
// opening /story/<id> for any other session — from My Stories, from a bookmark,
// or after a page reload — lands here instead. It reads the full session state
// the API already exposes at GET /api/sessions/<id> and prints it: every
// chapter, its textbook citation, and every question with the option the learner
// chose alongside the correct one.

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getSession } from "../api";
import FallbackNotice from "./FallbackNotice";
import ReaderToolbar from "./ReaderToolbar";
import { BadgeList, SourceNote } from "./StoryReader";
import { Button, Card, EmptyState, SkeletonLines, Toast, useToast } from "./ui";

export default function StoryArchive({ sessionId }) {
  const navigate = useNavigate();
  const { toast, showToast, clearToast } = useToast();
  const [story, setStory] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getSession(sessionId)
      .then((data) => { if (!cancelled) setStory(data); })
      .catch((e) => { if (!cancelled) showToast(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  if (loading) {
    return (
      <Card>
        <SkeletonLines lines={2} />
        <div style={{ height: 16 }} />
        <SkeletonLines lines={5} />
      </Card>
    );
  }

  if (!story) {
    return (
      <Card>
        <EmptyState
          icon="🔍"
          title="That story could not be opened"
          message="It may belong to another account, or it may no longer exist."
          action={<Button onClick={() => navigate("/library")}>Back to my stories</Button>}
        />
        <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
      </Card>
    );
  }

  const answered = story.chapters.flatMap((c) => c.questions).filter((q) => q.user_answer_index !== null);
  const correct = answered.filter((q) => q.is_correct).length;

  return (
    <Card className="story-archive">
      <div className="status-bar">
        <span className="pill pill-points">⭐ {story.points} pts</span>
        <span className="pill">{story.chapters.length} chapters</span>
        <span className="pill">Grade {story.grade}</span>
        <span className="pill">{story.is_complete ? "Completed" : "In progress"}</span>
        {story.badges.length > 0 && <BadgeList badges={story.badges.map((b) => b.name)} small />}
      </div>

      <h2 className="chapter-title">{story.topic}</h2>
      <p className="muted">
        {answered.length > 0
          ? `${correct} of ${answered.length} questions answered correctly.`
          : "No questions answered yet."}
      </p>

      <ReaderToolbar
        sessionId={sessionId}
        story={story}
        paragraphs={story.chapters[0]?.paragraphs || []}
        learnerName={story.learner_name}
      />

      <div id="printable-story">
        {story.chapters.map((c) => (
          <section key={c.id} className="archive-chapter">
            <FallbackNotice
              sessionId={story.id}
              chapterId={c.id}
              status={{ used_fallback: c.used_fallback, can_retry: c.can_retry,
                        retry_blocked_reason: "" }}
            />
            <h3>Chapter {c.order}: {c.title}</h3>
            <div className="story">
              {c.paragraphs.map((p, i) => <p key={i}>{p}</p>)}
            </div>
            <SourceNote grade={story.grade} sources={c.sources} />

            {c.questions.map((q) => (
              <div key={q.id} className="question-block">
                <h4 className="question">{q.question_text}</h4>
                <ul className="archive-options">
                  {q.options.map((opt, i) => {
                    const isCorrect = i === q.correct_index;
                    const isChosen = i === q.user_answer_index;
                    return (
                      <li
                        key={i}
                        className={`archive-option ${isCorrect ? "correct" : ""} ${
                          isChosen && !isCorrect ? "wrong" : ""
                        }`}
                      >
                        <span className="option-letter">{String.fromCharCode(65 + i)}</span>
                        {opt}
                        {isCorrect && <span className="archive-tag">correct answer</span>}
                        {isChosen && <span className="archive-tag">your answer</span>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </section>
        ))}
      </div>

      <div className="finish-early">
        <Button variant="link" onClick={() => navigate("/library")}>← Back to my stories</Button>
      </div>

      <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
    </Card>
  );
}
