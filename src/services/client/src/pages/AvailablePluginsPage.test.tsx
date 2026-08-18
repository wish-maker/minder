import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AvailablePluginsPage,
  PluginCard,
  type Installation,
  type Plugin,
} from "./AvailablePluginsPage";

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

// Mutable per test (like GraphExplorerPage.test.tsx's behavior vars) so both
// the logged-out and logged-in/authenticated paths can be exercised.
let mockAuth = { token: "", isAuthenticated: false };
vi.mock("../lib/auth", () => ({
  useAuth: () => mockAuth,
}));
vi.mock("../components/ConfirmDialog", () => ({
  useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(true), dialog: null }),
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

// Routes apiFetch by the real path shapes AvailablePluginsPage's three
// concurrent loaders hit (featured / catalog+search / my installations),
// mirroring AvailableToolsPage.test.tsx's approach for the same page shape.
function routeApiFetch(handlers: {
  featured?: Plugin[];
  catalog?: (offset: number) => { items: Plugin[]; total: number };
  installations?: Installation[];
}) {
  apiFetch.mockImplementation(async (path: string) => {
    if (path.startsWith("/v1/marketplace/plugins/featured")) {
      const items = handlers.featured ?? [];
      return { plugins: items, count: items.length, total: items.length, limit: 6, offset: 0 };
    }
    if (path.startsWith("/v1/marketplace/installations/me")) {
      const installations = handlers.installations ?? [];
      return { installations, count: installations.length };
    }
    if (path.startsWith("/v1/graph/recommendations")) {
      return { recommendations: [] };
    }
    const offset = Number(new URL(path, "http://x").searchParams.get("offset") ?? 0);
    const page = handlers.catalog ? handlers.catalog(offset) : { items: [], total: 0 };
    return { plugins: page.items, count: page.items.length, total: page.total, limit: 20, offset };
  });
}

describe("AvailablePluginsPage", () => {
  afterEach(() => {
    apiFetch.mockReset();
    mockAuth = { token: "", isAuthenticated: false };
    cleanup();
  });

  it("renders the catalog and excludes plugins already shown in Featured", async () => {
    routeApiFetch({
      featured: [plugin({ id: "p1", display_name: "Weather" })],
      catalog: () => ({
        items: [
          plugin({ id: "p1", display_name: "Weather" }),
          plugin({ id: "p2", display_name: "Translate", name: "translate" }),
        ],
        total: 2,
      }),
    });
    render(<AvailablePluginsPage />);

    await screen.findByText("Translate");
    // p1 is Featured, so its catalog-list card should NOT also render below.
    expect(screen.getAllByText("Weather")).toHaveLength(1);
  });

  it("keeps a Featured plugin visible in search results (a query browses the whole catalog)", async () => {
    mockAuth = { token: "", isAuthenticated: false };
    routeApiFetch({
      featured: [plugin({ id: "p1", display_name: "Weather" })],
      catalog: () => ({ items: [plugin({ id: "p1", display_name: "Weather" })], total: 1 }),
    });
    render(<AvailablePluginsPage />);
    // Before searching: Featured section renders it, catalog excludes the
    // duplicate -- so it's only under the "Featured" heading.
    await screen.findByText("Featured", { exact: false });
    expect(screen.getAllByText("Weather")).toHaveLength(1);

    fireEvent.change(screen.getByLabelText("Search plugins"), {
      target: { value: "weather" },
    });

    // Debounced 300ms -- once the post-debounce refetch lands, the Featured
    // section unmounts (query.trim() is now truthy) while the *catalog*
    // render still shows the plugin -- proving the exclusion filter was
    // skipped for this query, not just that Featured disappeared.
    await vi.waitFor(
      () => expect(screen.queryByText("Featured", { exact: false })).toBeNull(),
      { timeout: 1000 },
    );
    expect(screen.getByText("Weather")).toBeTruthy();
  });

  it("shows a Load more button when more results exist, and fetches the next page", async () => {
    routeApiFetch({
      catalog: (offset) =>
        offset === 0
          ? { items: [plugin({ id: "p1", display_name: "Weather" })], total: 2 }
          : { items: [plugin({ id: "p2", display_name: "Translate", name: "translate" })], total: 2 },
    });
    render(<AvailablePluginsPage />);
    await screen.findByText("Weather");

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));

    await screen.findByText("Translate");
    expect(apiFetch).toHaveBeenLastCalledWith("/v1/marketplace/plugins?limit=20&offset=20");
  });

  it("does not show Load more once every result has loaded", async () => {
    routeApiFetch({ catalog: () => ({ items: [plugin()], total: 1 }) });
    render(<AvailablePluginsPage />);

    await screen.findByText("Weather");
    expect(screen.queryByText("Load more")).toBeNull();
  });

  it("shows an empty state when the catalog has no plugins at all", async () => {
    routeApiFetch({ catalog: () => ({ items: [], total: 0 }) });
    render(<AvailablePluginsPage />);

    await screen.findByText("No plugins in the catalog yet.");
  });

  it("shows a search-specific empty state when a query matches nothing", async () => {
    routeApiFetch({ catalog: () => ({ items: [], total: 0 }) });
    render(<AvailablePluginsPage />);
    await screen.findByText("No plugins in the catalog yet.");

    fireEvent.change(screen.getByLabelText("Search plugins"), {
      target: { value: "nope" },
    });

    await screen.findByText("No plugins match your search.");
  });

  it("flips an installed plugin's enabled state via the real page-level handler", async () => {
    mockAuth = { token: "tok", isAuthenticated: true };
    routeApiFetch({
      catalog: () => ({ items: [plugin({ id: "p1", display_name: "Weather" })], total: 1 }),
      installations: [installation({ plugin_id: "p1", enabled: true })],
    });
    render(<AvailablePluginsPage />);
    await screen.findByText("✓ enabled");

    fireEvent.click(screen.getByRole("button", { name: "Disable" }));

    await screen.findByText("disabled");
    expect(screen.getByRole("button", { name: "Enable" })).toBeTruthy();
  });

  it("shows recommendations and an installed count once logged in with installs", async () => {
    mockAuth = { token: "tok", isAuthenticated: true };
    routeApiFetch({
      catalog: () => ({ items: [], total: 0 }),
      installations: [installation({ plugin_id: "p1" })],
    });
    apiFetch.mockImplementation(async (path: string, opts?: { method?: string }) => {
      if (path === "/v1/graph/recommendations?limit=5" && opts?.method === "POST") {
        return { recommendations: [{ plugin_id: "p9", name: "News", score: 0.9 }] };
      }
      if (path.startsWith("/v1/marketplace/installations/me")) {
        return { installations: [installation({ plugin_id: "p1" })], count: 1 };
      }
      if (path.startsWith("/v1/marketplace/plugins/featured")) {
        return { plugins: [], count: 0, total: 0, limit: 6, offset: 0 };
      }
      return { plugins: [], count: 0, total: 0, limit: 20, offset: 0 };
    });
    render(<AvailablePluginsPage />);

    await screen.findByText(/You have 1 plugin installed/);
    expect(screen.getByText(/Recommended based on what you've installed:/)).toBeTruthy();
    expect(screen.getByText(/News/)).toBeTruthy();
  });

  it("renders (does not crash) when the recommendations response omits `recommendations`", async () => {
    mockAuth = { token: "tok", isAuthenticated: true };
    apiFetch.mockImplementation(async (path: string, opts?: { method?: string }) => {
      if (path === "/v1/graph/recommendations?limit=5" && opts?.method === "POST") {
        return {}; // malformed/omitted-key response
      }
      if (path.startsWith("/v1/marketplace/installations/me")) {
        return { installations: [installation({ plugin_id: "p1" })], count: 1 };
      }
      return { plugins: [], count: 0, total: 0, limit: 20, offset: 0 };
    });

    render(<AvailablePluginsPage />);

    await screen.findByText(/You have 1 plugin installed/);
    expect(screen.queryByText(/Recommended based on/)).toBeNull();
  });
});
