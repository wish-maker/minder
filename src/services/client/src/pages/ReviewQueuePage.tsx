import { useCallback, useEffect, useId, useState } from "react";

import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { apiFetch, friendlyErrorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  badgeClass,
  cardClass,
  destructiveButtonClass,
  inputClass,
  mutedTextClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "../lib/ui";
import { submissionStatusBadgeColor, type Submission } from "./SubmissionsPage";

interface SubmissionListResponse {
  plugins: Submission[];
}

const STATUS_FILTERS: Submission["status"][] = [
  "submitted",
  "in_review",
  "rejected",
  "approved",
  "archived",
  "draft",
  "pending",
];

// Mirrors core/review.py's ALLOWED_TRANSITIONS exactly -- only the reviewer
// (not the submission's own developer) actions this page exposes.
function reviewerActionsFor(status: Submission["status"]): Array<"claim" | "approve" | "reject" | "archive"> {
  if (status === "submitted") return ["claim", "reject"];
  if (status === "in_review") return ["approve", "reject"];
  if (status === "approved") return ["archive"];
  if (status === "pending") return ["approve", "reject", "archive"];
  return []; // draft, rejected, archived -- nothing a reviewer can do here
}

function RejectForm({
  onConfirm,
  onCancel,
  busy,
}: {
  onConfirm: (notes: string) => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const idBase = useId();
  const [notes, setNotes] = useState("");

  return (
    <div className="mt-2 rounded-lg border border-gray-200 p-3 dark:border-gray-700">
      <label
        htmlFor={`${idBase}-notes`}
        className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
      >
        Feedback for the developer (required)
      </label>
      <textarea
        id={`${idBase}-notes`}
        className={inputClass}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        rows={2}
        placeholder="What needs to change before this can be resubmitted?"
      />
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={busy || !notes.trim()}
          onClick={() => onConfirm(notes.trim())}
          className={destructiveButtonClass}
        >
          Confirm reject
        </button>
        <button type="button" onClick={onCancel} className={secondaryButtonClass}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function ReviewCard({
  submission,
  onChanged,
}: {
  submission: Submission;
  onChanged: () => void;
}) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  async function runAction(path: string, body?: unknown) {
    setBusy(true);
    setStatusMsg("Working…");
    try {
      await apiFetch(`/v1/marketplace/submissions/${submission.id}${path}`, {
        method: "POST",
        token,
        body,
      });
      setRejecting(false);
      onChanged();
    } catch (err) {
      setStatusMsg(friendlyErrorMessage(err), true);
      setBusy(false);
    }
  }

  const actions = reviewerActionsFor(submission.status);

  return (
    <section className={`mb-4 ${cardClass}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-gray-900 dark:text-gray-100">
            <span aria-hidden="true">🧩</span> {submission.display_name}
          </h3>
          {submission.description && (
            <p className="mt-0.5 text-sm text-gray-600 dark:text-gray-400">
              {submission.description}
            </p>
          )}
          <p className={`mt-1 ${mutedTextClass}`}>
            {submission.name} · by {submission.author} · {submission.pricing_model}
          </p>
        </div>
        <span
          className={`${badgeClass} ${submissionStatusBadgeColor(submission.status)} flex-shrink-0`}
        >
          {submission.status.replace("_", " ")}
        </span>
      </div>

      {submission.review_notes && (
        <p className="mt-3 rounded-lg bg-gray-50 p-2 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300">
          <strong>Previous feedback:</strong> {submission.review_notes}
        </p>
      )}

      {actions.length === 0 && (
        <p className={`mt-3 ${mutedTextClass}`}>
          No reviewer action available in this status.
        </p>
      )}

      {actions.length > 0 && !rejecting && (
        <div className="mt-3 flex gap-2">
          {actions.includes("claim") && (
            <button
              disabled={busy}
              onClick={() => runAction("/claim")}
              className={primaryButtonClass}
            >
              Claim
            </button>
          )}
          {actions.includes("approve") && (
            <button
              disabled={busy}
              onClick={() => runAction("/approve")}
              className={primaryButtonClass}
            >
              Approve
            </button>
          )}
          {actions.includes("reject") && (
            <button
              disabled={busy}
              onClick={() => setRejecting(true)}
              className={destructiveButtonClass}
            >
              Reject
            </button>
          )}
          {actions.includes("archive") && (
            <button
              disabled={busy}
              onClick={() => runAction("/archive")}
              className={secondaryButtonClass}
            >
              Archive
            </button>
          )}
        </div>
      )}

      {rejecting && (
        <RejectForm
          busy={busy}
          onCancel={() => setRejecting(false)}
          onConfirm={(notes) => runAction("/reject", { notes })}
        />
      )}

      <StatusLine isError={isError}>{status}</StatusLine>
    </section>
  );
}

export function ReviewQueuePage() {
  const { token, role, isAuthenticated } = useAuth();
  const isAdmin = role === "admin";
  const [statusFilter, setStatusFilter] = useState<Submission["status"]>("submitted");
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const loadQueue = useCallback(async () => {
    if (!isAdmin) return;
    setStatusMsg("Loading review queue…");
    try {
      const res = await apiFetch<SubmissionListResponse>(
        `/v1/marketplace/submissions?status=${statusFilter}`,
        { token },
      );
      setSubmissions(res.plugins);
      setStatusMsg("");
    } catch (err) {
      setStatusMsg(friendlyErrorMessage(err), true);
    }
  }, [isAdmin, statusFilter, token, setStatusMsg]);

  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  if (!isAuthenticated || !isAdmin) {
    return (
      <>
        <PageHeader icon="🗂️" title="Review Queue" />
        <EmptyState>
          Admins only — log in with an admin account to review plugin
          submissions.
        </EmptyState>
      </>
    );
  }

  return (
    <>
      <PageHeader icon="🗂️" title="Review Queue" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Developer-submitted plugins waiting on admin review. Oldest first.
      </p>

      <div className="mb-4 flex items-center gap-2">
        <label htmlFor="review-status-filter" className={mutedTextClass}>
          Status
        </label>
        <select
          id="review-status-filter"
          className={`${inputClass} max-w-xs`}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as Submission["status"])}
        >
          {STATUS_FILTERS.map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </select>
      </div>

      <StatusLine isError={isError}>{status}</StatusLine>

      {submissions.length === 0 ? (
        <EmptyState>No submissions in status "{statusFilter.replace("_", " ")}".</EmptyState>
      ) : (
        submissions.map((s) => (
          <ReviewCard key={s.id} submission={s} onChanged={loadQueue} />
        ))
      )}
    </>
  );
}
