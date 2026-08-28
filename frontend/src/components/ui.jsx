// Shared component vocabulary.
//
// These are deliberately thin: they wrap the class names that already exist in
// styles.css so every page added later looks like the pages that were here
// before. Nothing here introduces a new visual language — if a component needs a
// look that is not expressible with these, it should add a rule to its own page
// stylesheet rather than change one of these.

import { useCallback, useEffect, useMemo, useState } from "react";

// A white rounded panel. `center` mirrors the existing `.card.center` variant.
export function Card({ children, className = "", center = false, ...rest }) {
  return (
    <div className={`card ${center ? "center" : ""} ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}

// The app's button. `variant` picks one of the three looks already in the CSS:
//   primary — the filled indigo call to action
//   link    — text-only, used for secondary actions
//   quiet   — an outlined button for tertiary actions
export function Button({ variant = "primary", className = "", children, ...rest }) {
  const base =
    variant === "link" ? "link-btn" : variant === "quiet" ? "quiet-btn" : "primary-btn";
  return (
    <button className={`${base} ${className}`.trim()} {...rest}>
      {children}
    </button>
  );
}

// The spinning ring used while something is loading. `label` is announced to
// screen readers and, when `showLabel`, printed beneath the spinner.
export function Spinner({ label = "Loading…", showLabel = false }) {
  return (
    <div className="loading">
      <div className="spinner" aria-hidden="true" />
      <span className="sr-only">{label}</span>
      {showLabel && <p className="loading-msg">{label}</p>}
    </div>
  );
}

// Shown in place of content when a learner has nothing yet. The action is
// optional so it can also be used for "no results" states.
export function EmptyState({ icon = "📭", title, message, action = null }) {
  return (
    <div className="empty-state">
      <div className="empty-icon" aria-hidden="true">{icon}</div>
      <h3>{title}</h3>
      {message && <p className="muted">{message}</p>}
      {action}
    </div>
  );
}

// A transient message pinned to the bottom of the screen. `tone` is
// 'error' | 'success' | 'info'. Dismisses itself after `duration` ms unless
// `duration` is 0, and can always be dismissed by hand.
export function Toast({ message, tone = "error", duration = 6000, onDismiss }) {
  useEffect(() => {
    if (!duration) return undefined;
    const id = setTimeout(() => onDismiss && onDismiss(), duration);
    return () => clearTimeout(id);
  }, [message, duration, onDismiss]);

  if (!message) return null;
  const icon = tone === "success" ? "✅" : tone === "info" ? "ℹ️" : "⚠️";
  return (
    <div className={`toast toast-${tone}`} role="status" aria-live="polite">
      <span className="toast-icon" aria-hidden="true">{icon}</span>
      <span className="toast-message">{message}</span>
      <button className="toast-close" aria-label="Dismiss" onClick={onDismiss}>
        ×
      </button>
    </div>
  );
}

// A horizontal bar. `value` and `max` are in the caller's own units; `tone`
// colours the fill ('indigo' | 'green' | 'amber' | 'red').
export function ProgressBar({ value, max = 100, tone = "indigo", label = null }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, Math.round((value / max) * 100))) : 0;
  return (
    <span
      className="bar"
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label || undefined}
    >
      <span className={`bar-fill bar-${tone}`} style={{ width: `${pct}%` }} />
    </span>
  );
}

// A shimmering grey block standing in for content that is still loading.
export function SkeletonBlock({ width = "100%", height = 16, className = "" }) {
  return (
    <span
      className={`skeleton ${className}`.trim()}
      style={{ width, height: typeof height === "number" ? `${height}px` : height }}
      aria-hidden="true"
    />
  );
}

// Several skeleton lines, for a paragraph-shaped placeholder.
export function SkeletonLines({ lines = 3 }) {
  const widths = ["100%", "96%", "88%", "92%", "76%"];
  return (
    <span className="skeleton-lines">
      {Array.from({ length: lines }, (_, i) => (
        <SkeletonBlock key={i} width={widths[i % widths.length]} />
      ))}
    </span>
  );
}

// Convenience hook for pages that show one toast at a time.
export function useToast() {
  const [toast, setToast] = useState(null); // {message, tone}
  // Both callbacks and the returned object are stable. `Toast` lists `onDismiss`
  // in its effect dependencies, so fresh closures here would clear and restart
  // the dismissal timer on every render of the host page — and a page that
  // re-renders faster than the timeout would never dismiss its toast at all.
  const showToast = useCallback((message, tone = "error") => setToast({ message, tone }), []);
  const clearToast = useCallback(() => setToast(null), []);
  return useMemo(() => ({ toast, showToast, clearToast }), [toast, showToast, clearToast]);
}
