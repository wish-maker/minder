import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  BackupsPage,
  JobRow,
  RestoreControl,
  type BackupArchive,
  type BackupJob,
} from "./BackupsPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

let mockAuth = { token: "", role: "" };
vi.mock("../lib/auth", () => ({
  useAuth: () => mockAuth,
}));

function archive(overrides: Partial<BackupArchive> = {}): BackupArchive {
  return {
    name: "minder-20260101-000000.tar.gz",
    size_bytes: 5_242_880,
    modified_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function job(overrides: Partial<BackupJob> = {}): BackupJob {
  return {
    id: "abc123",
    action: "backup",
    archive: null,
    status: "done",
    requested_by: "alice",
    requested_at: "2026-01-01T00:00:00Z",
    started_at: "2026-01-01T00:00:01Z",
    finished_at: "2026-01-01T00:00:05Z",
    error: null,
    output: "",
    ...overrides,
  };
}

describe("RestoreControl", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("keeps the confirm button disabled until the typed text exactly matches the filename", () => {
    render(
      <RestoreControl archive={archive()} token="tok" onRestored={vi.fn()} />,
    );
    fireEvent.click(screen.getByText("Restore…"));

    const confirmButton = screen.getByRole("button", { name: "Confirm Restore" });
    expect(confirmButton.hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByPlaceholderText(archive().name), {
      target: { value: "minder-20260101-000000" },
    });
    expect(confirmButton.hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByPlaceholderText(archive().name), {
      target: { value: archive().name },
    });
    expect(confirmButton.hasAttribute("disabled")).toBe(false);
  });

  it("posts confirm_filename and calls onRestored on success", async () => {
    apiFetch.mockResolvedValue({});
    const onRestored = vi.fn();
    render(
      <RestoreControl archive={archive()} token="tok" onRestored={onRestored} />,
    );
    fireEvent.click(screen.getByText("Restore…"));
    fireEvent.change(screen.getByPlaceholderText(archive().name), {
      target: { value: archive().name },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm Restore" }));

    await vi.waitFor(() => expect(onRestored).toHaveBeenCalled());
    expect(apiFetch).toHaveBeenCalledWith(
      `/v1/backups/${archive().name}/restore`,
      { method: "POST", token: "tok", body: { confirm_filename: archive().name } },
    );
  });

  it("shows a friendly error and stays expanded on failure", async () => {
    apiFetch.mockRejectedValue(new Error("confirm_filename must exactly match"));
    render(
      <RestoreControl archive={archive()} token="tok" onRestored={vi.fn()} />,
    );
    fireEvent.click(screen.getByText("Restore…"));
    fireEvent.change(screen.getByPlaceholderText(archive().name), {
      target: { value: archive().name },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm Restore" }));

    await screen.findByText("confirm_filename must exactly match");
    expect(screen.getByRole("button", { name: "Confirm Restore" })).toBeTruthy();
  });

  it("collapses back to the plain Restore… button on Cancel", () => {
    render(
      <RestoreControl archive={archive()} token="tok" onRestored={vi.fn()} />,
    );
    fireEvent.click(screen.getByText("Restore…"));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByText("Restore…")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Confirm Restore" })).toBeNull();
  });
});

describe("JobRow", () => {
  afterEach(cleanup);

  it("renders a backup job with its status badge", () => {
    render(<JobRow job={job()} />);
    expect(screen.getByText("💾 Backup")).toBeTruthy();
    expect(screen.getByText("done")).toBeTruthy();
    expect(screen.getByText(/requested by alice/)).toBeTruthy();
  });

  it("renders a restore job's archive name and error detail", () => {
    render(
      <JobRow
        job={job({
          action: "restore",
          archive: "minder-20260101-000000.tar.gz",
          status: "error",
          error: "archive not found",
        })}
      />,
    );
    expect(screen.getByText("♻️ Restore")).toBeTruthy();
    expect(screen.getByText("minder-20260101-000000.tar.gz")).toBeTruthy();
    expect(screen.getByText("error")).toBeTruthy();
    expect(screen.getByText("archive not found")).toBeTruthy();
  });
});

describe("BackupsPage", () => {
  afterEach(() => {
    apiFetch.mockReset();
    mockAuth = { token: "", role: "" };
    cleanup();
  });

  it("shows an admin-required hint and never fetches when logged out", () => {
    render(<BackupsPage />);
    expect(
      screen.getByText("Log in as an admin to view or manage backups."),
    ).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("shows an admin-required hint (different copy) when logged in as a non-admin", () => {
    mockAuth = { token: "tok", role: "user" };
    render(<BackupsPage />);
    expect(
      screen.getByText("Admin role required to view or manage backups."),
    ).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("fetches and renders archives and jobs for an admin", async () => {
    mockAuth = { token: "tok", role: "admin" };
    apiFetch.mockImplementation((path: string) => {
      if (path === "/v1/backups") {
        return Promise.resolve({ archives: [archive()] });
      }
      if (path === "/v1/backups/jobs") {
        return Promise.resolve({ jobs: [job()] });
      }
      throw new Error(`unexpected path ${path}`);
    });
    render(<BackupsPage />);

    await screen.findByText(archive().name);
    expect(screen.getByText("💾 Backup")).toBeTruthy();
  });

  it("shows empty states when there are no archives or jobs", async () => {
    mockAuth = { token: "tok", role: "admin" };
    apiFetch.mockResolvedValue({ archives: [], jobs: [] });
    render(<BackupsPage />);

    await screen.findByText("No backup archives yet — trigger one above.");
    expect(screen.getByText("No jobs yet.")).toBeTruthy();
  });

  it("triggers a backup and reloads jobs", async () => {
    mockAuth = { token: "tok", role: "admin" };
    apiFetch.mockImplementation((path: string, opts?: { method?: string }) => {
      if (opts?.method === "POST") return Promise.resolve(job());
      if (path === "/v1/backups") return Promise.resolve({ archives: [] });
      return Promise.resolve({ jobs: [] });
    });
    render(<BackupsPage />);
    await screen.findByText("No backup archives yet — trigger one above.");

    fireEvent.click(screen.getByRole("button", { name: "💾 Trigger Backup" }));

    await screen.findByText("Backup job enqueued — see Recent Jobs below.");
    expect(apiFetch).toHaveBeenCalledWith("/v1/backups", {
      method: "POST",
      token: "tok",
    });
  });
});
