// Home — the existing start flow, unchanged in behaviour.
//
// The topic box, the suggestion chips and the grade buttons are exactly as they
// were on the old start screen. Two things are new and additive: the topic and
// grade can arrive pre-filled through the router's location state (which is how
// the syllabus browser hands a sub-section over), and a successful start
// navigates to /story/<id> instead of switching an internal screen variable.

import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { getTopics } from "../api";
import Loading from "../components/Loading";
import { useSession } from "../session";

export default function HomePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const session = useSession();

  const prefill = location.state || {};
  const [topics, setTopics] = useState([]);
  const [topic, setTopic] = useState(prefill.topic || "");
  const [grade, setGrade] = useState(prefill.grade || null);

  // Load the topic list once (used only as clickable suggestions).
  useEffect(() => {
    getTopics()
      .then(setTopics)
      .catch((e) => session.setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A later arrival through the router (e.g. a second pick in the syllabus
  // browser) should replace what is in the boxes.
  useEffect(() => {
    if (prefill.topic) setTopic(prefill.topic);
    if (prefill.grade) setGrade(prefill.grade);
  }, [prefill.topic, prefill.grade]);

  async function handleStart() {
    const id = await session.start(topic, grade);
    if (id) navigate(`/story/${id}`);
  }

  if (session.generating) {
    return <div className="card"><Loading /></div>;
  }

  const canStart = topic.trim() && grade && !session.loading;

  return (
    <div className="card">
      <h2>Start your adventure</h2>

      <label className="field-label" htmlFor="topic">What topic do you want to learn?</label>
      <input
        id="topic"
        className="text-input"
        value={topic}
        placeholder="e.g. Photosynthesis"
        onChange={(e) => setTopic(e.target.value)}
      />
      {topics.length > 0 && (
        <div className="chips">
          <span className="chips-label">Try:</span>
          {topics.map((t) => (
            <button key={t.slug} type="button" className="chip" onClick={() => setTopic(t.title)}>
              {t.title}
            </button>
          ))}
        </div>
      )}

      <p className="field-label">Your grade</p>
      <div className="grade-grid">
        {[6, 7, 8, 9].map((g) => (
          <button
            key={g}
            className={`grade-btn ${grade === g ? "selected" : ""}`}
            onClick={() => setGrade(g)}
          >
            Grade {g}
          </button>
        ))}
      </div>

      <button className="primary-btn" disabled={!canStart} onClick={handleStart}>
        {session.loading ? "Starting…" : "Start learning →"}
      </button>

      <p className="auth-switch">
        Not sure what to pick?{" "}
        <button className="link-btn" onClick={() => navigate("/browse")}>
          Browse the syllabus
        </button>
      </p>
    </div>
  );
}
