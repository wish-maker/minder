import { Component, type ErrorInfo, type ReactNode } from "react";

import { primaryButtonClass, secondaryButtonClass } from "../lib/ui";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Top-level render-crash guard. Before this, any exception thrown while
 * rendering a page (e.g. calling `.map` on a value whose shape changed) unwound
 * the whole React tree to a blank/black screen with no way back — the failure
 * mode that a stale client vs. a #501-envelope backend produced live. This
 * catches the throw, keeps the app shell, and offers a recoverable fallback
 * (navigate elsewhere via the sidebar, or reload) instead of a dead screen.
 *
 * React error boundaries MUST be class components — there is no hook equivalent.
 * Wrapped per-route (keyed by pathname in App) so moving to another page clears
 * the error automatically. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surfaced to the console for debugging; not sent anywhere (no telemetry).
    console.error("Unhandled render error:", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        role="alert"
        className="mx-auto max-w-lg rounded-xl border border-red-200 bg-red-50 p-6 dark:border-red-900 dark:bg-red-950"
      >
        <h1 className="mb-1 text-lg font-semibold text-red-800 dark:text-red-200">
          This page hit an unexpected error
        </h1>
        <p className="mb-4 text-sm text-red-700 dark:text-red-300">
          The rest of the app still works — pick another page from the menu, or
          reload to try again.
        </p>
        <pre className="mb-4 max-h-40 overflow-auto rounded-md bg-white/60 p-3 text-xs text-red-900 dark:bg-black/30 dark:text-red-200">
          {error.message || String(error)}
        </pre>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className={secondaryButtonClass}
          >
            Try again
          </button>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className={primaryButtonClass}
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
