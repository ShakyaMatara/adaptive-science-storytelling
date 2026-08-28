// /achievements — the badge gallery, streaks and lifetime totals.
//
// Read-only over data the system already keeps. Unearned badges are shown
// alongside earned ones with their criteria visible, so the page tells a learner
// what is still within reach rather than only what is behind them.

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getAchievements } from "../api";
import { Button, Card, EmptyState, SkeletonBlock, SkeletonLines, Toast, useToast } from "../components/ui";
import "../styles/robustness.css";

export default function AchievementsPage() {
  const navigate = useNavigate();
  const { toast, showToast, clearToast } = useToast();
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAchievements()
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => {
        if (cancelled) return;
        showToast(e.message);
        setFailed(true);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (failed) {
    return (
      <Card>
        <h2>🏅 Achievements</h2>
        <EmptyState
          icon="🔌"
          title="Your achievements could not be loaded"
          message="This is a problem at our end, not with your progress — nothing has been lost."
          action={<Button onClick={() => window.location.reload()}>Try again</Button>}
        />
        <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
      </Card>
    );
  }

  if (!data) {
    return (
      <Card>
        <h2>🏅 Achievements</h2>
        <div className="totals-grid">
          {Array.from({ length: 6 }, (_, i) => <SkeletonBlock key={i} height={64} />)}
        </div>
        <div style={{ height: 20 }} />
        <SkeletonLines lines={4} />
      </Card>
    );
  }

  const { badges, explorer, streaks, totals } = data;
  const nothingYet = totals.badges_earned === 0 && totals.questions_answered === 0;

  return (
    <>
      <Card>
        <h2>🏅 Achievements</h2>

        {nothingYet ? (
          <EmptyState
            icon="🏅"
            title="No achievements yet"
            message="Read a story and answer its questions to earn your first badge."
            action={<Button onClick={() => navigate("/browse")}>Browse the syllabus</Button>}
          />
        ) : (
          <>
            <div className="totals-grid">
              <Total label="Points" value={totals.points} />
              <Total label="Badges" value={totals.badges_earned} />
              <Total label="Stories finished" value={totals.stories_completed} />
              <Total label="Chapters read" value={totals.chapters_read} />
              <Total label="Questions answered" value={totals.questions_answered} />
              <Total label="Accuracy" value={`${Math.round(totals.accuracy * 100)}%`} />
            </div>

            <div className="streak-panel">
              <div className="streak-figure">
                <span className="streak-number">{streaks.current}</span>
                <span className="streak-label">
                  current streak{streaks.current_topic ? ` · ${streaks.current_topic}` : ""}
                </span>
              </div>
              <div className="streak-figure">
                <span className="streak-number">{streaks.best}</span>
                <span className="streak-label">
                  best streak{streaks.best_topic ? ` · ${streaks.best_topic}` : ""}
                </span>
              </div>
              <p className="streak-definition muted">{streaks.definition}</p>
            </div>
          </>
        )}
      </Card>

      <Card className="badge-gallery-card">
        <h3>Badge gallery</h3>
        <div className="badge-gallery">
          {badges.map((b) => (
            <BadgeTile
              key={b.name}
              icon={b.icon}
              name={b.name}
              criterion={b.criterion}
              earned={b.earned}
              detail={b.earned ? `Earned ${formatDate(b.first_earned_at)}` : null}
            />
          ))}

          {/* The Explorer family: one badge per topic completed, so the earned
              members are listed and the criterion is stated once. */}
          {explorer.earned.map((e) => (
            <BadgeTile
              key={e.name}
              icon={explorer.icon}
              name={e.name}
              criterion={explorer.criterion}
              earned
              detail={`Earned ${formatDate(e.awarded_at)}`}
            />
          ))}
          {explorer.earned_count === 0 && (
            <BadgeTile
              icon={explorer.icon}
              name="Topic Explorer"
              criterion={explorer.criterion}
              earned={false}
              detail={null}
            />
          )}
        </div>
        <p className="muted gallery-note">
          {explorer.earned_count > 0
            ? `You have completed ${explorer.earned_count} ${
                explorer.earned_count === 1 ? "topic" : "topics"
              }. There is an Explorer badge for every topic you finish.`
            : "Finish a story to earn your first Explorer badge."}
        </p>
        <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
      </Card>
    </>
  );
}

function Total({ label, value }) {
  return (
    <div className="total-tile">
      <span className="total-value">{value}</span>
      <span className="total-label">{label}</span>
    </div>
  );
}

function BadgeTile({ icon, name, criterion, earned, detail }) {
  return (
    <div className={`badge-tile ${earned ? "earned" : "unearned"}`}>
      <span className="badge-tile-icon" aria-hidden="true">{icon}</span>
      <span className="badge-tile-name">{name}</span>
      <span className="badge-tile-criterion">{criterion}</span>
      {detail && <span className="badge-tile-detail">{detail}</span>}
      {!earned && <span className="badge-tile-detail muted">Not earned yet</span>}
    </div>
  );
}

function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric",
  });
}
