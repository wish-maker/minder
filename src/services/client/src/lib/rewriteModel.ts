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

/** Ranked family preferences for the regional-style rewrite, most-preferred
 * first. Found live, in order:
 *  - granite3-moe (small MoE) ignored the Turkish system prompt entirely and
 *    replied in English -- excluded by not being on this list at all.
 *  - llama3.2:latest (this platform's own default LLM, rag-pipeline's
 *    OLLAMA_LLM_MODEL) stopped replying in English, but with the app's real
 *    prompt it often answered the input as a conversational turn instead of
 *    rewriting it (e.g. "Merhaba, bugün nasılsın?" -> "İyiyim, teşekkürler!"),
 *    and even reworded prompts still leaked English/German/Portuguese words
 *    mid-sentence -- a genuine capability limit, not a prompt-wording bug.
 *  - gemma4:26b, screened live against mistral-nemo:12b, command-r:latest and
 *    qwen3:30b with the app's exact prompt across all 4 regional styles and
 *    2 sample sentences, was the only one that reliably rewrote (never
 *    replied) with zero foreign-language contamination and genuinely
 *    distinct, meaning-preserving dialect markers per style (e.g. Ege's
 *    "gari"/"deye"/"-yom", Güneydoğu's "eyidir"). Slower (~15-20s warm,
 *    ~80s cold) but correctness matters more than latency for a one-shot
 *    rewrite button. Prefer it first; llama3.2 remains a fallback tier
 *    rather than removed, since it's still miles better than granite3-moe on
 *    a deployment where gemma4 isn't pulled. */
const PREFERRED_FAMILY_PREFIXES = ["gemma4:", "llama3.2:"];

/** Best default among usable models: the first family from
 * PREFERRED_FAMILY_PREFIXES that has a usable match, else the first usable
 * model. Matches the exact tag prefix (colon included) so a same-family
 * multimodal variant like "llama3.2-vision:latest" doesn't false-match a
 * preference meant for the plain text model. Still just a default --
 * callers should let the user override it, since a deployment with a
 * different model set may need a different pick. */
export function pickDefaultRewriteModel(models: RewriteModelInfo[]): string {
  const usable = usableRewriteModels(models);
  for (const prefix of PREFERRED_FAMILY_PREFIXES) {
    const match = usable.find((m) => m.id.toLowerCase().startsWith(prefix));
    if (match) return match.id;
  }
  return usable[0]?.id ?? "";
}
