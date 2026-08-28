// Tells a learner when a chapter was written from standby material rather than
// from their textbook, and offers another attempt.
//
// The system has always had this fallback: if the model's reply cannot be
// parsed twice over, a canned chapter is served so the learner is never blocked.
// That behaviour is right and is unchanged. What was wrong is that it happened
// in silence — the chapter simply arrived with no page references and nothing
// said so. This is the disclosure.
//
// It renders nothing at all in the ordinary case, which is the overwhelming
// majority of chapters.

import { useEffect, useState } from "react";

import { getGenerationStatus, retryChapter } from "../api";
import { Button, Spinner, Toast, useToast } from "./ui";
import "../styles/robustness.css";

export default function FallbackNotice({ sessionId, chapterId, onRetried = null }) {
  const { toast, showToast, clearToast } = useToast();
  const [status, setStatus] = useState(null);
  const [retrying, setRetrying] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  // Ask whether this chapter came from the textbook. A failure here is not worth
  // troubling the learner with — it only means the notice cannot be shown — so it
  // fails quietly and the chapter reads as normal.
  useEffect(() => {
    let cancelled = false;
    setStatus(null);
    setDismissed(false);
    if (!chapterId) return undefined;
    getGenerationStatus(chapterId)
      .then((data) => { if (!cancelled) setStatus(data); })
      .catch(() => { if (!cancelled) setStatus({ used_fallback: false }); });
    return () => { cancelled = true; };
  }, [chapterId]);

  async function handleRetry() {
    setRetrying(true);
    try {
      const result = await retryChapter(sessionId, chapterId);
      if (result.succeeded) {
        showToast(result.message, "success");
        setStatus({ ...status, used_fallback: false });
        if (onRetried) onRetried(result);
      } else {
        showToast(result.message, "info");
      }
    } catch (e) {
      showToast(e.message);
    } finally {
      setRetrying(false);
    }
  }

  if (!status || !status.used_fallback || dismissed) return null;

  return (
    <div className="fallback-notice" role="status">
      <span className="fallback-icon" aria-hidden="true">📝</span>
      <div className="fallback-body">
        <p className="fallback-title">This chapter came from our standby material</p>
        <p className="fallback-text">
          It was not written from your textbook this time, so it has no page references.
          The science in it is still correct, and you can carry on reading — or ask for
          another go.
        </p>
        <div className="fallback-actions">
          {status.can_retry ? (
            <Button variant="quiet" onClick={handleRetry} disabled={retrying}>
              {retrying ? "Trying again…" : "Try again"}
            </Button>
          ) : (
            status.retry_blocked_reason && (
              <span className="fallback-blocked">{status.retry_blocked_reason}</span>
            )
          )}
          <Button variant="link" onClick={() => setDismissed(true)}>Hide this</Button>
        </div>
        {retrying && <Spinner label="Writing this chapter again…" />}
      </div>
      <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
    </div>
  );
}
