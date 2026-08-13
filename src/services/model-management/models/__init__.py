"""Pydantic request/response models for the model-management service."""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

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
