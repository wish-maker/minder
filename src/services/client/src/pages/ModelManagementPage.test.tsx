import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ModelCard,
  ModelManagementPage,
  PullModelForm,
  type ModelInfo,
} from "./ModelManagementPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

let mockAuth = { token: "", role: "" };
vi.mock("../lib/auth", () => ({
  useAuth: () => mockAuth,
}));
vi.mock("../components/ConfirmDialog", () => ({
  useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(true), dialog: null }),
}));

function model(overrides: Partial<ModelInfo> = {}): ModelInfo {
  return {
    id: "llama3.2:latest",
    name: "llama3.2:latest",
    type: "local",
    provider: "ollama",
    size: "1.88 GB",
    status: "ready",
    ...overrides,
  };
}

// ModelDetailPanel (nested inside ModelCard) fetches eagerly on mount with no
// options object -- give every apiFetch call a harmless shape so that eager
// fetch doesn't crash the render, and assert on the specific delete call via
// toHaveBeenCalledWith (which matches if ANY recorded call has those exact
// args, regardless of the other eager-fetch call also having happened).
function baseApiFetchMock() {
  apiFetch.mockResolvedValue({
    id: "llama3.2:latest",
    details: {},
    capabilities: [],
    status: "ready",
  });
}

describe("ModelCard delete", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("does not delete when the confirmation is declined", async () => {
    baseApiFetchMock();
    const onDeleted = vi.fn();
    const confirm = vi.fn().mockResolvedValue(false);
    render(
      <ModelCard
        model={model()}
        token="tok"
        isAdmin
        onDeleted={onDeleted}
        confirm={confirm}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete" }));
    await vi.waitFor(() => expect(confirm).toHaveBeenCalled());

    expect(
      apiFetch.mock.calls.some(([, opts]) => opts?.method === "DELETE"),
    ).toBe(false);
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("deletes the model once confirmed", async () => {
    baseApiFetchMock();
    const onDeleted = vi.fn();
    const confirm = vi.fn().mockResolvedValue(true);
    render(
      <ModelCard
        model={model()}
        token="tok"
        isAdmin
        onDeleted={onDeleted}
        confirm={confirm}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete" }));

    await vi.waitFor(() => expect(onDeleted).toHaveBeenCalledWith("llama3.2:latest"));
    expect(apiFetch).toHaveBeenCalledWith("/v1/models/llama3.2%3Alatest", {
      method: "DELETE",
      token: "tok",
    });
  });

  it("disables Delete with a role hint when not an admin", () => {
    baseApiFetchMock();
    render(
      <ModelCard
        model={model()}
        token="tok"
        isAdmin={false}
        onDeleted={vi.fn()}
        confirm={vi.fn()}
      />,
    );

    const button = screen.getByRole("button", { name: "🗑 Delete" });
    expect(button.hasAttribute("disabled")).toBe(true);
    expect(button.getAttribute("title")).toBe("Admin role required");
  });
});

describe("PullModelForm", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("rejects an empty model id without calling the API", () => {
    render(<PullModelForm token="tok" isAdmin onPulled={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Pull" }));

    expect(screen.getByText("Model id is required.")).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("pulls a model and reports a fresh pull distinctly from already-exists", async () => {
    apiFetch.mockResolvedValue({
      message: "ok",
      model: "llama3.2:latest",
      status: "pulled",
    });
    const onPulled = vi.fn();
    render(<PullModelForm token="tok" isAdmin onPulled={onPulled} />);

    fireEvent.change(screen.getByLabelText("Model id to pull"), {
      target: { value: "llama3.2:latest" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Pull" }));

    await screen.findByText('Pulled "llama3.2:latest".');
    expect(apiFetch).toHaveBeenCalledWith("/v1/models", {
      method: "POST",
      body: { model_id: "llama3.2:latest" },
      token: "tok",
    });
    expect(onPulled).toHaveBeenCalledTimes(1);
  });

  it("reports an already-pulled model with a distinct message", async () => {
    apiFetch.mockResolvedValue({
      message: "ok",
      model: "llama3.2:latest",
      status: "already_exists",
    });
    render(<PullModelForm token="tok" isAdmin onPulled={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Model id to pull"), {
      target: { value: "llama3.2:latest" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Pull" }));

    await screen.findByText('"llama3.2:latest" is already pulled.');
  });

  it("clears the input field after a successful pull", async () => {
    apiFetch.mockResolvedValue({
      message: "ok",
      model: "llama3.2:latest",
      status: "pulled",
    });
    render(<PullModelForm token="tok" isAdmin onPulled={vi.fn()} />);
    const input = screen.getByLabelText(
      "Model id to pull",
    ) as HTMLInputElement;

    fireEvent.change(input, { target: { value: "llama3.2:latest" } });
    fireEvent.click(screen.getByRole("button", { name: "Pull" }));

    await screen.findByText('Pulled "llama3.2:latest".');
    expect(input.value).toBe("");
  });

  it("shows a friendly error and keeps the input on a failed pull", async () => {
    apiFetch.mockRejectedValue(
      new Error("model_id may not specify a custom registry host"),
    );
    render(<PullModelForm token="tok" isAdmin onPulled={vi.fn()} />);
    const input = screen.getByLabelText(
      "Model id to pull",
    ) as HTMLInputElement;

    fireEvent.change(input, { target: { value: "evil.example.com/model" } });
    fireEvent.click(screen.getByRole("button", { name: "Pull" }));

    await screen.findByText("model_id may not specify a custom registry host");
    expect(input.value).toBe("evil.example.com/model");
  });

  it("disables the form with a login/role hint when not an admin", () => {
    render(<PullModelForm token="" isAdmin={false} onPulled={vi.fn()} />);
    expect(
      screen.getByText("Log in as an admin to pull a model."),
    ).toBeTruthy();
  });
});

// Routes apiFetch by path: the list, each ModelCard's eager detail fetch
// (`/v1/models/{id}`), and any other call (pull/delete/test) just resolves
// harmlessly unless a test overrides it via mockImplementationOnce.
function routeApiFetch(items: ModelInfo[]) {
  apiFetch.mockImplementation(async (path: string) => {
    if (path === "/v1/models?limit=500") {
      return { items, total: items.length, limit: 500, offset: 0 };
    }
    if (path.startsWith("/v1/models/") && !path.endsWith("/test")) {
      return { id: path.split("/").pop(), details: {}, capabilities: [], status: "ready" };
    }
    return {};
  });
}

describe("ModelManagementPage", () => {
  afterEach(() => {
    apiFetch.mockReset();
    mockAuth = { token: "", role: "" };
    cleanup();
  });

  it("shows an empty state when no models are pulled", async () => {
    routeApiFetch([]);
    render(<ModelManagementPage />);

    await screen.findByText("No models pulled yet — use the form above.");
  });

  it("renders a ModelCard per pulled model", async () => {
    routeApiFetch([model({ id: "a", name: "a" }), model({ id: "b", name: "b" })]);
    render(<ModelManagementPage />);

    await screen.findByText("a");
    expect(screen.getByText("b")).toBeTruthy();
  });

  it("renders (does not crash) when the response omits `items` entirely", async () => {
    apiFetch.mockResolvedValue({});
    render(<ModelManagementPage />);

    await screen.findByText("No models pulled yet — use the form above.");
  });

  it("filters the visible models by name, provider, or type and shows a match count", async () => {
    routeApiFetch([
      model({ id: "a", name: "llama3.2:latest" }),
      model({ id: "b", name: "mistral:latest", provider: "ollama" }),
    ]);
    render(<ModelManagementPage />);
    await screen.findByText("llama3.2:latest");

    fireEvent.change(screen.getByLabelText("Filter models"), {
      target: { value: "mistral" },
    });

    await screen.findByText("1 of 2");
    expect(screen.queryByText("llama3.2:latest")).toBeNull();
    expect(screen.getByText("mistral:latest")).toBeTruthy();
  });

  it("shows a no-match empty state when the filter matches nothing", async () => {
    routeApiFetch([model()]);
    render(<ModelManagementPage />);
    await screen.findByText("llama3.2:latest");

    fireEvent.change(screen.getByLabelText("Filter models"), {
      target: { value: "does-not-exist" },
    });

    await screen.findByText('No pulled models match "does-not-exist".');
  });

  it("refreshes the list after a successful delete (admin)", async () => {
    mockAuth = { token: "tok", role: "admin" };
    routeApiFetch([model()]);
    render(<ModelManagementPage />);
    await screen.findByText("llama3.2:latest");

    apiFetch.mockResolvedValueOnce({}); // the DELETE call itself
    routeApiFetch([]); // reload() re-fetches an now-empty list
    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete" }));

    await screen.findByText("No models pulled yet — use the form above.");
  });

  it("shows a friendly status message when the models fetch fails", async () => {
    apiFetch.mockRejectedValue(new Error("model-management unreachable"));
    render(<ModelManagementPage />);

    await screen.findByText("model-management unreachable");
  });
});
