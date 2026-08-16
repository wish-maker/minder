import { useId, useState } from "react";

import { EmptyState } from "../components/EmptyState";
import { InfoCallout } from "../components/InfoCallout";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { ApiError, apiFetch, friendlyErrorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { exampleForSchema } from "../lib/jsonSchemaExample";
import { badgeClass, inputClass, secondaryButtonClass } from "../lib/ui";
import { useAsyncResource } from "../lib/useAsyncResource";

export interface LiveTool {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: {
      type?: string;
      properties?: Record<string, { type?: string }>;
      required?: string[];
    };
  };
  metadata: {
    plugin: string;
    endpoint: string;
    method: string;
  };
}

interface LiveToolsResponse {
  tools: LiveTool[];
}

/** Runnable example query for one tool -- pre-fills a type-appropriate
 * example from the tool's own JSON-Schema parameters (editable), then calls
 * the tool's real endpoint with whatever's in the box. GET tools send the
 * parameters as a query string (matching how plugin-registry's read-action
 * route actually reads them); everything else sends a JSON body. */
export function TryItPanel({ tool, token }: { tool: LiveTool; token: string }) {
  const textareaId = useId();
  const [paramsText, setParamsText] = useState(() =>
    JSON.stringify(exampleForSchema(tool.function.parameters), null, 2),
  );
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState("");
  const [isError, setIsError] = useState(false);
  const method = (tool.metadata.method || "POST").toUpperCase();

  async function handleRun() {
    setRunning(true);
    setIsError(false);
    setResult("");
    try {
      const parsed: unknown = JSON.parse(paramsText);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new Error("Parameters must be a JSON object, e.g. {\"coin\": \"bitcoin\"}.");
      }
      const params = parsed as Record<string, unknown>;
      let response: unknown;
      if (method === "GET") {
        const qs = new URLSearchParams(
          Object.entries(params).map(([k, v]) => [k, String(v)]),
        ).toString();
        response = await apiFetch(
          `${tool.metadata.endpoint}${qs ? `?${qs}` : ""}`,
          { method: "GET", token },
        );
      } else {
        response = await apiFetch(tool.metadata.endpoint, {
          method,
          body: params,
          token,
        });
      }
      setResult(JSON.stringify(response, null, 2));
    } catch (e) {
      setResult(
        e instanceof SyntaxError
          ? `That's not valid JSON: ${e.message}`
          : e instanceof ApiError
            ? friendlyErrorMessage(e)
            : e instanceof Error
              ? e.message
              : friendlyErrorMessage(e),
      );
      setIsError(true);
    }
    setRunning(false);
  }

  return (
    <details className="mt-2">
      <summary className="cursor-pointer text-xs font-medium text-indigo-600 dark:text-indigo-400">
        ▶ Try it
      </summary>
      <div className="mt-2 flex flex-col gap-2 border-l-2 border-gray-100 pl-3 dark:border-gray-800">
        <label
          htmlFor={textareaId}
          className="text-xs font-medium text-gray-600 dark:text-gray-400"
        >
          Example parameters — edit, then Run
        </label>
        <textarea
          id={textareaId}
          value={paramsText}
          onChange={(e) => setParamsText(e.target.value)}
          rows={Math.min(8, paramsText.split("\n").length + 1)}
          spellCheck={false}
          className={`${inputClass} font-mono text-xs`}
        />
        {method !== "GET" && (
          <p className="text-xs text-amber-700 dark:text-amber-400">
            ⚠️ This is a {method} action — it may change data, not just read it.
          </p>
        )}
        <button
          onClick={handleRun}
          disabled={running}
          className={`${secondaryButtonClass} self-start`}
        >
          {running ? "Running…" : "▶ Run"}
        </button>
        {result && (
          <pre
            className={`overflow-x-auto rounded-md p-2 text-xs ${
              isError
                ? "bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-200"
                : "bg-gray-50 text-gray-800 dark:bg-gray-800 dark:text-gray-200"
            }`}
          >
            {result}
          </pre>
        )}
      </div>
    </details>
  );
}

function LiveToolCard({ tool, token }: { tool: LiveTool; token: string }) {
  return (
    <section className="mb-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">⚡</span> {tool.function.name}
        <span className={badgeClass}>{tool.metadata.plugin}</span>
      </h3>
      <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
        {tool.function.description || "No description provided."}
      </p>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        {tool.metadata.method} {tool.metadata.endpoint}
      </p>
      <TryItPanel tool={tool} token={token} />
    </section>
  );
}

/** Tools actually callable right now, computed fresh from the plugins
 * currently running on Plugin Registry -- exactly what the AI chat's own
 * function-calling feeds on. Each one carries its full JSON-Schema
 * parameter list (unlike the durable catalog on Available Tools), which is
 * what makes a runnable example possible only here. */
export function InstalledToolsPage() {
  const { token } = useAuth();
  const liveTools = useAsyncResource(
    (signal) =>
      apiFetch<LiveToolsResponse>("/v1/plugins/ai/tools", { signal }).then(
        (r) => r.tools,
      ),
    { timeoutMs: 15_000 },
  );

  return (
    <>
      <PageHeader icon="⚡" title="Installed Tools" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Every function-calling tool actually callable right now, from
        plugins currently running on Plugin Registry. This page has nothing
        to log in for to browse — running a tool that changes data does need
        to be logged in, same as anywhere else in Minder.
      </p>
      <InfoCallout icon="ℹ️">
        Computed fresh on every request. If a plugin isn't running, its
        tools won't appear here even if they're in the catalog on Available
        Tools — installing (and enabling) that plugin is what makes it show
        up.
      </InfoCallout>
      <StatusLine isError={!!liveTools.error}>
        {liveTools.error ?? (liveTools.loading ? "Loading…" : "")}
      </StatusLine>
      {liveTools.data !== null && liveTools.data.length === 0 && (
        <EmptyState className="mb-6">
          No plugin is currently exposing an AI tool.
        </EmptyState>
      )}
      {liveTools.data?.map((t) => (
        <LiveToolCard
          key={`${t.metadata.plugin}:${t.function.name}`}
          tool={t}
          token={token}
        />
      ))}
    </>
  );
}
