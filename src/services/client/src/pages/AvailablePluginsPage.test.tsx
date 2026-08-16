import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PluginCard, type Installation, type Plugin } from "./AvailablePluginsPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));
vi.mock("react-router-dom", () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

function plugin(overrides: Partial<Plugin> = {}): Plugin {
  return {
    id: "p1",
    name: "weather",
    display_name: "Weather",
    description: "Current weather lookups",
    author: "Minder",
    repository_url: null,
    distribution_type: "docker",
    docker_image: null,
    current_version: "1.0.0",
    pricing_model: "free",
    base_tier: "community",
    status: "approved",
    featured: false,
    download_count: 3,
    rating_average: null,
    rating_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    published_at: null,
    developer_id: null,
    category_id: null,
    requires_services: [],
    ...overrides,
  };
}

function installation(overrides: Partial<Installation> = {}): Installation {
  return {
    installation_id: "i1",
    plugin_id: "p1",
    version: "1.0.0",
    status: "active",
    enabled: true,
    installed_at: "2026-01-01T00:00:00Z",
    last_updated_at: "2026-01-01T00:00:00Z",
    name: "weather",
    display_name: "Weather",
    description: null,
    current_version: "1.0.0",
    pricing_model: "free",
    base_tier: "community",
    category_id: null,
    author: "Minder",
    ...overrides,
  };
}

function renderCard(overrides: {
  installation?: Installation;
  isAuthenticated?: boolean;
  confirm?: ReturnType<typeof vi.fn>;
  onInstalled?: ReturnType<typeof vi.fn>;
  onUninstalled?: ReturnType<typeof vi.fn>;
  onToggleEnabled?: ReturnType<typeof vi.fn>;
} = {}) {
  const confirm = overrides.confirm ?? vi.fn().mockResolvedValue(true);
  const onInstalled = overrides.onInstalled ?? vi.fn();
  const onUninstalled = overrides.onUninstalled ?? vi.fn();
  const onToggleEnabled = overrides.onToggleEnabled ?? vi.fn();
  render(
    <PluginCard
      plugin={plugin()}
      installation={overrides.installation}
      token="tok"
      isAuthenticated={overrides.isAuthenticated ?? true}
      onInstalled={onInstalled}
      onUninstalled={onUninstalled}
      onToggleEnabled={onToggleEnabled}
      confirm={confirm}
    />,
  );
  return { confirm, onInstalled, onUninstalled, onToggleEnabled };
}

describe("PluginCard", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("installs the plugin and shows the success banner", async () => {
    apiFetch.mockResolvedValue({});
    const { onInstalled } = renderCard({ installation: undefined });

    fireEvent.click(screen.getByRole("button", { name: "Install" }));

    await screen.findByText(/Installed\. If this plugin exposes an AI tool/);
    expect(apiFetch).toHaveBeenCalledWith("/v1/marketplace/plugins/p1/install", {
      method: "POST",
      token: "tok",
    });
    expect(onInstalled).toHaveBeenCalledTimes(1);
  });

  it("shows a friendly error and no success banner when install fails", async () => {
    apiFetch.mockRejectedValue(new Error("Plugin already installed"));
    renderCard({ installation: undefined });

    fireEvent.click(screen.getByRole("button", { name: "Install" }));

    await screen.findByText("Plugin already installed");
    expect(
      screen.queryByText(/Installed\. If this plugin exposes an AI tool/),
    ).toBeNull();
  });

  it("does not uninstall when the confirmation is declined", async () => {
    const { onUninstalled } = renderCard({
      installation: installation(),
      confirm: vi.fn().mockResolvedValue(false),
    });

    fireEvent.click(screen.getByRole("button", { name: "🗑 Uninstall" }));

    await vi.waitFor(() => {}); // let the confirm() promise settle
    expect(apiFetch).not.toHaveBeenCalled();
    expect(onUninstalled).not.toHaveBeenCalled();
  });

  it("uninstalls the plugin once confirmed", async () => {
    apiFetch.mockResolvedValue({});
    const { onUninstalled } = renderCard({ installation: installation() });

    fireEvent.click(screen.getByRole("button", { name: "🗑 Uninstall" }));

    await vi.waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/v1/marketplace/plugins/p1/uninstall",
        { method: "DELETE", token: "tok" },
      ),
    );
    expect(onUninstalled).toHaveBeenCalledWith("p1");
  });

  it("disables an enabled plugin via the enable/disable toggle", async () => {
    apiFetch.mockResolvedValue({});
    const { onToggleEnabled } = renderCard({
      installation: installation({ enabled: true }),
    });

    fireEvent.click(screen.getByRole("button", { name: "Disable" }));

    await vi.waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/v1/marketplace/plugins/p1/disable",
        { method: "POST", token: "tok" },
      ),
    );
    expect(onToggleEnabled).toHaveBeenCalledWith("p1", false);
  });

  it("enables a disabled plugin via the enable/disable toggle", async () => {
    apiFetch.mockResolvedValue({});
    const { onToggleEnabled } = renderCard({
      installation: installation({ enabled: false }),
    });

    fireEvent.click(screen.getByRole("button", { name: "Enable" }));

    await vi.waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/v1/marketplace/plugins/p1/enable",
        { method: "POST", token: "tok" },
      ),
    );
    expect(onToggleEnabled).toHaveBeenCalledWith("p1", true);
  });

  it("disables the Install button and shows a login hint when logged out", () => {
    renderCard({ installation: undefined, isAuthenticated: false });

    expect(
      screen.getByRole("button", { name: "Install" }).hasAttribute("disabled"),
    ).toBe(true);
    expect(screen.getByText("Log in to install")).toBeTruthy();
  });
});
