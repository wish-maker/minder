import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Bundle } from "../lib/bundles";
import { ExportImportPanel } from "./InstalledBundlesPage";

const apiFetch = vi.fn();
const onChanged = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
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
