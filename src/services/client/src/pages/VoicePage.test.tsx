import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TextToSpeechCard } from "./VoicePage";

const apiFetch = vi.fn();
const apiFetchBlob = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  apiFetchBlob: (...args: unknown[]) => apiFetchBlob(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

interface RouterOverrides {
  models?: unknown;
  chatCompletion?: () => Promise<unknown>;
}

/** TextToSpeechCard fires 3 concurrent fetches on mount (tts/languages,
 * stt/languages, models) plus a 4th (voices) once the default language is
 * known. Routes each by URL so every test doesn't have to hand-roll all 4 --
 * only the pieces a given test cares about (models / chat completion) are
 * overridable. */
function routeApiFetch(overrides: RouterOverrides = {}) {
  apiFetch.mockImplementation((url: string) => {
    if (url.startsWith("/v1/tts/languages")) {
      return Promise.resolve({
        languages: { tr: "Turkish", en: "English" },
        default: "tr",
        available: true,
      });
    }
    if (url.startsWith("/v1/stt/languages")) {
      return Promise.resolve({ languages: {}, default: "", available: true });
    }
    if (url.startsWith("/v1/models")) {
      return Promise.resolve(
        overrides.models ?? {
          items: [{ id: "llama3.2:latest", status: "ready" }],
          total: 1,
          limit: 500,
          offset: 0,
        },
      );
    }
    if (url.startsWith("/v1/tts/voices")) {
      return Promise.resolve({ language: "tr", voices: [] });
    }
    if (url.startsWith("/v1/ai/chat/completions")) {
      return (
        overrides.chatCompletion?.() ??
        Promise.reject(new Error(`no chatCompletion mock configured`))
      );
    }
    return Promise.reject(new Error(`unexpected apiFetch call: ${url}`));
  });
}

async function selectRegionalStyle() {
  fireEvent.change(await screen.findByLabelText("Regional style (experimental)"), {
    target: { value: "karadeniz" },
  });
}

describe("TextToSpeechCard rewrite", () => {
  afterEach(() => {
    apiFetch.mockReset();
    apiFetchBlob.mockReset();
    cleanup();
  });

  it("rewrites the text and shows Undo, using the correct model/messages", async () => {
    routeApiFetch({
      chatCompletion: () =>
        Promise.resolve({ message: { content: "Naber ahbap?" } }),
    });
    render(<TextToSpeechCard token="tok" seed={null} />);

    fireEvent.change(await screen.findByLabelText("Text"), {
      target: { value: "Merhaba, nasılsın?" },
    });
    await selectRegionalStyle();
    fireEvent.click(
      screen.getByRole("button", { name: "🪄 Rewrite text in this style" }),
    );

    const textarea = (await screen.findByLabelText(
      "Text",
    )) as HTMLTextAreaElement;
    await vi.waitFor(() => expect(textarea.value).toBe("Naber ahbap?"));
    expect(screen.getByRole("button", { name: "↺ Undo rewrite" })).toBeTruthy();

    const call = apiFetch.mock.calls.find((args: unknown[]) =>
      (args[0] as string).startsWith("/v1/ai/chat/completions"),
    )!;
    const opts = call[1] as {
      body: { model: string; messages: { role: string; content: string }[] };
    };
    expect(opts.body.model).toBe("llama3.2:latest");
    expect(opts.body.messages[1]).toEqual({
      role: "user",
      content: "Merhaba, nasılsın?",
    });
  });

  it("restores the original text via Undo", async () => {
    routeApiFetch({
      chatCompletion: () =>
        Promise.resolve({ message: { content: "Naber ahbap?" } }),
    });
    render(<TextToSpeechCard token="tok" seed={null} />);

    fireEvent.change(await screen.findByLabelText("Text"), {
      target: { value: "Merhaba, nasılsın?" },
    });
    await selectRegionalStyle();
    fireEvent.click(
      screen.getByRole("button", { name: "🪄 Rewrite text in this style" }),
    );
    const textarea = (await screen.findByLabelText(
      "Text",
    )) as HTMLTextAreaElement;
    await vi.waitFor(() => expect(textarea.value).toBe("Naber ahbap?"));

    fireEvent.click(screen.getByRole("button", { name: "↺ Undo rewrite" }));

    expect(textarea.value).toBe("Merhaba, nasılsın?");
    expect(screen.queryByRole("button", { name: "↺ Undo rewrite" })).toBeNull();
  });

  it("re-enables the Rewrite button after a failure (#597: no stuck 'Rewriting…')", async () => {
    routeApiFetch({
      chatCompletion: () => Promise.reject(new Error("Ollama unreachable")),
    });
    render(<TextToSpeechCard token="tok" seed={null} />);

    fireEvent.change(await screen.findByLabelText("Text"), {
      target: { value: "Merhaba, nasılsın?" },
    });
    await selectRegionalStyle();
    fireEvent.click(
      screen.getByRole("button", { name: "🪄 Rewrite text in this style" }),
    );

    await screen.findByText("Ollama unreachable");
    const button = screen.getByRole("button", {
      name: "🪄 Rewrite text in this style",
    });
    expect(button.hasAttribute("disabled")).toBe(false);
  });

  it("shows a specific message and leaves text untouched when the model returns nothing", async () => {
    routeApiFetch({ chatCompletion: () => Promise.resolve({ message: {} }) });
    render(<TextToSpeechCard token="tok" seed={null} />);

    fireEvent.change(await screen.findByLabelText("Text"), {
      target: { value: "Merhaba, nasılsın?" },
    });
    await selectRegionalStyle();
    fireEvent.click(
      screen.getByRole("button", { name: "🪄 Rewrite text in this style" }),
    );

    await screen.findByText("The model returned an empty rewrite.");
    const textarea = screen.getByLabelText("Text") as HTMLTextAreaElement;
    expect(textarea.value).toBe("Merhaba, nasılsın?");
    expect(screen.queryByRole("button", { name: "↺ Undo rewrite" })).toBeNull();
  });

  it("tells the user to pull a model when none is ready, and disables Rewrite", async () => {
    routeApiFetch({
      models: { items: [], total: 0, limit: 500, offset: 0 },
    });
    render(<TextToSpeechCard token="tok" seed={null} />);

    fireEvent.change(await screen.findByLabelText("Text"), {
      target: { value: "Merhaba, nasılsın?" },
    });
    await selectRegionalStyle();

    // No ready models -> the "Rewrite model" picker never renders at all
    // (usableRewriteModels(...).length > 0 gates it), and the button is
    // disabled since rewriteModel stays "".
    expect(screen.queryByLabelText("Rewrite model")).toBeNull();
    expect(
      screen
        .getByRole("button", { name: "🪄 Rewrite text in this style" })
        .hasAttribute("disabled"),
    ).toBe(true);
  });
});
