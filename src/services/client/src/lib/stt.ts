/** Pure STT/TTS language-code helper, split out of VoicePage so it's unit
 * testable without rendering the page (#502). */

/** STT language codes are BCP-47 ("tr-TR"); TTS's are bare ("tr") — #449 — so
 * "verify by transcribing" a just-synthesized clip has to bridge the two lists
 * itself. Matches on the BCP-47 code's language prefix; returns null (not a
 * guess) when no STT locale covers this TTS language, so the caller can disable
 * the action instead of silently transcribing in the wrong language. */
export function matchingSttLanguage(
  ttsCode: string,
  sttLanguages: Record<string, string>,
): string | null {
  const match = Object.keys(sttLanguages).find(
    (code) => code.split("-")[0] === ttsCode,
  );
  return match ?? null;
}
