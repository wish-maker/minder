"""
Pydantic Models for Model Fine-Tuning Service

Request and response schemas for training jobs and datasets.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TrainingJobCreate(BaseModel):
    """Create a new training job"""
    job_name: str = Field(..., description="Training job name")
    base_model: str = Field(
        default="llama3.2",
        description="Base model to fine-tune"
    )
    dataset_file: str = Field(..., description="Dataset filename")
    model_type: str = Field(
        default="lora",
        description="Fine-tuning type: lora, qlora, or full"
    )
    epochs: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of training epochs"
    )
    learning_rate: float = Field(
        default=0.0001,
        ge=0.00001,
        le=0.01,
        description="Learning rate for training"
    )
    batch_size: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Training batch size"
    )
    context_length: int = Field(
        default=2048,
        ge=256,
        le=8192,
        description="Context window size"
    )
    description: Optional[str] = Field(
        None,
        description="Job description"
    )


class TrainingJobResponse(BaseModel):
    """Training job response"""
    job_id: str
    job_name: str
    base_model: str
    model_type: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    epochs: int
    current_epoch: int = 0
    loss: float = 0.0
    description: Optional[str] = None


class DatasetUploadResponse(BaseModel):
    """Dataset upload response"""
    filename: str
    samples_count: int
    format: str
    size_bytes: int
    validation_passed: bool
    errors: List[str] = Field(default_factory=list)


class TrainingJobStatus(BaseModel):
    """Training job status"""
    job_id: str
    status: str
    progress: float = Field(ge=0, le=100, description="Training progress %")
    current_epoch: int = 0
    total_epochs: int
    loss: float = 0.0
    error: Optional[str] = None


class FineTunedModelInfo(BaseModel):
    """Fine-tuned model information"""
    model_id: str
    base_model: str
    job_id: str
    created_at: str
    model_type: str
    status: str
    size_mb: float
    description: Optional[str] = None


class DatasetInfo(BaseModel):
    """Dataset information"""
    filename: str
    samples_count: int
    format: str
    size_bytes: int
    upload_date: str
    validation_passed: bool
    description: Optional[str] = None
