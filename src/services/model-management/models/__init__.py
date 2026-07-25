"""Pydantic request/response models for the model-management service."""

from typing import List, Optional

from pydantic import BaseModel


class ModelInfo(BaseModel):
    """Model information"""

    id: str
    name: str
    type: str  # "local" or "remote"
    provider: str
    size: str
    status: str


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
