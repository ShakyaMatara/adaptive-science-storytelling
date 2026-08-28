// /progress — cross-session concept mastery.
//
// This is the existing progress screen, moved out of App.jsx unchanged so that
// the route has real content from the moment it exists. It is extended in place
// in a later phase; the mastery rows below are the part that must keep working.

import { useEffect, useState } from "react";

import { getProgress } from "../api";
import { Card, EmptyState, SkeletonLines, Toast, useToast } from "../components/ui";

export default function ProgressPage() {
  const { toast, showToast, clearToast } = useToast();
  const [progress, setProgress] = useState(null);

  useEffect(() => {
    getProgress()
      .then((data) => setProgress(data.progress || []))
      .catch((e) => { showToast(e.message); setProgress([]); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (progress === null) {
    return <Card><h2>📊 Your progress</h2><SkeletonLines lines={4} /></Card>;
  }

  return (
    <Card>
      <h2>📊 Your progress</h2>
      {progress.length === 0 ? (
        <EmptyState
          icon="📊"
          title="No progress yet"
          message="Finish a session to see your strengths and weaknesses."
        />
      ) : (
        progress.map((t) => (
          <div key={t.topic} className="progress-topic">
            <h3>{t.topic}</h3>
            {t.concepts.map((c) => (
              <div key={c.concept} className="progress-row">
                <span className="progress-concept">{c.concept}</span>
                <span className="mastery-bar">
                  <span className="mastery-fill" style={{ width: `${Math.round(c.mastery * 100)}%` }} />
                </span>
                <span className="progress-num">{c.correct}/{c.attempts}</span>
              </div>
            ))}
          </div>
        ))
      )}
      <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
    </Card>
  );
}
