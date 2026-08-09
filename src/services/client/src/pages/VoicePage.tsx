import { useEffect, useRef, useState } from "react";

import { LoginPanel } from "../components/LoginPanel";
import { apiFetch, apiFetchBlob } from "../lib/api";
import { useAuth } from "../lib/auth";
import { inputClass, primaryButtonClass, secondaryButtonClass, statusClass } from "../lib/ui";

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

function TextToSpeechCard({ token }: { token: string }) {
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const [text, setText] = useState("");
  const [language, setLanguage] = useState("tr");
  const [slow, setSlow] = useState(false);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ language: string; duration: string } | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    apiFetch<LanguagesResponse>("/v1/tts/languages")
      .then((res) => {
        setLanguages(res.languages);
        setLanguage(res.default);
      })
      .catch(() => setStatus("Could not load supported languages."));
  }, []);

  useEffect(() => {
    // Revoke the previous object URL whenever it's replaced/unmounted --
    // otherwise every synthesis leaks a blob URL for the session's lifetime.
    return () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    };
  }, []);

  async function handleSpeak() {
    if (!text.trim()) {
      setStatus("Text is required.");
      return;
    }
    setBusy(true);
    setStatus("Synthesizing…");
    setAudioUrl(null);
    try {
      const { blob, headers } = await apiFetchBlob("/v1/tts", {
        method: "POST",
        body: { text, language, slow },
        token,
      });
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      setAudioUrl(url);
      setMeta({
        language: headers.get("X-Language") ?? language,
        duration: headers.get("X-Duration") ?? "",
      });
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  return (
    <section className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        🔊 Text to Speech
      </h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
        Piper (offline) synthesizes bundled languages as WAV; anything else
        falls back to gTTS (online) as MP3.
      </p>
      <fieldset disabled={!token} className="flex flex-col gap-3">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Text
          </label>
          <textarea
            className={inputClass}
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type something to hear it spoken…"
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Language
            </label>
            <select
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
          <div className="flex items-end pb-1.5">
            <label className="flex items-center gap-2 text-sm">
              <input
                className="h-4 w-4 rounded border-gray-300 disabled:cursor-not-allowed disabled:opacity-60"
                type="checkbox"
                checked={slow}
                onChange={(e) => setSlow(e.target.checked)}
              />
              Speak slowly
            </label>
          </div>
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
        <div className="mt-3 border-t border-gray-100 pt-3 dark:border-gray-800">
          <audio controls src={audioUrl} className="w-full" />
          {meta && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Language: {meta.language}
              {meta.duration && ` · ~${Math.round(parseFloat(meta.duration))}s`} ·{" "}
              <a href={audioUrl} download="speech" className="underline">
                Download
              </a>
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function SpeechToTextCard({ token }: { token: string }) {
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const [language, setLanguage] = useState("tr-TR");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SttResponse | null>(null);
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    apiFetch<LanguagesResponse>("/v1/stt/languages")
      .then((res) => {
        setLanguages(res.languages);
        setLanguage(res.default);
      })
      .catch(() => setStatus("Could not load supported languages."));
  }, []);

  async function transcribe(file: File) {
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
      setStatus(e instanceof Error ? e.message : String(e));
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
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
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
    <section className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        🎙️ Speech to Text
      </h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
        Record from your microphone or upload an audio file — transcribed via
        Google's speech recognition backend.
      </p>
      <fieldset disabled={!token} className="flex flex-col gap-3">
        <div className="max-w-xs">
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Language
          </label>
          <select
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
            <button
              type="button"
              onClick={handleStopRecording}
              className={`${primaryButtonClass} animate-pulse`}
            >
              ⏹ Stop &amp; transcribe
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
      <div className={statusClass(false)}>{status}</div>
      {result && (
        <div className="mt-1 rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-800">
          <p className="whitespace-pre-wrap">{result.text || "(no speech detected)"}</p>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Confidence: {Math.round(result.confidence * 100)}%
          </p>
        </div>
      )}
    </section>
  );
}

export function VoicePage() {
  const { token } = useAuth();
  const [statusMsg, setStatusMsg] = useState("");

  return (
    <>
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Try Minder's text-to-speech and speech-to-text engines directly —
        ~12 languages supported, Turkish by default. Browsing is open for
        everyone; log in to synthesize or transcribe.
      </p>
      <LoginPanel onStatus={setStatusMsg} />
      {statusMsg && <div className={statusClass(false)}>{statusMsg}</div>}
      <TextToSpeechCard token={token} />
      <SpeechToTextCard token={token} />
    </>
  );
}
