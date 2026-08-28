// /story/:id — the reading surface.
//
// When the id matches the story currently held in memory, this renders the
// interactive reader (and, once the story ends, the results card) exactly as the
// old single-component app did. For any other id it falls back to the read-only
// replay, which is what "read again" from My Stories opens.

import { useNavigate, useParams } from "react-router-dom";

import Loading from "../components/Loading";
import StoryArchive from "../components/StoryArchive";
import StoryReader, { BadgeList } from "../components/StoryReader";
import { useSession } from "../session";

export default function StoryPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const session = useSession();
  const isLive = String(session.sessionId) === String(id);

  if (isLive && session.generating) {
    return <div className="card"><Loading /></div>;
  }

  if (isLive && session.isComplete) {
    return (
      <CompleteCard
        points={session.points}
        badges={session.badges}
        onRestart={() => { session.reset(); navigate("/"); }}
        onShowProgress={() => navigate("/progress")}
      />
    );
  }

  if (isLive && session.chapter) {
    return (
      <StoryReader
        chapter={session.chapter}
        sessionId={session.sessionId}
        grade={session.grade}
        resumed={session.resumed}
        sources={session.sources}
        points={session.points}
        difficulty={session.difficulty}
        totalChapters={session.totalChapters}
        badges={session.badges}
        justEarned={session.justEarned}
        answers={session.answers}
        chapterComplete={session.chapterComplete}
        loading={session.loading}
        onAnswer={session.answer}
        onNext={session.next}
        onFinish={session.finish}
      />
    );
  }

  return <StoryArchive sessionId={id} />;
}

// The results card shown at the end of a story (formerly CompleteScreen).
function CompleteCard({ points, badges, onRestart, onShowProgress }) {
  return (
    <div className="card center">
      <h2>🎉 Session complete!</h2>
      <p className="final-points">{points} points</p>
      <p className="field-label">Badges earned</p>
      {badges.length ? (
        <BadgeList badges={badges} />
      ) : (
        <p className="muted">No badges this time — try again to earn some!</p>
      )}
      <button className="primary-btn" onClick={onRestart}>Start over</button>
      <p className="auth-switch">
        <button className="link-btn" onClick={onShowProgress}>📊 My progress</button>
      </p>
    </div>
  );
}
