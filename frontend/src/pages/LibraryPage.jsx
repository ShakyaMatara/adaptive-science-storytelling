// /library — My Stories.
//
// Every story this learner has started, as a filterable grid of cards: how far
// through it they are, what they scored, what they earned, and when they last
// worked on it.
//
// Neither action here is new machinery. "Resume" runs the existing start call —
// the backend recognises an unfinished story on the same topic and grade and
// returns it rather than creating another — and then opens the live reader.
// "Read again" opens /story/<id>, which replays a finished story read-only.

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getLibrary } from "../api";
import {
  Button,
  Card,
  EmptyState,
  ProgressBar,
  SkeletonBlock,
  Toast,
  useToast,
} from "../components/ui";
import { useSession } from "../session";
import "../styles/discovery.css";

const STATUS_FILTERS = [
  { key: "all", label: "All" },
  { key: "open", label: "In progress" },
  { key: "done", label: "Completed" },
];

export default function LibraryPage() {
  const navigate = useNavigate();
  const session = useSession();
  const { toast, showToast, clearToast } = useToast();

  const [stories, setStories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [grade, setGrade] = useState("all");
  const [status, setStatus] = useState("all");
  const [resumingId, setResumingId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getLibrary()
      .then((data) => { if (!cancelled) setStories((data && data.stories) || []); })
      .catch((e) => { if (!cancelled) showToast(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Only offer a grade filter for grades the learner actually has stories in.
  const gradesPresent = useMemo(
    () => [...new Set(stories.map((s) => s.grade))].sort((a, b) => a - b),
    [stories]
  );

  const visible = useMemo(
    () =>
      stories.filter((s) => {
        if (grade !== "all" && s.grade !== grade) return false;
        if (status === "open" && s.is_complete) return false;
        if (status === "done" && !s.is_complete) return false;
        return true;
      }),
    [stories, grade, status]
  );

  // Resume through the existing start path: the backend returns the unfinished
  // session instead of making a new one, and the shared session state is filled
  // in so /story/<id> opens the interactive reader rather than the replay.
  async function resume(story) {
    setResumingId(story.id);
    try {
      const id = await session.start(story.topic, story.grade);
      // A null id means the start call was refused or failed; `start` has already
      // put the reason on the shared session error, which the app-wide toast in
      // App.jsx shows. Raising a second toast here would only talk over it.
      if (id) navigate(`/story/${id}`);
    } catch (e) {
      showToast(e.message);
    } finally {
      setResumingId(null);
    }
  }

  if (loading) {
    return (
      <Card>
        <div className="disc-head"><h2>📖 My stories</h2></div>
        <div className="lib-grid">
          {[0, 1, 2, 3].map((i) => (
            <div className="lib-skeleton-card" key={i} aria-hidden="true">
              <SkeletonBlock width="70%" height={18} />
              <SkeletonBlock width="45%" height={11} />
              <SkeletonBlock width="100%" height={10} />
              <SkeletonBlock width="60%" height={22} />
            </div>
          ))}
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="disc-head">
        <h2>📖 My stories</h2>
        <span className="disc-count">
          {stories.length} started ·{" "}
          {stories.filter((s) => s.is_complete).length} completed
        </span>
      </div>

      {stories.length === 0 ? (
        <EmptyState
          icon="📚"
          title="No stories yet"
          message="Every story you start will be kept here, with your points and badges. Pick something from your syllabus to begin."
          action={<Button onClick={() => navigate("/browse")}>Browse the syllabus</Button>}
        />
      ) : (
        <>
          <p className="disc-lede">Pick up where you left off, or read a finished story again.</p>

          {gradesPresent.length > 1 && (
            <div className="disc-filters" role="group" aria-label="Filter by grade">
              <FilterButton active={grade === "all"} onClick={() => setGrade("all")}>
                All grades
              </FilterButton>
              {gradesPresent.map((g) => (
                <FilterButton key={g} active={grade === g} onClick={() => setGrade(g)}>
                  Grade {g}
                </FilterButton>
              ))}
            </div>
          )}

          <div className="disc-filters" role="group" aria-label="Filter by progress">
            {STATUS_FILTERS.map((f) => (
              <FilterButton key={f.key} active={status === f.key} onClick={() => setStatus(f.key)}>
                {f.label}
              </FilterButton>
            ))}
          </div>

          {visible.length === 0 ? (
            <EmptyState
              icon="🔍"
              title="Nothing matches those filters"
              message="Try a different grade, or show all of your stories."
              action={
                <Button
                  variant="quiet"
                  onClick={() => { setGrade("all"); setStatus("all"); }}
                >
                  Show every story
                </Button>
              }
            />
          ) : (
            <div className="lib-grid">
              {visible.map((story) => (
                <StoryCard
                  key={story.id}
                  story={story}
                  resuming={resumingId === story.id}
                  busy={resumingId !== null}
                  onResume={() => resume(story)}
                  onRead={() => navigate(`/story/${story.id}`)}
                />
              ))}
            </div>
          )}
        </>
      )}

      <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
    </Card>
  );
}

// --- Pieces ----------------------------------------------------------------------

function FilterButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      className={`disc-filter ${active ? "selected" : ""}`}
      aria-pressed={active}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function StoryCard({ story, resuming, busy, onResume, onRead }) {
  // Show progress against the planned length where there is one; a story from
  // before planning falls back to the chapters it actually has.
  const total = Math.max(story.planned_chapters || 0, story.chapter_count, 1);
  // Report what was actually read. Completion used to fill the bar to 100% and
  // claim every chapter had been read, which was untrue of a story ended early —
  // a story abandoned at chapter 1 of 2 with nothing answered still announced
  // "All 2 chapters read". A chapter counts as read once its questions are
  // answered, so this is the same measure the reader itself uses.
  const done = Math.min(story.chapters_completed, total);
  const endedEarly = story.is_complete && done < total;
  const scored = story.questions_answered > 0;

  return (
    <article className="lib-card">
      <div className="lib-card-top">
        <h3 className="lib-topic">{story.topic}</h3>
        <span className={`lib-status ${story.is_complete ? "lib-status-done" : "lib-status-open"}`}>
          {story.is_complete ? "Finished" : "In progress"}
        </span>
      </div>

      <div className="lib-meta">
        <span>Grade {story.grade}</span>
        <span className="lib-meta-dot" aria-hidden="true">·</span>
        <span>{timeAgo(story.last_activity)}</span>
      </div>

      <div>
        <div className="lib-progress-label">
          <span>
            {story.is_complete
              ? (endedEarly
                  ? `Ended early — ${done} of ${total} chapter${total === 1 ? "" : "s"} read`
                  : `All ${total} chapter${total === 1 ? "" : "s"} read`)
              : `Chapter ${Math.min(done + 1, total)} of ${total}`}
          </span>
          <span>{Math.round((done / total) * 100)}%</span>
        </div>
        <ProgressBar
          value={done}
          max={total}
          tone={endedEarly ? "amber" : story.is_complete ? "green" : "indigo"}
          label={`${done} of ${total} chapters completed`}
        />
      </div>

      <div className="lib-stats">
        <span className="lib-stat lib-stat-points">{story.points} points</span>
        {scored && (
          <span className="lib-stat lib-stat-score">
            {story.correct_count}/{story.questions_answered} correct
          </span>
        )}
        {story.badges.length > 0 && (
          <span className="lib-stat">
            🏅 {story.badges.length} badge{story.badges.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {story.badges.length > 0 && (
        <div className="badges badges-small">
          {story.badges.map((name) => (
            <span className="badge-chip" key={name}>{name}</span>
          ))}
        </div>
      )}

      <div className="lib-actions">
        {!story.is_complete && (
          <Button onClick={onResume} disabled={busy}>
            {resuming ? "Resuming…" : "Resume"}
          </Button>
        )}
        <Button variant="quiet" onClick={onRead} disabled={busy}>
          Read again
        </Button>
      </div>
    </article>
  );
}

// --- Helpers ---------------------------------------------------------------------

// A short, friendly "when" for a card. Falls back to a plain date once a story
// is more than a week old.
function timeAgo(iso) {
  if (!iso) return "recently";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "recently";
  const seconds = Math.round((Date.now() - then.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return then.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
