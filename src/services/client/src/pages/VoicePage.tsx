import { useEffect, useId, useRef, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { apiFetch, apiFetchBlob, friendlyErrorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { badgeClass, cardClass, confidenceBadgeColor, inputClass, primaryButtonClass, secondaryButtonClass } from "../lib/ui";
import { formatElapsed, useElapsedSeconds } from "../lib/useElapsedSeconds";

interface LanguagesResponse {
  languages: Record<string, string>;
  default: string;
  available: boolean;
  auto_detect?: boolean;
}

interface SttResponse {
  text: string;
  language: string;
  confidence: number;
}

/** Bumped on every "speak this back" click, even for identical text -- a
 * plain string dependency wouldn't re-fire the effect that seeds the TTS
 * card's textarea if the same transcript is sent back twice in a row. */
interface Seed {
  text: string;
  nonce: number;
}

const TTS_EXAMPLES: { label: string; text: string }[] = [
  { label: "Turkish greeting", text: "Merhaba, bugün nasılsın?" },
  { label: "English pangram", text: "The quick brown fox jumps over the lazy dog." },
  { label: "Numbers", text: "One, two, three, four, five." },
];

/** STT language codes are BCP-47 ("tr-TR"); TTS's are bare ("tr") -- #449 --
 * so "verify by transcribing" a just-synthesized clip has to bridge the two
 * lists itself. Matches on the BCP-47 code's language prefix; returns null
 * (not a guess) when no STT locale covers this TTS language, so the caller
 * can disable the action instead of silently transcribing in the wrong
 * language. */
function matchingSttLanguage(
  ttsCode: string,
  sttLanguages: Record<string, string>,
): string | null {
  const match = Object.keys(sttLanguages).find(
    (code) => code.split("-")[0] === ttsCode,
  );
  return match ?? null;
}

function TextToSpeechCard({
  token,
  seed,
}: {
  token: string;
  seed: Seed | null;
}) {
  const textId = useId();
  const languageId = useId();
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const [sttLanguages, setSttLanguages] = useState<Record<string, string>>({});
  const [text, setText] = useState("");
  const [language, setLanguage] = useState("tr");
  const [slow, setSlow] = useState(false);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ language: string; duration: string } | null>(null);
  const [verifyResult, setVerifyResult] = useState<SttResponse | null>(null);
  const [verifyBusy, setVerifyBusy] = useState(false);
  const objectUrlRef = useRef<string | null>(null);
  const lastBlobRef = useRef<Blob | null>(null);

  useEffect(() => {
    apiFetch<LanguagesResponse>("/v1/tts/languages")
      .then((res) => {
        setLanguages(res.languages);
        setLanguage(res.default);
      })
      .catch(() => setStatus("Could not load supported languages."));
    // Only used to pick a matching locale for "verify by transcribing" --
    // never shown as a selector, so a load failure here is silent (the
    // verify button just stays disabled via matchingSttLanguage's null).
    apiFetch<LanguagesResponse>("/v1/stt/languages")
      .then((res) => setSttLanguages(res.languages))
      .catch(() => {});
  }, []);

  useEffect(() => {
    // Revoke the previous object URL whenever it's replaced/unmounted --
    // otherwise every synthesis leaks a blob URL for the session's lifetime.
    return () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    };
  }, []);

  useEffect(() => {
    if (seed) setText(seed.text);
  }, [seed]);

  async function handleSpeak() {
    if (!text.trim()) {
      setStatus("Text is required.");
      return;
    }
    setBusy(true);
    setStatus("Synthesizing…");
    setAudioUrl(null);
    setVerifyResult(null);
    try {
      const { blob, headers } = await apiFetchBlob("/v1/tts", {
        method: "POST",
        body: { text, language, slow },
        token,
      });
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      lastBlobRef.current = blob;
      setAudioUrl(url);
      setMeta({
        language: headers.get("X-Language") ?? language,
        duration: headers.get("X-Duration") ?? "",
      });
      setStatus("");
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  const verifyLanguage = matchingSttLanguage(language, sttLanguages);

  async function handleVerify() {
    if (!lastBlobRef.current || !verifyLanguage) return;
    setVerifyBusy(true);
    setVerifyResult(null);
    try {
      const form = new FormData();
      form.append("file", new File([lastBlobRef.current], "verify-clip"));
      form.append("language", verifyLanguage);
      const res = await apiFetch<SttResponse>("/v1/stt", {
        method: "POST",
        body: form,
        token,
      });
      setVerifyResult(res);
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setVerifyBusy(false);
  }

  return (
    <section className={`mb-6 ${cardClass}`}>
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">🔊</span> Text to Speech
      </h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
        Piper (offline) synthesizes bundled languages as WAV; anything else
        falls back to gTTS (online) as MP3.
      </p>
      <fieldset disabled={!token} className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-1.5">
          {TTS_EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              type="button"
              onClick={() => setText(ex.text)}
              className="rounded-full border border-gray-300 px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-800"
            >
              {ex.label}
            </button>
          ))}
        </div>
        <div>
          <label
            htmlFor={textId}
            className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Text
          </label>
          <textarea
            id={textId}
            className={inputClass}
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type something to hear it spoken, or pick an example above…"
          />
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="max-w-xs flex-1">
            <label
              htmlFor={languageId}
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Language
            </label>
            <select
              id={languageId}
              className={inputClass}
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              {Object.entries(languages).map(([code, name]) => (
                <option key={code} value={code}>
                  {name} ({code})
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 pb-1.5 text-sm text-gray-700 dark:text-gray-300">
            <input
              className="h-4 w-4 rounded border-gray-300 disabled:cursor-not-allowed disabled:opacity-60"
              type="checkbox"
              checked={slow}
              onChange={(e) => setSlow(e.target.checked)}
            />
            Speak slowly
          </label>
        </div>
        <div className="flex items-center gap-3">
          <button type="button" onClick={handleSpeak} disabled={busy} className={primaryButtonClass}>
            {busy ? "Synthesizing…" : "▶ Speak"}
          </button>
          {!token && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Log in to synthesize speech.
            </span>
          )}
          <span className="text-sm text-gray-500 dark:text-gray-400">{status}</span>
        </div>
      </fieldset>
      {audioUrl && (
        <div className="mt-3 flex flex-col gap-2 rounded-lg bg-gray-50 p-3 dark:bg-gray-800">
          <div className="flex flex-wrap items-center gap-2">
            <span className={badgeClass}>{meta?.language ?? language}</span>
            {meta?.duration && (
              <span className={badgeClass}>~{Math.round(parseFloat(meta.duration))}s</span>
            )}
            <a
              href={audioUrl}
              download="speech"
              className="text-sm text-indigo-600 underline hover:text-indigo-700 dark:text-indigo-400"
            >
              ⬇ Download
            </a>
            <button
              type="button"
              onClick={handleVerify}
              disabled={verifyBusy || !verifyLanguage}
              title={
                verifyLanguage
                  ? "Feed this clip straight back into Speech-to-Text to confirm the round trip works"
                  : "No matching Speech-to-Text locale for this language"
              }
              className={`${secondaryButtonClass} ml-auto`}
            >
              {verifyBusy ? "Transcribing…" : "🎙 Verify by transcribing"}
            </button>
          </div>
          <audio controls src={audioUrl} className="w-full" />
          {verifyResult && (
            <p className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-gray-600 dark:text-gray-400">Transcribed back as:</span>
              <span className="italic text-gray-900 dark:text-gray-100">
                “{verifyResult.text || "(no speech detected)"}”
              </span>
              <span className={`${badgeClass} ${confidenceBadgeColor(verifyResult.confidence)}`}>
                {Math.round(verifyResult.confidence * 100)}% confidence
              </span>
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function SpeechToTextCard({
  token,
  onSpeakBack,
}: {
  token: string;
  onSpeakBack: (text: string) => void;
}) {
  const languageId = useId();
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const [language, setLanguage] = useState("tr-TR");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SttResponse | null>(null);
  const [recording, setRecording] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const previewUrlRef = useRef<string | null>(null);
  const elapsed = useElapsedSeconds(recording);

  useEffect(() => {
    apiFetch<LanguagesResponse>("/v1/stt/languages")
      .then((res) => {
        setLanguages(res.languages);
        setLanguage(res.default);
      })
      .catch(() => setStatus("Could not load supported languages."));
  }, []);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  // Release the microphone if the user navigates away mid-recording. Without
  // this, getUserMedia's stream keeps the mic live (privacy + resource leak).
  // Detach the handlers first so stopping doesn't fire onstop -> transcribe ->
  // setState on an unmounted component (and doesn't upload an abandoned clip).
  useEffect(() => {
    return () => {
      const recorder = mediaRecorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.ondataavailable = null;
        recorder.onstop = null;
        try {
          recorder.stop();
        } catch {
          /* already stopped */
        }
      }
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, []);

  async function transcribe(file: File) {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    const url = URL.createObjectURL(file);
    previewUrlRef.current = url;
    setPreviewUrl(url);

    setBusy(true);
    setStatus("Transcribing…");
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("language", language);
      const res = await apiFetch<SttResponse>("/v1/stt", {
        method: "POST",
        body: form,
        token,
      });
      setResult(res);
      setStatus("");
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) transcribe(file);
  }

  async function handleStartRecording() {
    setStatus("");
    setResult(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        transcribe(new File([blob], "recording.webm", { type: "audio/webm" }));
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
    } catch (e) {
      setStatus(
        e instanceof Error
          ? `Microphone access failed: ${e.message}`
          : "Microphone access failed.",
      );
    }
  }

  function handleStopRecording() {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  }

  return (
    <section className={`mb-6 ${cardClass}`}>
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">🎙️</span> Speech to Text
      </h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
        Record from your microphone or upload an audio file — transcribed via
        Google's speech recognition backend.
      </p>
      <fieldset disabled={!token} className="flex flex-col gap-3">
        <div className="max-w-xs">
          <label
            htmlFor={languageId}
            className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Language
          </label>
          <select
            id={languageId}
            className={inputClass}
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            {Object.entries(languages).map(([code, name]) => (
              <option key={code} value={code}>
                {name} ({code})
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {!recording ? (
            <button
              type="button"
              onClick={handleStartRecording}
              disabled={busy}
              className={primaryButtonClass}
            >
              🔴 Record
            </button>
          ) : (
            <button type="button" onClick={handleStopRecording} className={primaryButtonClass}>
              <span className="inline-flex items-center gap-2">
                <span
                  className="h-2 w-2 animate-pulse rounded-full bg-red-300"
                  aria-hidden="true"
                />
                Stop &amp; transcribe · {formatElapsed(elapsed)}
              </span>
            </button>
          )}
          <label className={`${secondaryButtonClass} cursor-pointer`}>
            📁 Upload audio file
            <input
              type="file"
              accept="audio/*"
              className="hidden"
              onChange={handleFileSelect}
              disabled={busy || recording}
            />
          </label>
          {!token && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Log in to transcribe audio.
            </span>
          )}
        </div>
      </fieldset>
      <StatusLine isError={false}>{status}</StatusLine>
      {previewUrl && (
        <div className="mt-1 flex flex-col gap-2 rounded-lg bg-gray-50 p-3 dark:bg-gray-800">
          <audio controls src={previewUrl} className="w-full" />
          {result && (
            <>
              <p className="whitespace-pre-wrap text-sm">
                {result.text || "(no speech detected)"}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`${badgeClass} ${confidenceBadgeColor(result.confidence)}`}>
                  {Math.round(result.confidence * 100)}% confidence
                </span>
                {result.text && (
                  <button
                    type="button"
                    onClick={() => onSpeakBack(result.text)}
                    className={`${secondaryButtonClass} ml-auto`}
                  >
                    🔊 Speak this back
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

export function VoicePage() {
  const { token } = useAuth();
  const [seed, setSeed] = useState<Seed | null>(null);

  return (
    <>
      <PageHeader icon="🎙️" title="Voice" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Try Minder's text-to-speech and speech-to-text engines directly —
        ~12 languages supported, Turkish by default. Browsing is open for
        everyone; log in to synthesize or transcribe.
      </p>
      <TextToSpeechCard token={token} seed={seed} />
      <SpeechToTextCard
        token={token}
        onSpeakBack={(text) => setSeed({ text, nonce: Date.now() })}
      />
    </>
  );
}
