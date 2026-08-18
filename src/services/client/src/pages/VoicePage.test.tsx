import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TextToSpeechCard, VoicePage } from "./VoicePage";

const apiFetch = vi.fn();
const apiFetchBlob = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  apiFetchBlob: (...args: unknown[]) => apiFetchBlob(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));
const useAuthMock = vi.fn(() => ({ token: "test-token" }));
vi.mock("../lib/auth", () => ({
  useAuth: () => useAuthMock(),
}));

// jsdom doesn't implement Blob object URLs at all.
URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

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

describe("TextToSpeechCard speak/verify", () => {
  afterEach(() => {
    apiFetch.mockReset();
    apiFetchBlob.mockReset();
    cleanup();
  });

  function mockBlobResponse(overrides: Record<string, string> = {}) {
    const headers = new Headers({ "X-Language": "tr", "X-Duration": "2.4", ...overrides });
    apiFetchBlob.mockResolvedValue({ blob: new Blob(["fake-audio"]), headers });
  }

  it("shows a validation message and never calls the API when text is empty", async () => {
    routeApiFetch();
    render(<TextToSpeechCard token="tok" seed={null} />);

    fireEvent.click(await screen.findByRole("button", { name: "▶ Speak" }));

    await screen.findByText("Text is required.");
    expect(apiFetchBlob).not.toHaveBeenCalled();
  });

  it("synthesizes speech and shows the audio player with language/duration and a download link", async () => {
    routeApiFetch();
    mockBlobResponse();
    render(<TextToSpeechCard token="tok" seed={null} />);

    fireEvent.change(await screen.findByLabelText("Text"), {
      target: { value: "Merhaba" },
    });
    fireEvent.click(screen.getByRole("button", { name: "▶ Speak" }));

    await screen.findByText("tr");
    expect(screen.getByText("~2s")).toBeTruthy();
    const download = screen.getByText("⬇ Download") as HTMLAnchorElement;
    expect(download.getAttribute("href")).toBe("blob:mock-url");
    expect(apiFetchBlob).toHaveBeenCalledWith(
      "/v1/tts",
      expect.objectContaining({
        method: "POST",
        body: { text: "Merhaba", language: "tr", slow: false, voice: undefined },
        token: "tok",
      }),
    );
  });

  it("shows a friendly error when synthesis fails", async () => {
    routeApiFetch();
    apiFetchBlob.mockRejectedValue(new Error("TTS engine unavailable"));
    render(<TextToSpeechCard token="tok" seed={null} />);

    fireEvent.change(await screen.findByLabelText("Text"), {
      target: { value: "Merhaba" },
    });
    fireEvent.click(screen.getByRole("button", { name: "▶ Speak" }));

    await screen.findByText("TTS engine unavailable");
  });

  it("verifies the synthesized clip by transcribing it back, showing confidence", async () => {
    routeApiFetch();
    mockBlobResponse();
    apiFetch.mockImplementation((url: string) => {
      if (url.startsWith("/v1/tts/languages")) {
        return Promise.resolve({
          languages: { tr: "Turkish" },
          default: "tr",
          available: true,
        });
      }
      if (url.startsWith("/v1/stt/languages")) {
        return Promise.resolve({ languages: { "tr-TR": "Turkish" }, default: "tr-TR", available: true });
      }
      if (url.startsWith("/v1/models")) {
        return Promise.resolve({ items: [], total: 0, limit: 500, offset: 0 });
      }
      if (url.startsWith("/v1/tts/voices")) {
        return Promise.resolve({ language: "tr", voices: [] });
      }
      if (url.startsWith("/v1/stt")) {
        return Promise.resolve({ text: "merhaba", language: "tr-TR", confidence: 0.87 });
      }
      return Promise.reject(new Error(`unexpected apiFetch call: ${url}`));
    });
    render(<TextToSpeechCard token="tok" seed={null} />);

    fireEvent.change(await screen.findByLabelText("Text"), {
      target: { value: "Merhaba" },
    });
    fireEvent.click(screen.getByRole("button", { name: "▶ Speak" }));
    await screen.findByText("⬇ Download");

    fireEvent.click(screen.getByRole("button", { name: "🎙 Verify by transcribing" }));

    await screen.findByText("Transcribed back as:");
    expect(screen.getByText("“merhaba”")).toBeTruthy();
    expect(screen.getByText("87% confidence")).toBeTruthy();
  });

  it("shows a friendly error when the verify-by-transcribing request fails", async () => {
    routeApiFetch();
    mockBlobResponse();
    apiFetch.mockImplementation((url: string) => {
      if (url.startsWith("/v1/tts/languages")) {
        return Promise.resolve({
          languages: { tr: "Turkish" },
          default: "tr",
          available: true,
        });
      }
      if (url.startsWith("/v1/stt/languages")) {
        return Promise.resolve({ languages: { "tr-TR": "Turkish" }, default: "tr-TR", available: true });
      }
      if (url.startsWith("/v1/models")) {
        return Promise.resolve({ items: [], total: 0, limit: 500, offset: 0 });
      }
      if (url.startsWith("/v1/tts/voices")) {
        return Promise.resolve({ language: "tr", voices: [] });
      }
      if (url.startsWith("/v1/stt")) {
        return Promise.reject(new Error("STT backend down"));
      }
      return Promise.reject(new Error(`unexpected apiFetch call: ${url}`));
    });
    render(<TextToSpeechCard token="tok" seed={null} />);

    fireEvent.change(await screen.findByLabelText("Text"), {
      target: { value: "Merhaba" },
    });
    fireEvent.click(screen.getByRole("button", { name: "▶ Speak" }));
    await screen.findByText("⬇ Download");

    fireEvent.click(screen.getByRole("button", { name: "🎙 Verify by transcribing" }));

    await screen.findByText("STT backend down");
  });

  it("shows a log-in hint instead of disabling silently when logged out", async () => {
    routeApiFetch();
    render(<TextToSpeechCard token="" seed={null} />);

    await screen.findByText("Log in to synthesize speech.");
  });

  it("clicking an example fills the text field", async () => {
    routeApiFetch();
    render(<TextToSpeechCard token="tok" seed={null} />);

    fireEvent.click(await screen.findByRole("button", { name: "Turkish greeting" }));

    expect((screen.getByLabelText("Text") as HTMLTextAreaElement).value).toBe(
      "Merhaba, bugün nasılsın?",
    );
  });

  it("shows a Voice picker only when the language has more than one bundled voice", async () => {
    apiFetch.mockImplementation((url: string) => {
      if (url.startsWith("/v1/tts/languages")) {
        return Promise.resolve({
          languages: { en: "English" },
          default: "en",
          available: true,
        });
      }
      if (url.startsWith("/v1/stt/languages")) {
        return Promise.resolve({ languages: {}, default: "", available: true });
      }
      if (url.startsWith("/v1/models")) {
        return Promise.resolve({ items: [], total: 0, limit: 500, offset: 0 });
      }
      if (url.startsWith("/v1/tts/voices")) {
        return Promise.resolve({
          language: "en",
          voices: [
            { id: "en-male", label: "Male" },
            { id: "en-female", label: "Female" },
          ],
        });
      }
      return Promise.reject(new Error(`unexpected apiFetch call: ${url}`));
    });
    render(<TextToSpeechCard token="tok" seed={null} />);

    const voiceSelect = (await screen.findByLabelText("Voice")) as HTMLSelectElement;
    expect(Array.from(voiceSelect.options).map((o) => o.textContent)).toEqual([
      "Male",
      "Female",
    ]);
  });
});

