import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Bundle } from "../lib/bundles";
import { ExportImportPanel, InstalledBundlesPage } from "./InstalledBundlesPage";

const apiFetch = vi.fn();
const onChanged = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));
let mockAuth = { token: "tok", role: "admin" };
vi.mock("../lib/auth", () => ({
  useAuth: () => mockAuth,
}));

function bundle(overrides: Partial<Bundle> = {}): Bundle {
  return {
    name: "monitoring",
    core: false,
    enabled: false,
    claims: [],
    services: [],
    ...overrides,
  };
}

// jsdom's Blob/File doesn't implement .text() in this environment -- the
// component only ever calls file.text(), so a plain object satisfying just
// that (not a real File instance) sidesteps the gap entirely.
function fakeFile(text: string) {
  return { text: () => Promise.resolve(text) };
}

async function importFile(content: unknown) {
  const file = fakeFile(JSON.stringify(content));
  const input = screen.getByLabelText("Import bundle state from a JSON file");
  fireEvent.change(input, { target: { files: [file] } });
  await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
}

describe("InstalledBundlesPage", () => {
  afterEach(() => {
    apiFetch.mockReset();
    mockAuth = { token: "tok", role: "admin" };
    cleanup();
  });

  it("shows only the enabled bundles", async () => {
    apiFetch.mockResolvedValue({
      bundles: [
        bundle({ name: "core", enabled: true }),
        bundle({ name: "monitoring", enabled: false }),
        bundle({ name: "voice", enabled: true }),
      ],
      count: 3,
    });
    render(<InstalledBundlesPage />);

    expect(await screen.findByText("core")).toBeTruthy();
    expect(screen.getByText("voice")).toBeTruthy();
    expect(screen.queryByText("monitoring")).toBeNull();
  });

  it("shows an empty state when no bundle is enabled", async () => {
    apiFetch.mockResolvedValue({
      bundles: [bundle({ name: "monitoring", enabled: false })],
      count: 1,
    });
    render(<InstalledBundlesPage />);

    expect(
      await screen.findByText("No bundles are enabled yet — see Available Bundles."),
    ).toBeTruthy();
  });

  it("shows an orphaned-services warning banner listing every orphan", async () => {
    apiFetch.mockResolvedValue({
      bundles: [bundle({ name: "core", enabled: true })],
      count: 1,
      orphaned: ["old-worker", "stale-cache"],
    });
    render(<InstalledBundlesPage />);

    const banner = await screen.findByText(/Orphaned services/);
    expect(banner.textContent).toContain("old-worker, stale-cache");
  });

  it("reconciles successfully and reports the outcome, then reloads", async () => {
    apiFetch
      .mockResolvedValueOnce({ bundles: [bundle({ name: "core", enabled: true })], count: 1 })
      .mockResolvedValueOnce({
        started: ["worker"],
        already_running: [],
        pending_create: [],
        stopped: [],
        already_stopped: [],
        errors: [],
      })
      .mockResolvedValueOnce({ bundles: [bundle({ name: "core", enabled: true })], count: 1 });
    render(<InstalledBundlesPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Reconcile/ }));

    await screen.findByText(/Reconciled: started worker/);
    expect(apiFetch).toHaveBeenCalledWith("/v1/bundles/reconcile", {
      method: "POST",
      token: "tok",
    });
    // Success reload -- a 3rd call beyond the initial load + the reconcile itself.
    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(3));
  });

  it("shows a friendly error when reconcile fails, without reloading", async () => {
    apiFetch
      .mockResolvedValueOnce({ bundles: [bundle({ name: "core", enabled: true })], count: 1 })
      .mockRejectedValueOnce(new Error("plugin-registry unreachable"));
    render(<InstalledBundlesPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Reconcile/ }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("plugin-registry unreachable");
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });

  it("disables Reconcile with a login hint when logged out", async () => {
    mockAuth = { token: "", role: "" };
    apiFetch.mockResolvedValue({ bundles: [bundle({ name: "core", enabled: true })], count: 1 });
    render(<InstalledBundlesPage />);

    const btn = await screen.findByRole("button", { name: /Reconcile/ });
    expect(btn.hasAttribute("disabled")).toBe(true);
    expect(btn.getAttribute("title")).toBe("Log in as an admin to reconcile");
  });

  it("disables Reconcile with an admin-role hint when logged in but not admin", async () => {
    mockAuth = { token: "tok", role: "member" };
    apiFetch.mockResolvedValue({ bundles: [bundle({ name: "core", enabled: true })], count: 1 });
    render(<InstalledBundlesPage />);

    const btn = await screen.findByRole("button", { name: /Reconcile/ });
    expect(btn.hasAttribute("disabled")).toBe(true);
    expect(btn.getAttribute("title")).toBe("Admin role required");
  });
});

