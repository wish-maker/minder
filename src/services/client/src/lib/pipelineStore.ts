// The rag-pipeline API has no GET/list endpoint for pipelines (confirmed
// against src/services/rag-pipeline/routes/rag.py) -- once created, a
// pipeline_id only ever exists in the create response. This is the client's
// own record of what it created, namespaced per logged-in username so a
// shared browser profile doesn't mix users' pipelines together.

export interface TrackedPipeline {
  id: string;
  name: string;
  knowledge_base_ids: string[];
  created_at: string;
}

function storageKey(username: string): string {
  return `minder_rag_pipelines_${username}`;
}

export function loadPipelines(username: string): TrackedPipeline[] {
  try {
    const raw = localStorage.getItem(storageKey(username));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function save(username: string, pipelines: TrackedPipeline[]): void {
  localStorage.setItem(storageKey(username), JSON.stringify(pipelines));
}

export function addPipeline(username: string, pipeline: TrackedPipeline): TrackedPipeline[] {
  const next = [...loadPipelines(username), pipeline];
  save(username, next);
  return next;
}

export function removePipeline(username: string, id: string): TrackedPipeline[] {
  const next = loadPipelines(username).filter((p) => p.id !== id);
  save(username, next);
  return next;
}
