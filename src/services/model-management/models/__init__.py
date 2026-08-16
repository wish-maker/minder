"""Pydantic request/response models for the model-management service."""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Constrained vocabularies so an invalid value is a 422 at the edge (and shows in
# /docs) instead of a free string (#143). These match the values the service actually
# produces (`type="local"`, `status="ready"` in GET /models).
ModelType = Literal["local", "remote"]
ModelStatus = Literal["ready", "loading", "error"]


class ModelInfo(BaseModel):
    """Model information"""

    id: str
    name: str
    type: ModelType
    provider: str
    size: str
    status: ModelStatus


class ModelPullRequest(BaseModel):
    """Request body for ``POST /models`` — just the Ollama model id to pull.

    Replaces the old design that required a whole (ignored) ModelInfo body plus a
    ``model_id`` query param (#145). ``protected_namespaces=()`` silences pydantic's
    ``model_`` namespace warning for the ``model_id`` field.
    """

    model_config = ConfigDict(protected_namespaces=())

    # min_length=1 so an empty id is a clean 422 at the edge, not a 503 leaking
    # the ollama client's own internal PullRequest validation error (#532).
    model_id: str = Field(min_length=1)

    @field_validator("model_id")
    @classmethod
    def _reject_custom_registry_host(cls, v: str) -> str:
        """Block pulls from a custom OCI registry host (#679-b): Ollama's model
        name grammar is ``[host[:port]/][namespace/]name[:tag]``, genuinely
        ambiguous between "a namespace" and "a registry hostname" -- both look
        like an arbitrary path segment. A plain namespaced name under the
        DEFAULT Ollama library (e.g. "jimscard/whiterabbit-neo:latest", a real
        community model already in use on this platform) must stay allowed;
        only a segment that's unambiguously a HOST should be rejected.

        Mirrors Docker's own reference-parsing heuristic for telling a host
        apart from a namespace: the first "/"-separated segment is a host
        only if it contains a "." or a ":" (domain or port), or is exactly
        "localhost". A bare "name:tag" (no "/" at all) is never a host --
        that colon is the tag separator, not a port.

        No legitimate use of a custom registry exists anywhere in this
        codebase/docs today (confirmed via grep) -- this is the simplest safe
        default rather than maintaining an allowlist of trusted hosts.
        """
        segments = v.split("/")
        if len(segments) > 1:
            first = segments[0]
            if "." in first or ":" in first or first == "localhost":
                raise ValueError(
                    "model_id may not specify a custom registry host -- only "
                    "the default Ollama library is supported (optionally "
                    "namespaced, e.g. 'namespace/model:tag')"
                )
        return v


class ModelTestRequest(BaseModel):
    """Request body for ``POST /models/{model_id}/test`` (prompt moved out of the
    query string, #145)."""

    prompt: str = "Hello, test."


class ModelConstraints(BaseModel):
    """Model constraints"""

    rate_limit: int
    cost_limit: float
    allowed_users: List[str]
    content_filtering: bool
    max_tokens: int


class FineTuneRequest(BaseModel):
    """Fine-tuning request"""

    base_model: str
    training_data: Optional[str] = None
    epochs: Optional[int] = 3
    learning_rate: Optional[float] = 0.0001
