// /revise — revision mode.
//
// The page answers one question honestly: which ideas has this learner got wrong
// most often, and what happens if they choose to work on one?
//
// What it does NOT do is generate anything of its own. "Revise these" sends the
// learner into the ordinary story flow, with exactly the request the Home page
// sends — POST /api/sessions {topic, grade}. That endpoint already looks up the
// learner's weakest concepts for the topic and hands them to the generator to
// revisit, so an ordinary story on a weak topic IS the targeted revision story.
// Building a second generator here would have duplicated the adaptation rules
// and the syllabus gate for no gain, and would have drifted apart from them.
//
// The copy below says exactly that, and no more than that. It does not promise
// that every weak concept appears, because the generator is given the weakest
// few (see `revisit_per_story` in the API response), nor that a concept will be
// mastered by reading one story.

import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { getWeakConcepts } from "../api";
import Loading from "../components/Loading";
import {
  Button,
  Card,
  EmptyState,
  ProgressBar,
  SkeletonLines,
  Toast,
  useToast,
} from "../components/ui";
import { useSession } from "../session";
import "../styles/study.css";

// Weak mastery is coloured by how weak it is, using the shared bar tones.
function toneFor(mastery) {
  if (mastery >= 0.6) return "amber";
  if (mastery >= 0.3) return "indigo";
  return "red";
}

function pct(mastery) {
  return Math.round((mastery || 0) * 100);
}

const sameTopic = (a, b) => (a || "").trim().toLowerCase() === (b || "").trim().toLowerCase();

export default function RevisePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const session = useSession();
  const { toast, showToast, clearToast } = useToast();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [startingTopic, setStartingTopic] = useState("");
  const topicRefs = useRef({});

  // The progress dashboard links here with the topic (and often the concept) the
  // learner tapped: navigate("/revise", { state: { topic, concept, grade } }).
  // All three are optional — arriving from the navigation bar sends none of them.
  const focus = location.state || {};

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getWeakConcepts()
      .then((res) => { if (!cancelled) setData(res); })
      .catch((e) => {
        if (cancelled) return;
        showToast(e.message);
        setData({ count: 0, concepts: [], topics: [] });  // show the page, not a blank screen
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const topics = useMemo(() => data?.topics || [], [data]);

  // Bring the topic the dashboard pointed at into view once the list has rendered.
  useEffect(() => {
    if (!focus.topic || topics.length === 0) return;
    const node = topicRefs.current[(focus.topic || "").trim().toLowerCase()];
    if (node) node.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focus.topic, topics]);

  async function handleRevise(topic, grade) {
    if (!grade || session.loading) return;
    setStartingTopic(topic);
    // Exactly the Home page's start: the shared session context's start(topic,
    // grade), which POSTs {topic, grade} to /api/sessions. Using the shared
    // context (rather than calling the API directly) also means /story/<id>
    // opens the live, answerable reader instead of the read-only replay.
    const id = await session.start(topic, grade);
    setStartingTopic("");
    if (id) navigate(`/story/${id}`);
    // On failure the shared session records the error and the app-level toast
    // shows it, so there is nothing to swallow here.
  }

  // A story is being written — the same full-card loader the Home page shows.
  if (session.generating) {
    return <Card><Loading /></Card>;
  }

  if (loading) {
    return (
      <Card>
        <h2>Revision</h2>
        <SkeletonLines lines={2} />
        <div style={{ height: 20 }} />
        <SkeletonLines lines={4} />
      </Card>
    );
  }

  if (topics.length === 0) {
    return (
      <Card>
        <h2>Revision</h2>
        <EmptyState
          icon="🎯"
          title="Nothing to revise yet"
          message="Revision collects the ideas you have answered incorrectly at least once. Answer a few more questions and anything you find hard will appear here."
          action={<Button onClick={() => navigate("/")}>Start a story</Button>}
        />
        <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
      </Card>
    );
  }

  const revisitPerStory = data?.revisit_per_story || 3;

  return (
    <Card>
      <h2>Revision</h2>
      <p className="revise-intro">
        These are the ideas you have missed at least once, weakest first. Choosing a topic starts
        an ordinary story on it — the difference is that the {revisitPerStory} concepts you are
        weakest at in that topic are given to the storyteller to work back into the chapters and
        the questions.
      </p>
      <p className="revise-intro">
        It is practice, not a shortcut: your answers there count exactly as they normally do.
      </p>

      <div className="revise-summary">
        <span className="pill">
          {data.count} {data.count === 1 ? "concept" : "concepts"} to revise
        </span>
        <span className="pill">
          across {topics.length} {topics.length === 1 ? "topic" : "topics"}
        </span>
      </div>

      {topics.map((topic) => {
        const isFocused = sameTopic(topic.topic, focus.topic);
        const busy = startingTopic === topic.topic && session.loading;
        return (
          <section
            key={`${topic.topic}-${topic.grade}`}
            ref={(node) => { topicRefs.current[(topic.topic || "").trim().toLowerCase()] = node; }}
            className={`revise-topic ${isFocused ? "is-focused" : ""}`.trim()}
            aria-label={`Revision for ${topic.topic}`}
          >
            <div className="revise-topic-head">
              <h3>{topic.topic}</h3>
              <span className="pill">{topic.grade ? `Grade ${topic.grade}` : "Grade unknown"}</span>
            </div>

            <div className="revise-topic-mastery">
              <ProgressBar
                value={pct(topic.mastery)}
                tone={toneFor(topic.mastery)}
                label={`${topic.topic} mastery`}
              />
              <span className="revise-mastery-value">
                {pct(topic.mastery)}% ({topic.correct}/{topic.attempts})
              </span>
            </div>

            <ul className="revise-concepts">
              {topic.concepts.map((c) => (
                <li
                  key={c.concept}
                  className={`revise-concept ${
                    isFocused && sameTopic(c.concept, focus.concept) ? "is-focused" : ""
                  }`.trim()}
                >
                  <span className="revise-concept-name">{c.concept}</span>
                  <ProgressBar
                    value={pct(c.mastery)}
                    tone={toneFor(c.mastery)}
                    label={`${c.concept} mastery`}
                  />
                  <span className="revise-concept-score">
                    {c.correct} of {c.attempts} correct
                  </span>
                </li>
              ))}
            </ul>

            <div className="revise-topic-actions">
              <Button
                onClick={() => handleRevise(topic.topic, topic.grade)}
                disabled={!topic.grade || session.loading}
              >
                {busy
                  ? "Starting…"
                  : topic.has_unfinished_session
                    ? "Continue revising this topic →"
                    : "Revise these →"}
              </Button>
              {topic.has_unfinished_session && (
                <p className="muted">
                  You have an unfinished story on this topic — this continues it.
                </p>
              )}
              {!topic.grade && (
                <p className="muted">
                  Choose a grade on the home page to revise this topic.
                </p>
              )}
            </div>
          </section>
        );
      })}

      <p className="revise-note">
        Mastery is the share of questions you have answered correctly for each idea, counted across
        every story you have read. A concept leaves this list once you stop getting it wrong.
      </p>

      <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
    </Card>
  );
}
