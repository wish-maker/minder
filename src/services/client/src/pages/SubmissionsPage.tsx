import { useCallback, useEffect, useId, useState } from "react";

import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { apiFetch, friendlyErrorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  badgeClass,
  badgeTone,
  cardClass,
  fieldHintClass,
  inputClass,
  mutedTextClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "../lib/ui";

export type SubmissionStatus =
  | "draft"
  | "submitted"
  | "in_review"
  | "approved"
  | "rejected"
  | "archived"
  | "pending";

export interface Submission {
  id: string;
  name: string;
  display_name: string;
  description: string | null;
  author: string;
  repository_url: string | null;
  distribution_type: "git" | "docker" | "hybrid";
  docker_image: string | null;
  pricing_model: "free" | "paid" | "freemium";
  base_tier: string;
  status: SubmissionStatus;
  review_notes: string | null;
  requires_services: string[];
}

interface SubmissionListResponse {
  plugins: Submission[];
}

// Own submission's editable fields (#402 follow-up) -- mirrors backend's
// _OWNER_UPDATABLE in routes/marketplace.py exactly: never name/status/featured
// via this form; status only moves through the submit/claim/approve/reject
// endpoints below, and only an admin can set `featured`.
const DISTRIBUTION_TYPES = ["git", "docker", "hybrid"] as const;
const PRICING_MODELS = ["free", "paid", "freemium"] as const;

// A draft/rejected submission is the only state its own developer may still
// edit or (re)submit -- once claimed/approved/archived it's read-only here
// (matches core/review.py's ALLOWED_TRANSITIONS: only draft/rejected -> submitted).
const EDITABLE_STATUSES: SubmissionStatus[] = ["draft", "rejected"];

export function submissionStatusBadgeColor(status: SubmissionStatus): string {
  if (status === "approved") return badgeTone.success;
  if (status === "rejected") return badgeTone.danger;
  if (status === "submitted" || status === "in_review") return badgeTone.warn;
  return ""; // draft/archived/pending -- neutral badgeClass alone
}

function NewSubmissionForm({ onCreated }: { onCreated: () => void }) {
  const { token } = useAuth();
  const idBase = useId();
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [author, setAuthor] = useState("");
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [distributionType, setDistributionType] =
    useState<(typeof DISTRIBUTION_TYPES)[number]>("git");
  const [dockerImage, setDockerImage] = useState("");
  const [pricingModel, setPricingModel] =
    useState<(typeof PRICING_MODELS)[number]>("free");
  const [baseTier, setBaseTier] = useState("community");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setStatusMsg("Creating draft…");
    try {
      await apiFetch("/v1/marketplace/plugins", {
        method: "POST",
        token,
        body: {
          name,
          display_name: displayName,
          description: description.trim() || null,
          author,
          repository_url: repositoryUrl.trim() || null,
          distribution_type: distributionType,
          docker_image: dockerImage.trim() || null,
          pricing_model: pricingModel,
          base_tier: baseTier,
        },
      });
      setName("");
      setDisplayName("");
      setDescription("");
      setAuthor("");
      setRepositoryUrl("");
      setDockerImage("");
      setStatusMsg(
        "Draft created below — edit it, then submit it for review when ready.",
      );
      onCreated();
    } catch (err) {
      setStatusMsg(friendlyErrorMessage(err), true);
    }
    setBusy(false);
  }

  return (
    <form onSubmit={handleSubmit} className={`mb-6 ${cardClass}`}>
      <h2 className="mb-3 text-base font-semibold text-gray-900 dark:text-gray-100">
        Submit a new plugin
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label
            htmlFor={`${idBase}-name`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Name (slug)
          </label>
          <input
            id={`${idBase}-name`}
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
          />
        </div>
        <div>
          <label
            htmlFor={`${idBase}-display`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Display name
          </label>
          <input
            id={`${idBase}-display`}
            className={inputClass}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            maxLength={200}
          />
        </div>
        <div className="sm:col-span-2">
          <label
            htmlFor={`${idBase}-desc`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Description
          </label>
          <textarea
            id={`${idBase}-desc`}
            className={inputClass}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
          />
        </div>
        <div>
          <label
            htmlFor={`${idBase}-author`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Author
          </label>
          <input
            id={`${idBase}-author`}
            className={inputClass}
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            required
            maxLength={100}
          />
        </div>
        <div>
          <label
            htmlFor={`${idBase}-repo`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Repository URL
          </label>
          <input
            id={`${idBase}-repo`}
            type="url"
            className={inputClass}
            value={repositoryUrl}
            onChange={(e) => setRepositoryUrl(e.target.value)}
            placeholder="https://github.com/you/plugin"
          />
        </div>
        <div>
          <label
            htmlFor={`${idBase}-dist`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Distribution type
          </label>
          <select
            id={`${idBase}-dist`}
            className={inputClass}
            value={distributionType}
            onChange={(e) =>
              setDistributionType(
                e.target.value as (typeof DISTRIBUTION_TYPES)[number],
              )
            }
          >
            {DISTRIBUTION_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor={`${idBase}-image`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Docker image
          </label>
          <input
            id={`${idBase}-image`}
            className={inputClass}
            value={dockerImage}
            onChange={(e) => setDockerImage(e.target.value)}
            placeholder="org/name:tag"
          />
        </div>
        <div>
          <label
            htmlFor={`${idBase}-pricing`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Pricing model
          </label>
          <select
            id={`${idBase}-pricing`}
            className={inputClass}
            value={pricingModel}
            onChange={(e) =>
              setPricingModel(e.target.value as (typeof PRICING_MODELS)[number])
            }
          >
            {PRICING_MODELS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor={`${idBase}-tier`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Base tier
          </label>
          <input
            id={`${idBase}-tier`}
            className={inputClass}
            value={baseTier}
            onChange={(e) => setBaseTier(e.target.value)}
          />
        </div>
      </div>
      <p className={`mt-2 ${fieldHintClass}`}>
        Creates a draft only — nothing is visible to anyone else until an
        admin reviews and approves it.
      </p>
      <button type="submit" disabled={busy} className={`mt-3 ${primaryButtonClass}`}>
        Create draft
      </button>
      <StatusLine isError={isError}>{status}</StatusLine>
    </form>
  );
}

function EditSubmissionForm({
  submission,
  onSaved,
  onCancel,
}: {
  submission: Submission;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const { token } = useAuth();
  const idBase = useId();
  const [displayName, setDisplayName] = useState(submission.display_name);
  const [description, setDescription] = useState(submission.description ?? "");
  const [author, setAuthor] = useState(submission.author);
  const [pricingModel, setPricingModel] = useState(submission.pricing_model);
  const [baseTier, setBaseTier] = useState(submission.base_tier);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setStatusMsg("Saving…");
    try {
      // Deliberately never sends status/featured -- the backend 403s a
      // non-admin for those (self-approval is the exact bug #929 closed).
      await apiFetch(`/v1/marketplace/plugins/${submission.id}`, {
        method: "PUT",
        token,
        body: {
          display_name: displayName,
          description: description.trim() || null,
          author,
          pricing_model: pricingModel,
          base_tier: baseTier,
        },
      });
      onSaved();
    } catch (err) {
      setStatusMsg(friendlyErrorMessage(err), true);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSave} className="mt-3 rounded-lg border border-gray-200 p-3 dark:border-gray-700">
      <div className="grid gap-2 sm:grid-cols-2">
        <div>
          <label
            htmlFor={`${idBase}-display`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Display name
          </label>
          <input
            id={`${idBase}-display`}
            className={inputClass}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
          />
        </div>
        <div>
          <label
            htmlFor={`${idBase}-author`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Author
          </label>
          <input
            id={`${idBase}-author`}
            className={inputClass}
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            required
          />
        </div>
        <div className="sm:col-span-2">
          <label
            htmlFor={`${idBase}-desc`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Description
          </label>
          <textarea
            id={`${idBase}-desc`}
            className={inputClass}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
          />
        </div>
        <div>
          <label
            htmlFor={`${idBase}-pricing`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Pricing model
          </label>
          <select
            id={`${idBase}-pricing`}
            className={inputClass}
            value={pricingModel}
            onChange={(e) =>
              setPricingModel(e.target.value as Submission["pricing_model"])
            }
          >
            {PRICING_MODELS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor={`${idBase}-tier`}
            className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300"
          >
            Base tier
          </label>
          <input
            id={`${idBase}-tier`}
            className={inputClass}
            value={baseTier}
            onChange={(e) => setBaseTier(e.target.value)}
          />
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <button type="submit" disabled={busy} className={primaryButtonClass}>
          Save
        </button>
        <button type="button" onClick={onCancel} className={secondaryButtonClass}>
          Cancel
        </button>
      </div>
      <StatusLine isError={isError}>{status}</StatusLine>
    </form>
  );
}

function SubmissionCard({
  submission,
  onChanged,
}: {
  submission: Submission;
  onChanged: () => void;
}) {
  const { token } = useAuth();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  async function handleSubmitForReview() {
    setBusy(true);
    setStatusMsg("Submitting for review…");
    try {
      await apiFetch(`/v1/marketplace/submissions/${submission.id}/submit`, {
        method: "POST",
        token,
      });
      onChanged();
    } catch (err) {
      setStatusMsg(friendlyErrorMessage(err), true);
    }
    setBusy(false);
  }

  const editable = EDITABLE_STATUSES.includes(submission.status);

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
            {submission.name} · {submission.pricing_model} · {submission.base_tier}
          </p>
        </div>
        <span
          className={`${badgeClass} ${submissionStatusBadgeColor(submission.status)} flex-shrink-0`}
        >
          {submission.status.replace("_", " ")}
        </span>
      </div>

      {submission.status === "rejected" && submission.review_notes && (
        <p className="mt-3 rounded-lg bg-red-50 p-2 text-xs text-red-900 dark:bg-red-950 dark:text-red-100">
          <strong>Reviewer feedback:</strong> {submission.review_notes}
        </p>
      )}

      {editable && !editing && (
        <div className="mt-3 flex gap-2">
          <button onClick={() => setEditing(true)} className={secondaryButtonClass}>
            Edit
          </button>
          <button
            onClick={handleSubmitForReview}
            disabled={busy}
            className={primaryButtonClass}
          >
            {submission.status === "rejected" ? "Resubmit for review" : "Submit for review"}
          </button>
        </div>
      )}

      {editable && editing && (
        <EditSubmissionForm
          submission={submission}
          onCancel={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            onChanged();
          }}
        />
      )}

      <StatusLine isError={isError}>{status}</StatusLine>
    </section>
  );
}

export function SubmissionsPage() {
  const { token, isAuthenticated } = useAuth();
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const loadMine = useCallback(async () => {
    if (!isAuthenticated) {
      setSubmissions([]);
      return;
    }
    setStatusMsg("Loading your submissions…");
    try {
      const res = await apiFetch<SubmissionListResponse>(
        "/v1/marketplace/submissions/mine",
        { token },
      );
      setSubmissions(res.plugins);
      setStatusMsg("");
    } catch (err) {
      setStatusMsg(friendlyErrorMessage(err), true);
    }
  }, [isAuthenticated, token, setStatusMsg]);

  useEffect(() => {
    loadMine();
  }, [loadMine]);

  return (
    <>
      <PageHeader icon="📝" title="Submit a Plugin" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Publish your own plugin to the Minder marketplace. Every submission
        starts as a private draft and goes through an admin review before
        anyone else can see or install it.
      </p>

      {!isAuthenticated ? (
        <EmptyState>Log in to submit a plugin or see your own submissions.</EmptyState>
      ) : (
        <>
          <NewSubmissionForm onCreated={loadMine} />
          <StatusLine isError={isError}>{status}</StatusLine>

          <h2 className="mb-2 text-base font-semibold text-gray-900 dark:text-gray-100">
            Your submissions
          </h2>
          {submissions.length === 0 ? (
            <EmptyState>You haven't submitted any plugins yet.</EmptyState>
          ) : (
            submissions.map((s) => (
              <SubmissionCard key={s.id} submission={s} onChanged={loadMine} />
            ))
          )}
        </>
      )}
    </>
  );
}
