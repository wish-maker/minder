/** Pure model-selection helper for the Voice page's regional-style rewrite,
 * split out of VoicePage so it's unit testable without rendering the page
 * (same rationale as lib/stt.ts's matchingSttLanguage). */

export interface RewriteModelInfo {
  id: string;
  status: string;
}

/** Models actually usable for a chat-style rewrite: ready, and not an
 * embedding-only model (there's no capability flag to check here, but
 * "embed" in the name is a near-universal Ollama naming convention — e.g.
 * nomic-embed-text — and those can't chat at all). */
export function usableRewriteModels(
  models: RewriteModelInfo[],
): RewriteModelInfo[] {
  return models.filter(
    (m) => m.status === "ready" && !m.id.toLowerCase().includes("embed"),
  );
}

/** Best default among usable models. Found live: picking the plain "first
 * usable model" landed on a small model that ignored Turkish instructions
 * entirely and replied in English — prefers the `llama3.2` family instead,
 * since it's already this platform's own default LLM (rag-pipeline's
 * OLLAMA_LLM_MODEL), not an arbitrary guess. Matches the exact tag prefix
 * ("llama3.2:") so a same-family variant like "llama3.2-vision:latest"
 * (multimodal, not necessarily as reliable for a plain text task) doesn't
 * false-match. Still just a default — callers should let the user override
 * it, since a deployment with a different model set may need a different pick. */
export function pickDefaultRewriteModel(models: RewriteModelInfo[]): string {
  const usable = usableRewriteModels(models);
  const llama = usable.find((m) => m.id.toLowerCase().startsWith("llama3.2:"));
  return (llama ?? usable[0])?.id ?? "";
}