describe("ExportImportPanel import logic", () => {
  afterEach(() => {
    apiFetch.mockReset();
    onChanged.mockReset();
    cleanup();
  });

  it("skips an unknown bundle name without calling the API", async () => {
    const bundles = [bundle({ name: "monitoring", enabled: false })];
    render(
      <ExportImportPanel
        bundles={bundles}
        token="tok"
        isAdmin
        onChanged={onChanged}
      />,
    );

    await importFile({ "no-such-bundle": { enabled: true } });

    expect(apiFetch).not.toHaveBeenCalled();
    await screen.findByText(/skipped: no-such-bundle \(unknown bundle\)/);
  });

  it("skips a bundle whose state already matches, without calling the API", async () => {
    const bundles = [bundle({ name: "monitoring", enabled: true })];
    render(
      <ExportImportPanel
        bundles={bundles}
        token="tok"
        isAdmin
        onChanged={onChanged}
      />,
    );

    await importFile({ monitoring: { enabled: true } });

    expect(apiFetch).not.toHaveBeenCalled();
    await screen.findByText("Nothing to change.");
  });

  it("refuses to disable a core bundle, without calling the API", async () => {
    const bundles = [
      bundle({ name: "core-services", core: true, enabled: true }),
    ];
    render(
      <ExportImportPanel
        bundles={bundles}
        token="tok"
        isAdmin
        onChanged={onChanged}
      />,
    );

    await importFile({ "core-services": { enabled: false } });

    expect(apiFetch).not.toHaveBeenCalled();
    await screen.findByText(/skipped: core-services \(core can't be disabled\)/);
  });

  it("enables a bundle whose desired state differs from current", async () => {
    apiFetch.mockResolvedValue({});
    const bundles = [bundle({ name: "monitoring", enabled: false })];
    render(
      <ExportImportPanel
        bundles={bundles}
        token="tok"
        isAdmin
        onChanged={onChanged}
      />,
    );

    await importFile({ monitoring: { enabled: true } });

    expect(apiFetch).toHaveBeenCalledWith("/v1/bundles/monitoring/enable", {
      method: "POST",
      token: "tok",
    });
    await screen.findByText(/applied: monitoring/);
  });

  it("records a per-bundle API failure without aborting the rest of the import", async () => {
    apiFetch.mockImplementation((url: string) =>
      url.includes("monitoring")
        ? Promise.reject(new Error("plugin-registry unreachable"))
        : Promise.resolve({}),
    );
    const bundles = [
      bundle({ name: "monitoring", enabled: false }),
      bundle({ name: "voice", enabled: false }),
    ];
    render(
      <ExportImportPanel
        bundles={bundles}
        token="tok"
        isAdmin
        onChanged={onChanged}
      />,
    );

    await importFile({
      monitoring: { enabled: true },
      voice: { enabled: true },
    });

    await screen.findByText(/applied: voice/);
    expect(screen.getByText(/errors: monitoring: plugin-registry unreachable/))
      .toBeTruthy();
  });

  it("surfaces the real parse error for a file that isn't valid JSON", async () => {
    const bundles = [bundle()];
    render(
      <ExportImportPanel
        bundles={bundles}
        token="tok"
        isAdmin
        onChanged={vi.fn()}
      />,
    );

    const file = fakeFile("not json");
    const input = screen.getByLabelText("Import bundle state from a JSON file");
    fireEvent.change(input, { target: { files: [file] } });

    // JSON.parse's own SyntaxError message -- it IS an Error instance, so the
    // component's "Could not read that file..." fallback (for a non-Error
    // throw) is never reached on this path; asserting the real message
    // catches a regression that swallowed it into the generic fallback.
    await screen.findByText(/is not valid JSON/);
  });
});