describe("SpeechToTextCard", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
    vi.unstubAllGlobals();
  });

  function routeVoicePageApiFetch() {
    apiFetch.mockImplementation((url: string) => {
      if (url.startsWith("/v1/tts/languages")) {
        return Promise.resolve({
          languages: { tr: "Turkish" },
          default: "tr",
          available: true,
        });
      }
      if (url.startsWith("/v1/stt/languages")) {
        return Promise.resolve({ languages: { "tr-TR": "Turkish" }, default: "tr-TR", available: true });
      }
      if (url.startsWith("/v1/models")) {
        return Promise.resolve({ items: [], total: 0, limit: 500, offset: 0 });
      }
      if (url.startsWith("/v1/tts/voices")) {
        return Promise.resolve({ language: "tr", voices: [] });
      }
      return Promise.reject(new Error(`unexpected apiFetch call: ${url}`));
    });
  }

  it("transcribes an uploaded file and shows the result with confidence", async () => {
    routeVoicePageApiFetch();
    apiFetch.mockImplementation((url: string, opts?: { body?: unknown }) => {
      if (url === "/v1/stt/languages") {
        return Promise.resolve({ languages: { "tr-TR": "Turkish" }, default: "tr-TR", available: true });
      }
      if (url === "/v1/stt") {
        return Promise.resolve({ text: "test transcript", language: "tr-TR", confidence: 0.5 });
      }
      return Promise.reject(new Error(`unexpected: ${url} ${JSON.stringify(opts)}`));
    });
    render(<VoicePage />);

    const file = new File(["clip"], "clip.webm", { type: "audio/webm" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await screen.findByText("test transcript");
    expect(screen.getByText("50% confidence")).toBeTruthy();
    expect(screen.getByRole("button", { name: "🔊 Speak this back" })).toBeTruthy();
  });

  it("shows '(no speech detected)' when the transcript is empty, with no speak-back button", async () => {
    apiFetch.mockImplementation((url: string) => {
      if (url === "/v1/stt/languages") {
        return Promise.resolve({ languages: { "tr-TR": "Turkish" }, default: "tr-TR", available: true });
      }
      if (url === "/v1/stt") {
        return Promise.resolve({ text: "", language: "tr-TR", confidence: 0 });
      }
      return Promise.reject(new Error(`unexpected: ${url}`));
    });
    render(<VoicePage />);

    const file = new File(["clip"], "clip.webm", { type: "audio/webm" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await screen.findByText("(no speech detected)");
    expect(screen.queryByRole("button", { name: "🔊 Speak this back" })).toBeNull();
  });

  it("shows a friendly error when transcription fails", async () => {
    apiFetch.mockImplementation((url: string) => {
      if (url === "/v1/stt/languages") {
        return Promise.resolve({ languages: { "tr-TR": "Turkish" }, default: "tr-TR", available: true });
      }
      if (url === "/v1/stt") {
        return Promise.reject(new Error("STT engine crashed"));
      }
      return Promise.reject(new Error(`unexpected: ${url}`));
    });
    render(<VoicePage />);

    const file = new File(["clip"], "clip.webm", { type: "audio/webm" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await screen.findByText("STT engine crashed");
  });

  it("records via the microphone, then stops and transcribes on Stop", async () => {
    apiFetch.mockImplementation((url: string) => {
      if (url === "/v1/stt/languages") {
        return Promise.resolve({ languages: { "tr-TR": "Turkish" }, default: "tr-TR", available: true });
      }
      if (url === "/v1/stt") {
        return Promise.resolve({ text: "recorded speech", language: "tr-TR", confidence: 0.9 });
      }
      return Promise.reject(new Error(`unexpected: ${url}`));
    });

    const fakeTrack = { stop: vi.fn() };
    const fakeStream = { getTracks: () => [fakeTrack] };
    const getUserMedia = vi.fn().mockResolvedValue(fakeStream);
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });

    class FakeMediaRecorder {
      ondataavailable: ((e: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      state = "recording";
      constructor(public stream: unknown) {}
      start() {}
      stop() {
        this.ondataavailable?.({ data: new Blob(["chunk"]) });
        this.onstop?.();
      }
    }
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);

    render(<VoicePage />);

    fireEvent.click(screen.getByRole("button", { name: "🔴 Record" }));
    await screen.findByText(/Stop & transcribe/);

    fireEvent.click(screen.getByRole("button", { name: /Stop & transcribe/ }));

    await screen.findByText("recorded speech");
    expect(fakeTrack.stop).toHaveBeenCalled();
  });

  it("shows a friendly error when microphone access is denied", async () => {
    routeVoicePageApiFetch();
    const getUserMedia = vi.fn().mockRejectedValue(new Error("Permission denied"));
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    render(<VoicePage />);

    fireEvent.click(screen.getByRole("button", { name: "🔴 Record" }));

    await screen.findByText("Microphone access failed: Permission denied");
  });

  it("shows a generic message when microphone access fails with a non-Error value", async () => {
    routeVoicePageApiFetch();
    const getUserMedia = vi.fn().mockRejectedValue("denied");
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    render(<VoicePage />);

    fireEvent.click(screen.getByRole("button", { name: "🔴 Record" }));

    await screen.findByText("Microphone access failed.");
  });

  it("releases the microphone and stops an in-progress recorder on unmount", async () => {
    routeVoicePageApiFetch();
    const fakeTrack = { stop: vi.fn() };
    const fakeStream = { getTracks: () => [fakeTrack] };
    const getUserMedia = vi.fn().mockResolvedValue(fakeStream);
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });

    class FakeMediaRecorder {
      ondataavailable: ((e: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      state = "recording";
      stop = vi.fn(() => {
        throw new Error("already stopping"); // exercise the cleanup's own try/catch
      });
      start() {}
    }
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);

    const { unmount } = render(<VoicePage />);
    fireEvent.click(screen.getByRole("button", { name: "🔴 Record" }));
    await screen.findByText(/Stop & transcribe/);

    expect(() => unmount()).not.toThrow();
    expect(fakeTrack.stop).toHaveBeenCalled();
  });

  it("shows a log-in hint instead of the upload control's action when logged out", async () => {
    useAuthMock.mockReturnValueOnce({ token: "" });
    routeVoicePageApiFetch();
    render(<VoicePage />);

    await screen.findByText("Log in to transcribe audio.");
  });
});

describe("VoicePage", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("renders both the Text to Speech and Speech to Text cards", async () => {
    routeApiFetch();
    render(<VoicePage />);

    await screen.findByText("Text to Speech");
    expect(screen.getByText("Speech to Text")).toBeTruthy();
  });

  it("wires 'Speak this back' from STT into the TTS card's text field", async () => {
    apiFetch.mockImplementation((url: string) => {
      if (url.startsWith("/v1/tts/languages")) {
        return Promise.resolve({
          languages: { tr: "Turkish" },
          default: "tr",
          available: true,
        });
      }
      if (url.startsWith("/v1/stt/languages")) {
        return Promise.resolve({ languages: { "tr-TR": "Turkish" }, default: "tr-TR", available: true });
      }
      if (url.startsWith("/v1/models")) {
        return Promise.resolve({ items: [], total: 0, limit: 500, offset: 0 });
      }
      if (url.startsWith("/v1/tts/voices")) {
        return Promise.resolve({ language: "tr", voices: [] });
      }
      if (url === "/v1/stt") {
        return Promise.resolve({ text: "geri konuş", language: "tr-TR", confidence: 0.7 });
      }
      return Promise.reject(new Error(`unexpected apiFetch call: ${url}`));
    });
    render(<VoicePage />);

    const file = new File(["clip"], "clip.webm", { type: "audio/webm" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    fireEvent.click(await screen.findByRole("button", { name: "🔊 Speak this back" }));

    const textarea = (await screen.findByLabelText("Text")) as HTMLTextAreaElement;
    expect(textarea.value).toBe("geri konuş");
  });
});
