import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ConfigurePanel,
  InstalledPluginCard,
  type Installation,
} from "./InstalledPluginsPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

function installation(overrides: Partial<Installation> = {}): Installation {
  return {
    installation_id: "inst-1",
    plugin_id: "plugin-1",
    version: "1.0.0",
    status: "active",
    enabled: true,
    installed_at: "2026-01-01T00:00:00Z",
    last_updated_at: "2026-01-01T00:00:00Z",
    name: "my-plugin",
    display_name: "My Plugin",
    description: null,
    current_version: "1.0.0",
    pricing_model: "free",
    base_tier: "free",
    category_id: null,
    author: null,
    requires_services: [],
    ...overrides,
  };
}

afterEach(() => {
  apiFetch.mockReset();
  cleanup();
});

describe("InstalledPluginCard — enable/disable", () => {
  it("disables an enabled plugin and reports the new state", async () => {
    apiFetch.mockResolvedValue({});
    const onToggleEnabled = vi.fn();
    render(
      <InstalledPluginCard
        installation={installation({ enabled: true })}
        token="tok"
        onUninstalled={vi.fn()}
        onToggleEnabled={onToggleEnabled}
        confirm={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Disable" }));

    await waitFor(() =>
      expect(onToggleEnabled).toHaveBeenCalledWith("plugin-1", false),
    );
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/marketplace/plugins/plugin-1/disable",
      { method: "POST", token: "tok" },
    );
  });

  it("enables a disabled plugin and reports the new state", async () => {
    apiFetch.mockResolvedValue({});
    const onToggleEnabled = vi.fn();
    render(
      <InstalledPluginCard
        installation={installation({ enabled: false })}
        token="tok"
        onUninstalled={vi.fn()}
        onToggleEnabled={onToggleEnabled}
        confirm={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Enable" }));

    await waitFor(() =>
      expect(onToggleEnabled).toHaveBeenCalledWith("plugin-1", true),
    );
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/marketplace/plugins/plugin-1/enable",
      { method: "POST", token: "tok" },
    );
  });

  it("shows a friendly error and does not report a toggle on failure", async () => {
    apiFetch.mockRejectedValue(new Error("plugin-registry unreachable"));
    const onToggleEnabled = vi.fn();
    render(
      <InstalledPluginCard
        installation={installation({ enabled: true })}
        token="tok"
        onUninstalled={vi.fn()}
        onToggleEnabled={onToggleEnabled}
        confirm={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Disable" }));

    await screen.findByText("plugin-registry unreachable");
    expect(onToggleEnabled).not.toHaveBeenCalled();
  });
});

describe("InstalledPluginCard — uninstall", () => {
  it("does not uninstall when the confirmation is declined", async () => {
    const onUninstalled = vi.fn();
    const confirm = vi.fn().mockResolvedValue(false);
    render(
      <InstalledPluginCard
        installation={installation()}
        token="tok"
        onUninstalled={onUninstalled}
        onToggleEnabled={vi.fn()}
        confirm={confirm}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "🗑 Uninstall" }));
    await waitFor(() => expect(confirm).toHaveBeenCalled());

    expect(apiFetch).not.toHaveBeenCalled();
    expect(onUninstalled).not.toHaveBeenCalled();
  });

  it("uninstalls the plugin once confirmed", async () => {
    apiFetch.mockResolvedValue({});
    const onUninstalled = vi.fn();
    const confirm = vi.fn().mockResolvedValue(true);
    render(
      <InstalledPluginCard
        installation={installation()}
        token="tok"
        onUninstalled={onUninstalled}
        onToggleEnabled={vi.fn()}
        confirm={confirm}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "🗑 Uninstall" }));

    await waitFor(() =>
      expect(onUninstalled).toHaveBeenCalledWith("plugin-1"),
    );
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/marketplace/plugins/plugin-1/uninstall",
      { method: "DELETE", token: "tok" },
    );
  });
});

describe("ConfigurePanel", () => {
  it("loads the schema on first expand and shows 'no configurable settings' when not configurable", async () => {
    apiFetch.mockResolvedValue({ configurable: false, schema: [], values: {} });
    render(<ConfigurePanel name="my-plugin" token="tok" />);

    fireEvent.click(screen.getByText("Configure"));

    await screen.findByText("This plugin has no configurable settings.");
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/plugins/my-plugin/config",
      { token: "tok" },
    );
  });

  it("does not re-fetch when re-opened a second time", async () => {
    apiFetch.mockResolvedValue({ configurable: false, schema: [], values: {} });
    render(<ConfigurePanel name="my-plugin" token="tok" />);
    const details = screen.getByText("Configure").closest("details")!;

    fireEvent.click(screen.getByText("Configure"));
    await waitFor(() => expect(details.open).toBe(true));
    await screen.findByText("This plugin has no configurable settings.");

    fireEvent.click(screen.getByText("Configure")); // close
    await waitFor(() => expect(details.open).toBe(false));
    fireEvent.click(screen.getByText("Configure")); // re-open
    await waitFor(() => expect(details.open).toBe(true));

    expect(apiFetch).toHaveBeenCalledTimes(1);
  });

  it("renders form fields and submits edited values", async () => {
    apiFetch.mockResolvedValueOnce({
      configurable: true,
      schema: [{ key: "greeting", type: "string" }],
      values: { greeting: "hello" },
    });
    apiFetch.mockResolvedValueOnce({});
    render(<ConfigurePanel name="my-plugin" token="tok" />);

    fireEvent.click(screen.getByText("Configure"));
    const input = (await screen.findByLabelText("greeting")) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "hi there" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByText("Saved.");
    expect(apiFetch).toHaveBeenLastCalledWith("/v1/plugins/my-plugin/config", {
      method: "PUT",
      body: { greeting: "hi there" },
      token: "tok",
    });
  });

  it("skips an emptied/invalid number field instead of saving null (#field-nan-guard)", async () => {
    apiFetch.mockResolvedValueOnce({
      configurable: true,
      schema: [{ key: "retries", type: "int" }],
      values: { retries: 3 },
    });
    apiFetch.mockResolvedValueOnce({});
    render(<ConfigurePanel name="my-plugin" token="tok" />);

    fireEvent.click(screen.getByText("Configure"));
    const input = (await screen.findByLabelText("retries")) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByText("Saved (left retries unchanged — not a valid number).");
    expect(apiFetch).toHaveBeenLastCalledWith("/v1/plugins/my-plugin/config", {
      method: "PUT",
      body: {},
      token: "tok",
    });
  });

  it("treats an untouched secret field as unchanged, not blanked", async () => {
    apiFetch.mockResolvedValueOnce({
      configurable: true,
      schema: [{ key: "api_key", secret: true }],
      values: { api_key: "***" },
    });
    apiFetch.mockResolvedValueOnce({});
    render(<ConfigurePanel name="my-plugin" token="tok" />);

    fireEvent.click(screen.getByText("Configure"));
    // Leave the secret field blank (its placeholder says "unchanged if left blank")
    // but still touch it, to prove the *value*, not just presence in the DOM, gates it.
    const input = await screen.findByLabelText("api_key");
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByText("Saved.");
    expect(apiFetch).toHaveBeenLastCalledWith("/v1/plugins/my-plugin/config", {
      method: "PUT",
      body: {},
      token: "tok",
    });
  });

  it("shows a friendly error when the config fetch fails", async () => {
    apiFetch.mockRejectedValue(new Error("plugin-registry unreachable"));
    render(<ConfigurePanel name="my-plugin" token="tok" />);

    fireEvent.click(screen.getByText("Configure"));

    await screen.findByText("plugin-registry unreachable");
  });
});
