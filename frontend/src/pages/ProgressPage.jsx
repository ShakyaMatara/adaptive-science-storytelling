// /progress — the learner's progress dashboard (FR-17).
//
// Three things, in the order a learner cares about them:
//   1. headline counters — how much work has been done, and how well;
//   2. mastery per concept, grouped by topic, with the topic's own aggregate;
//   3. strengths and weaknesses, each concept carrying a link straight into
//      revision at the grade it was studied at.
//
// Every concept on this page is a route into /revise, which is what makes the
// dashboard actionable rather than merely descriptive. The one chart is an SVG
// drawn here — mastery against practice — chosen because it shows something the
// bars cannot: how much evidence sits behind each score. No charting library is
// used; nothing on this page needs one.

import { useCallback, useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { getProgress } from "../api";
import ProvenancePanel from "../components/ProvenancePanel";
import { Button, Card, EmptyState, ProgressBar, SkeletonBlock, SkeletonLines, Toast, useToast } from "../components/ui";
import "../styles/insight.css";

const pct = (fraction) => `${Math.round((fraction || 0) * 100)}%`;

export default function ProgressPage() {
  const navigate = useNavigate();
  const { toast, showToast, clearToast } = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  // Which chapter the provenance panel is showing, if any.
  const [provenance, setProvenance] = useState(null);

  const load = useCallback(() => {
    setData(null);
    setError("");
    getProgress()
      .then(setData)
      .catch((e) => {
        // A failed load is never dressed up as "no progress yet" — the learner
        // is told the difference between having no data and not reaching it.
        setError(e.message);
        showToast(e.message);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load]);

  // Send the learner into revision for one concept. /revise reads these from
  // location.state; nothing of that page is imported here.
  const revise = (topic, concept, grade) =>
    navigate("/revise", { state: { topic, concept, grade } });

  if (error) {
    return (
      <Card>
        <h2>📊 Your progress</h2>
        <EmptyState
          icon="⚠️"
          title="Could not load your progress"
          message={error}
          action={<Button onClick={load}>Try again</Button>}
        />
        <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
      </Card>
    );
  }

  if (!data) return <LoadingCard />;

  const summary = data.summary || {};
  const topics = data.topics || [];
  const definitions = data.definitions || {};
  const hasActivity = (summary.topics_studied || 0) > 0 || (summary.chapters_read || 0) > 0;

  if (!hasActivity) {
    return (
      <Card>
        <h2>📊 Your progress</h2>
        <EmptyState
          icon="📊"
          title="No progress yet"
          message="Read a story and answer its questions — your strengths and the concepts to revise will appear here."
        />
        <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
      </Card>
    );
  }

  return (
    <Card>
      <h2>📊 Your progress</h2>
      <p className="ins-section-note">
        Everything you have read and answered so far, across every story.
      </p>

      <Counters summary={summary} />

      <MasteryChart topics={topics} onPick={revise} />

      <section className="ins-section">
        <h3>Mastery by topic</h3>
        <p className="ins-section-note">
          Each bar is the share of questions you have answered correctly for that
          concept. Choose <em>Revise</em> to practise one again.
        </p>
        {topics.length === 0 ? (
          <EmptyState
            icon="📝"
            title="No answers recorded yet"
            message="Answer a chapter's questions and your concept mastery will show up here."
          />
        ) : (
          topics.map((t) => (
            <TopicBlock
              key={t.topic}
              topic={t}
              onRevise={revise}
              onShowSource={setProvenance}
            />
          ))
        )}
      </section>

      <Highlights
        strongest={data.strongest || []}
        weakest={data.weakest || []}
        definitions={definitions}
        onRevise={revise}
      />

      <ProvenancePanel
        chapterId={provenance?.chapterId}
        grade={provenance?.grade}
        label={provenance?.label}
        open={!!provenance}
        onClose={() => setProvenance(null)}
      />

      <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
    </Card>
  );
}

// --- Headline counters ---------------------------------------------------------
function Counters({ summary }) {
  const items = [
    { label: "Topics studied", value: summary.topics_studied || 0 },
    { label: "Chapters read", value: summary.chapters_read || 0 },
    {
      label: "Questions answered",
      value: summary.questions_attempted || 0,
      sub: `${summary.questions_correct || 0} correct`,
    },
    { label: "Accuracy", value: pct(summary.accuracy) },
    { label: "Points", value: summary.total_points || 0 },
    { label: "Badges earned", value: summary.badges_earned || 0 },
    { label: "Stories completed", value: summary.stories_completed || 0 },
    { label: "Stories in progress", value: summary.stories_in_progress || 0 },
  ];

  return (
    <div className="ins-counters">
      {items.map((item) => (
        <div className="ins-counter" key={item.label}>
          <span className="ins-counter-value">{item.value}</span>
          <span className="ins-counter-label">{item.label}</span>
          {item.sub && <span className="ins-counter-label ins-counter-sub">{item.sub}</span>}
        </div>
      ))}
    </div>
  );
}

// --- Mastery against practice --------------------------------------------------
// One dot per concept: how well it is known (up the side) against how often it
// has been answered (along the bottom). A low dot on the right is a real gap; a
// low dot on the left is simply not practised enough to say yet. Every dot is a
// revision link, like every concept elsewhere on the page.
function MasteryChart({ topics, onPick }) {
  // Derived from `topics` alone, so it is memoised: the parent re-renders every
  // time the textbook panel opens or a toast appears, and none of that changes
  // the chart.
  const points = useMemo(() => {
    const out = [];
    topics.forEach((t) => {
      (t.concepts || []).forEach((c) => {
        if (c.attempts > 0) out.push({ ...c, topic: t.topic, grade: t.grade });
      });
    });
    return out;
  }, [topics]);
  if (points.length === 0) return null;

  const W = 640;
  const H = 220;
  const left = 44;
  const right = W - 16;
  const top = 14;
  const bottom = H - 42;
  const maxAttempts = Math.max(2, ...points.map((p) => p.attempts));

  const x = (attempts) => left + ((attempts - 1) / (maxAttempts - 1)) * (right - left);
  const y = (mastery) => bottom - mastery * (bottom - top);

  const yTicks = [0, 0.5, 1];
  const step = Math.max(1, Math.ceil(maxAttempts / 6));
  const xTicks = [];
  for (let a = 1; a <= maxAttempts; a += step) xTicks.push(a);
  if (xTicks[xTicks.length - 1] !== maxAttempts) xTicks.push(maxAttempts);

  // Two concepts can land on exactly the same spot; nudge the later ones so
  // neither is hidden underneath the other.
  const seen = {};
  const placed = points.map((p) => {
    const key = `${p.attempts}-${p.mastery}`;
    const n = seen[key] || 0;
    seen[key] = n + 1;
    return { ...p, cx: x(p.attempts) + n * 9, cy: y(p.mastery) };
  });


  const band = (m) => (m >= 0.8 ? "strong" : m >= 0.5 ? "middling" : "weak");

  return (
    <section className="ins-section">
      <h3>Mastery against practice</h3>
      <p className="ins-section-note">
        Each dot is one concept. Higher is better; further right means you have
        answered more questions on it, so its score is more reliable. Choose a dot
        to revise that concept.
      </p>
      <div className="ins-chart-wrap">
        <svg
          className="ins-chart"
          viewBox={`0 0 ${W} ${H}`}
          width={W}
          height={H}
          role="img"
          aria-label={`Mastery against practice for ${placed.length} concepts.`}
        >
          {yTicks.map((t) => (
            <g key={t}>
              <line className="ins-chart-grid" x1={left} y1={y(t)} x2={right} y2={y(t)} />
              <text className="ins-chart-label" x={left - 8} y={y(t) + 3} textAnchor="end">
                {pct(t)}
              </text>
            </g>
          ))}
          <line className="ins-chart-axis" x1={left} y1={top} x2={left} y2={bottom} />
          {xTicks.map((a) => (
            <text
              key={a}
              className="ins-chart-label"
              x={x(a)}
              y={bottom + 16}
              textAnchor="middle"
            >
              {a}
            </text>
          ))}
          <text className="ins-chart-axis-title" x={(left + right) / 2} y={H - 8} textAnchor="middle">
            Questions answered on that concept
          </text>
          {placed.map((p) => (
            <circle
              key={`${p.topic}-${p.concept}`}
              className={`ins-dot ins-dot-${band(p.mastery)}`}
              cx={p.cx}
              cy={p.cy}
              r={7}
              tabIndex={0}
              role="button"
              aria-label={`Revise ${p.concept} in ${p.topic}: ${p.correct} of ${p.attempts} answered correctly, ${pct(p.mastery)}.`}
              onClick={() => onPick(p.topic, p.concept, p.grade)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onPick(p.topic, p.concept, p.grade);
                }
              }}
            >
              <title>
                {`${p.concept} (${p.topic}) — ${p.correct}/${p.attempts} correct`}
              </title>
            </circle>
          ))}
        </svg>
      </div>
      <p className="ins-legend">
        <span className="ins-legend-key">
          <span className="ins-legend-swatch" style={{ background: "var(--green)" }} /> Secure (80% and above)
        </span>
        <span className="ins-legend-key">
          <span className="ins-legend-swatch" style={{ background: "#d97706" }} /> Getting there (50-79%)
        </span>
        <span className="ins-legend-key">
          <span className="ins-legend-swatch" style={{ background: "var(--red)" }} /> Needs work (below 50%)
        </span>
      </p>
    </section>
  );
}

// --- One topic, its aggregate mastery and its concepts -------------------------
function TopicBlock({ topic, onRevise, onShowSource }) {
  const grades = topic.grades && topic.grades.length ? topic.grades : (topic.grade ? [topic.grade] : []);
  const source = topic.source_chapter;

  return (
    <div className="ins-topic">
      <div className="ins-topic-head">
        <h4 className="ins-topic-name">{topic.topic}</h4>
        {grades.map((g) => (
          <span className="ins-chip" key={g}>Grade {g}</span>
        ))}
        <span className="ins-chip ins-chip-quiet">
          {topic.correct}/{topic.attempts} correct
        </span>
      </div>

      <div className="ins-topic-bar">
        <ProgressBar
          value={Math.round((topic.mastery || 0) * 100)}
          tone={topic.mastery >= 0.8 ? "green" : topic.mastery >= 0.5 ? "amber" : "red"}
          label={`${topic.topic} overall mastery`}
        />
        <span className="ins-topic-pct">{pct(topic.mastery)}</span>
      </div>

      {(topic.concepts || []).map((c) => (
        <div className="ins-concept" key={c.concept}>
          <span className="ins-concept-name">
            {c.concept}
            {c.last_seen && (
              <span className="ins-concept-seen">Last seen {formatDate(c.last_seen)}</span>
            )}
          </span>
          {/* The shared bar rather than a hand-written one: it carries the
              progressbar role and value that a screen reader needs, which the
              topic bars above already had and these did not. */}
          <span className="ins-concept-bar">
            <ProgressBar
              value={Math.round(c.mastery * 100)}
              tone="green"
              label={`${c.concept}: ${c.correct} of ${c.attempts} correct`}
            />
          </span>
          <span className="ins-concept-num">{c.correct}/{c.attempts}</span>
          <button
            className="ins-revise"
            onClick={() => onRevise(topic.topic, c.concept, topic.grade)}
          >
            Revise
          </button>
        </div>
      ))}

      {source && (
        <button
          className="ins-source-btn"
          onClick={() => onShowSource({
            chapterId: source.chapter_id,
            grade: source.grade,
            label: `${topic.topic} — ${source.title}`,
          })}
        >
          📖 View the textbook source
        </button>
      )}
    </div>
  );
}

// --- Strengths and weaknesses --------------------------------------------------
function Highlights({ strongest, weakest, definitions, onRevise }) {
  if (strongest.length === 0 && weakest.length === 0) return null;

  return (
    <section className="ins-section">
      <h3>Strengths and gaps</h3>
      <div className="ins-highlights">
        <div className="ins-highlight ins-highlight-strong">
          <h4>💪 Strongest concepts</h4>
          <p className="ins-highlight-def">{definitions.strongest}</p>
          {strongest.length === 0 ? (
            <p className="muted">Nothing here yet — answer a few questions correctly.</p>
          ) : (
            strongest.map((c) => (
              <HighlightRow key={`${c.topic}-${c.concept}`} item={c} onRevise={onRevise} />
            ))
          )}
        </div>

        <div className="ins-highlight ins-highlight-weak">
          <h4>🎯 Concepts to revise</h4>
          <p className="ins-highlight-def">{definitions.weakest}</p>
          {weakest.length === 0 ? (
            <p className="muted">Nothing to revise — every concept you have met is fully correct.</p>
          ) : (
            weakest.map((c) => (
              <HighlightRow key={`${c.topic}-${c.concept}`} item={c} onRevise={onRevise} />
            ))
          )}
        </div>
      </div>
    </section>
  );
}

function HighlightRow({ item, onRevise }) {
  return (
    <div className="ins-highlight-row">
      <span className="ins-concept-name">
        {item.concept}
        <span className="ins-highlight-topic">
          {item.topic}{item.grade ? ` · Grade ${item.grade}` : ""}
        </span>
      </span>
      <span className="ins-highlight-score">
        {pct(item.mastery)} <span className="ins-concept-num">({item.correct}/{item.attempts})</span>
      </span>
      <button
        className="ins-revise"
        onClick={() => onRevise(item.topic, item.concept, item.grade)}
      >
        Revise
      </button>
    </div>
  );
}

// --- Small helpers -------------------------------------------------------------
function LoadingCard() {
  return (
    <Card>
      <h2>📊 Your progress</h2>
      <div className="ins-counters">
        {Array.from({ length: 8 }, (_, i) => (
          <div className="ins-counter" key={i}>
            <SkeletonBlock width="60%" height={22} />
            <SkeletonBlock width="90%" height={10} />
          </div>
        ))}
      </div>
      <div className="ins-section">
        <SkeletonLines lines={5} />
      </div>
    </Card>
  );
}

// "Last seen" only needs to be readable, not precise to the second.
function formatDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
